import pandas as pd
import sqlite3
import datetime
import os

FEATURES = [
    'jockey_id', 'trainer_id', 'program_number', 'distance_m', 'field_size',
    'carry_weight_kg', 'body_weight_kg', 'morning_odds', 'horse_age', 'horse_sex',
    'track', 'track_condition', 'weather', 'days_since_last_race',
    'horse_win_rate', 'jockey_win_rate', 'trainer_win_rate', 'sire_win_rate',
    'past_avg_s1f_time', 'past_avg_g3f_time',
    'humidity', 'past_avg_start_rank', 'past_avg_mid_rank', 'past_avg_finish_rank',
    'surface', 'grade', 'body_weight_delta_kg', 'morning_odds_rank',
    'distance_win_rate', 'jockey_horse_win_rate',
]
TARGET = 'relevance'

_QUERY = """
SELECT
    r.id as race_id,
    r.race_date,
    r.distance_m,
    r.field_size,
    r.track,
    r.track_condition,
    r.weather,
    r.humidity,
    r.surface,
    r.grade,
    e.horse_id,
    e.jockey_id,
    e.trainer_id,
    e.program_number,
    e.carry_weight_kg,
    e.body_weight_kg,
    e.morning_odds,
    h.age as horse_age,
    h.sex as horse_sex,
    p.sire_id,
    t.s1f_time,
    t.g3f_time,
    t.corner1_rank,
    t.corner2_rank,
    t.corner3_rank,
    t.corner4_rank,
    t.corner5_rank,
    t.corner6_rank,
    t.corner7_rank,
    res.finish_position,
    res.finish_time_s,
    CASE WHEN res.finish_position = 1 THEN 1 ELSE 0 END as is_win
FROM races r
JOIN race_entries e ON r.id = e.race_id
JOIN horses h ON e.horse_id = h.id
LEFT JOIN pedigree p ON h.id = p.horse_id
LEFT JOIN inrace_timings t ON r.id = t.race_id AND e.horse_id = t.horse_id
LEFT JOIN race_results res ON r.id = res.race_id AND e.horse_id = res.horse_id
ORDER BY r.race_date, r.id
"""


