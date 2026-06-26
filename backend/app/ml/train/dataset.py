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
]
TARGET = 'relevance'

_PG_QUERY = """
SELECT
    r.id as race_id,
    r.race_date,
    r.distance_m,
    r.field_size,
    r.track,
    r.track_condition,
    r.weather,
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
    df['body_weight_kg'] = df['body_weight_kg'].fillna(500.0)
    df['horse_age'] = df['horse_age'].fillna(3).astype(int)

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
    df['relevance'] = df['finish_position'].apply(
        lambda x: 3 if x == 1 else (2 if x == 2 else (1 if x == 3 else 0))
    )
    df.sort_values(['race_date', 'race_id'], inplace=True)
    df['finish_time_s'] = df['finish_time_s'].fillna(999.0)
    return df


def load_dataset_pg(db_url: str):
    """
    Load training dataset from PostgreSQL.
    Returns (train_df, val_df, test_df, FEATURES, TARGET).
    Uses a sync SQLAlchemy engine — safe for batch training jobs.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)
    with engine.connect() as conn:
        df = pd.read_sql(text(_PG_QUERY), conn, parse_dates=['race_date'])
    engine.dispose()

    df = _apply_features(df)

    train_mask = (df['race_date'] >= '2021-01-01') & (df['race_date'] <= '2024-12-31')
    val_mask = (df['race_date'] >= '2025-01-01') & (df['race_date'] <= '2025-12-31')
    test_mask = (df['race_date'] >= '2026-01-01') & (df['race_date'] <= '2026-12-31')

    return (
        df[train_mask].copy(),
        df[val_mask].copy(),
        df[test_mask].copy(),
        FEATURES,
        TARGET,
    )


def load_dataset(db_path: str = "test_dod.db"):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database {db_path} not found. Run synthetic_data.py first.")
        
    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT 
        r.id as race_id,
        r.race_date,
        r.distance_m,
        r.field_size,
        r.track,
        r.track_condition,
        r.weather,
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
    
    df = pd.read_sql(query, conn, parse_dates=['race_date'])
    conn.close()
    
    # Feature Engineering
    df['horse_sex'] = df['horse_sex'].astype('category')
    df['track'] = df['track'].astype('category')
    df['track_condition'] = df['track_condition'].fillna('건조').astype('category')
    df['weather'] = df['weather'].fillna('맑음').astype('category')
    df['body_weight_kg'] = df['body_weight_kg'].fillna(500.0)
    
    # Rest Days (Days Since Last Race)
    df = df.sort_values(by=['horse_id', 'race_date'])
    df['days_since_last_race'] = df.groupby('horse_id')['race_date'].transform(lambda x: (x - x.shift(1)).dt.days).fillna(30.0)
    
    # Historical Win Rates (EWMA)
    # Using shift(1) to avoid data leakage
    df['horse_win_rate'] = df.groupby('horse_id')['is_win'].transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean()).fillna(0)
    df['past_avg_s1f_time'] = df.groupby('horse_id')['s1f_time'].transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean()).fillna(14.0)
    df['past_avg_g3f_time'] = df.groupby('horse_id')['g3f_time'].transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean()).fillna(38.0)
    
    df = df.sort_values(by=['jockey_id', 'race_date'])
    df['jockey_win_rate'] = df.groupby('jockey_id')['is_win'].transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean()).fillna(0)
    
    df = df.sort_values(by=['trainer_id', 'race_date'])
    df['trainer_win_rate'] = df.groupby('trainer_id')['is_win'].transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean()).fillna(0)
    
    df = df.sort_values(by=['sire_id', 'race_date'])
    df['sire_win_rate'] = df.groupby('sire_id')['is_win'].transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean()).fillna(0)
    
    # Relevance Score for LTR
    # 1st: 3, 2nd: 2, 3rd: 1, Others: 0
    df['relevance'] = df['finish_position'].apply(lambda x: 3 if x == 1 else (2 if x == 2 else (1 if x == 3 else 0)))
    
    # Restore original sorting
    df = df.sort_values(by=['race_date', 'race_id'])
    
    # Handle DNF
    df['finish_time_s'] = df['finish_time_s'].fillna(999.0)
    
    # Split Dataset
    train_mask = (df['race_date'] >= '2021-01-01') & (df['race_date'] <= '2024-12-31')
    val_mask = (df['race_date'] >= '2025-01-01') & (df['race_date'] <= '2025-12-31')
    test_mask = (df['race_date'] >= '2026-01-01') & (df['race_date'] <= '2026-12-31')
    
    train_df = df[train_mask].copy()
    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()
    
    features = [
        'jockey_id', 'trainer_id', 'program_number', 'distance_m', 'field_size', 
        'carry_weight_kg', 'body_weight_kg', 'morning_odds', 'horse_age', 'horse_sex', 
        'track', 'track_condition', 'weather', 'days_since_last_race',
        'horse_win_rate', 'jockey_win_rate', 'trainer_win_rate', 'sire_win_rate',
        'past_avg_s1f_time', 'past_avg_g3f_time'
    ]
    target = 'relevance'
    
    return train_df, val_df, test_df, features, target

if __name__ == "__main__":
    train, val, test, feats, tgt = load_dataset()
    print(f"Train size: {len(train)}")
    print(f"Val size: {len(val)}")
    print(f"Test size: {len(test)}")