def _apply_features(df: pd.DataFrame):
    """Apply feature engineering to a raw DataFrame. Modifies in place."""
    df['horse_sex'] = df['horse_sex'].astype('category')
    df['track'] = df['track'].astype('category')
    df['track_condition'] = df['track_condition'].fillna('건조').astype('category')
    df['weather'] = df['weather'].fillna('맑음').astype('category')
    df['surface'] = df['surface'].fillna('Dirt').astype('category')
    df['grade'] = df['grade'].fillna('unknown').astype('category')
    df['humidity'] = df['humidity'].fillna(5.0).astype(float)
    df['body_weight_kg'] = df['body_weight_kg'].fillna(500.0)
    df['horse_age'] = df['horse_age'].fillna(3).astype(int)

    # Standardize Start Rank and Finish Rank
    df['start_rank'] = df['corner1_rank'].fillna(7.0)
    corner_cols = ['corner7_rank', 'corner6_rank', 'corner5_rank', 'corner4_rank', 'corner3_rank', 'corner2_rank', 'corner1_rank']
    df['finish_rank'] = df[corner_cols].bfill(axis=1).iloc[:, 0].fillna(7.0)
    
    def calc_mid(row):
        cols = ['corner1_rank', 'corner2_rank', 'corner3_rank', 'corner4_rank', 'corner5_rank', 'corner6_rank', 'corner7_rank']
        vals = [row[c] for c in cols if pd.notnull(row[c])]
        if len(vals) > 2:
            return sum(vals[1:-1]) / (len(vals) - 2)
        elif len(vals) == 2:
            return (vals[0] + vals[1]) / 2.0
        elif len(vals) == 1:
            return vals[0]
        else:
            return 7.0
            
    df['mid_rank'] = df.apply(calc_mid, axis=1)

    df.sort_values(['horse_id', 'race_date'], inplace=True)
    df['days_since_last_race'] = (
        df.groupby('horse_id')['race_date']
        .transform(lambda x: (x - x.shift(1)).dt.days)
        .fillna(30.0)
    )
    df['horse_win_rate'] = (
        df.groupby('horse_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )
    df['past_avg_s1f_time'] = (
        df.groupby('horse_id')['s1f_time']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(14.0)
    )
    df['past_avg_g3f_time'] = (
        df.groupby('horse_id')['g3f_time']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(38.0)
    )
    df['past_avg_start_rank'] = (
        df.groupby('horse_id')['start_rank']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(7.0)
    )
    df['past_avg_mid_rank'] = (
        df.groupby('horse_id')['mid_rank']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(7.0)
    )
    df['past_avg_finish_rank'] = (
        df.groupby('horse_id')['finish_rank']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(7.0)
    )
    
    df.sort_values(['jockey_id', 'race_date'], inplace=True)
    df['jockey_win_rate'] = (
        df.groupby('jockey_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )
    df.sort_values(['trainer_id', 'race_date'], inplace=True)
    df['trainer_win_rate'] = (
        df.groupby('trainer_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )
    df.sort_values(['sire_id', 'race_date'], inplace=True)
    df['sire_win_rate'] = (
        df.groupby('sire_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )

    # Distance bucket win rate (short / middle / long)
    df['_distance_bucket'] = pd.cut(
        df['distance_m'],
        bins=[0, 1300, 1800, 99999],
        labels=['short', 'middle', 'long'],
    )
    df.sort_values(['horse_id', '_distance_bucket', 'race_date'], inplace=True)
    df['distance_win_rate'] = (
        df.groupby(['horse_id', '_distance_bucket'], observed=True)['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0.0)
    )

    # Jockey-horse pair win rate
    df.sort_values(['jockey_id', 'horse_id', 'race_date'], inplace=True)
    df['jockey_horse_win_rate'] = (
        df.groupby(['jockey_id', 'horse_id'])['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0.0)
    )

    df['relevance'] = df['finish_position'].apply(
        lambda x: 3 if x == 1 else (2 if x == 2 else (1 if x == 3 else 0))
    )
    df.sort_values(['race_date', 'race_id'], inplace=True)

    # Body weight delta (horse weight change from previous race)
    df.sort_values(['horse_id', 'race_date', 'race_id'], inplace=True)
    df['body_weight_delta_kg'] = (
        df.groupby('horse_id')['body_weight_kg']
        .transform(lambda x: x - x.shift(1))
        .fillna(0.0)
    )

    # Morning odds rank within race (1 = favourite = lowest odds)
    df['morning_odds_rank'] = (
        df.groupby('race_id')['morning_odds']
        .rank(method='min', ascending=True)
        .astype(int)
    )

    df.sort_values(['race_date', 'race_id'], inplace=True)
    df['finish_time_s'] = df['finish_time_s'].fillna(999.0)
    return df


def load_dataset_pg(db_url: str):
    """
    Load training dataset from PostgreSQL.
    """
    from sqlalchemy import create_engine, text

    # Derive a synchronous URL: replace async driver specifier so that the
    # standard sync create_engine can connect (async driver can't be used here).
    sync_url = (
        db_url
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgresql://", "postgresql+psycopg2://")
        .replace("sqlite+aiosqlite://", "sqlite://")
    )
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        df = pd.read_sql(text(_QUERY), conn, parse_dates=['race_date'])
    engine.dispose()

    df = _apply_features(df)

    if df['race_date'].min() >= pd.to_datetime('2026-01-01'):
        n = len(df)
        train_df = df.iloc[:int(n*0.7)].copy()
        val_df = df.iloc[int(n*0.7):int(n*0.85)].copy()
        test_df = df.iloc[int(n*0.85):].copy()
    else:
        train_mask = (df['race_date'] >= '2021-01-01') & (df['race_date'] <= '2024-12-31')
        val_mask   = (df['race_date'] >= '2025-01-01') & (df['race_date'] <= '2025-12-31')
        test_mask  = (df['race_date'] >= '2026-01-01') & (df['race_date'] <= '2026-12-31')
        train_df = df[train_mask].copy()
        val_df   = df[val_mask].copy()
        test_df  = df[test_mask].copy()

    return (
        train_df,
        val_df,
        test_df,
        FEATURES,
        TARGET,
    )


def load_dataset(db_path: str = "test_dod.db"):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database {db_path} not found. Run synthetic_data.py first.")
        
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(_QUERY, conn, parse_dates=['race_date'])
    conn.close()
    
    df = _apply_features(df)

    if df['race_date'].min() >= pd.to_datetime('2026-01-01'):
        n = len(df)
        train_df = df.iloc[:int(n*0.7)].copy()
        val_df = df.iloc[int(n*0.7):int(n*0.85)].copy()
        test_df = df.iloc[int(n*0.85):].copy()
    else:
        train_mask = (df['race_date'] >= '2021-01-01') & (df['race_date'] <= '2024-12-31')
        val_mask   = (df['race_date'] >= '2025-01-01') & (df['race_date'] <= '2025-12-31')
        test_mask  = (df['race_date'] >= '2026-01-01') & (df['race_date'] <= '2026-12-31')
        train_df = df[train_mask].copy()
        val_df   = df[val_mask].copy()
        test_df  = df[test_mask].copy()

    return train_df, val_df, test_df, FEATURES, TARGET

if __name__ == "__main__":
    train, val, test, feats, tgt = load_dataset()
    print(f"Train size: {len(train)}")
    print(f"Val size: {len(val)}")
    print(f"Test size: {len(test)}")
