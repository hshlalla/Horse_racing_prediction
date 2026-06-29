import pandas as pd
import numpy as np
import sqlite3
import datetime
import os

# Feature set v2 (2026-06-29): pruned 17 dead/sparse features, added 5 severity-tiered
# health features. Dropped (all-zero importance across SEOUL/BUSAN/JEJU champions):
#   body_weight_kg, body_weight_delta_kg, horse_age, horse_sex, track, surface,
#   grade, humidity, sire_win_rate, odds_drift, jockey_changed
# Dropped (workout data structurally sparse ~8% coverage, train/val mismatch):
#   recent_workout_time_s, recent_workout_rank, swim_count_recent,
#   recent_workout_count_30d, start_training_passed, days_since_start_training
# These columns are still produced by the SQL/feature code so they can be re-added
# once their underlying data is dense enough to measure.
FEATURES = [
    # --- Core market / form features (proven importance) ---
    'jockey_id', 'trainer_id', 'program_number', 'distance_m', 'field_size',
    'carry_weight_kg', 'morning_odds', 'track_condition', 'weather',
    'days_since_last_race',
    'horse_win_rate', 'jockey_win_rate', 'trainer_win_rate',
    'past_avg_s1f_time', 'past_avg_g3f_time',
    'past_avg_start_rank', 'past_avg_mid_rank', 'past_avg_finish_rank',
    'morning_odds_rank', 'distance_win_rate', 'jockey_horse_win_rate',
    'jockey_win_rate_delta',  # current jockey win rate - previous jockey win rate
    # --- Health features (non-market signal) ---
    # Confirmed predictive 2026-06-29: with clean morning_odds AND the fixed
    # _race_log_loss metric, adding these drops SEOUL ensemble val_log_loss
    # 1.9438 → 1.9080. (Earlier "no effect" was an artifact of the broken metric
    # + corrupted odds — both fixed.)
    'injury_count_30d',           # all health incidents in 30 days before race
    'days_since_injury',          # days since most recent health record (999 = never)
    'serious_injury_count_30d',   # locomotor/serious injuries in 30 days (파행/근육통/관절염/골절/건염/마비/부종)
    'serious_injury_count_90d',   # locomotor/serious injuries in 90 days
    'days_since_serious_injury',  # days since last serious injury (999 = never)
    'illness_count_30d',          # systemic illness in 30 days (감기/식욕부진/출혈/위궤양/비염)
    'chronic_injury_rate',        # lifetime health records ÷ career starts (만성 약체마 지표)
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
    h.last_start_training_date,
    h.last_start_training_passed,
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
    CASE WHEN res.finish_position = 1 THEN 1 ELSE 0 END as is_win,
    odds_snap.opening_odds,
    odds_snap.closing_odds,
    wk.time_s           AS recent_workout_time_s,
    wk.rank             AS recent_workout_rank,
    wk.swim_count_recent,
    hr.injury_count_30d,
    hr.days_since_injury,
    hr.serious_injury_count_30d,
    hr.serious_injury_count_90d,
    hr.days_since_serious_injury,
    hr.illness_count_30d,
    hr.total_injury_count,
    wk_cnt.recent_workout_count_30d
FROM races r
JOIN race_entries e ON r.id = e.race_id
JOIN horses h ON e.horse_id = h.id
LEFT JOIN pedigree p ON h.id = p.horse_id
LEFT JOIN inrace_timings t ON r.id = t.race_id AND e.horse_id = t.horse_id
LEFT JOIN race_results res ON r.id = res.race_id AND e.horse_id = res.horse_id
LEFT JOIN (
    SELECT
        race_id, horse_id,
        FIRST_VALUE(win_odds) OVER (
            PARTITION BY race_id, horse_id ORDER BY snapshot_time
        ) AS opening_odds,
        LAST_VALUE(win_odds) OVER (
            PARTITION BY race_id, horse_id
            ORDER BY snapshot_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS closing_odds
    FROM odds_snapshots
    WHERE win_odds IS NOT NULL
) odds_snap ON odds_snap.race_id = r.id AND odds_snap.horse_id = e.horse_id
LEFT JOIN LATERAL (
    SELECT time_s, rank, swim_count_recent
    FROM workout_times
    WHERE horse_id = e.horse_id
      AND workout_date < r.race_date
    ORDER BY workout_date DESC
    LIMIT 1
) wk ON true
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS recent_workout_count_30d
    FROM workout_times
    WHERE horse_id = e.horse_id
      AND workout_date >= r.race_date - INTERVAL '30 days'
      AND workout_date < r.race_date
) wk_cnt ON true
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE record_date >= r.race_date - INTERVAL '30 days') AS injury_count_30d,
        (r.race_date - MAX(record_date))::int AS days_since_injury,
        -- 운동기·중증 질환 (경주력 직접 타격): 파행/근육통/관절염/골절/건염/마비/부종
        COUNT(*) FILTER (
            WHERE record_date >= r.race_date - INTERVAL '30 days'
              AND condition IN ('파행','근육통','관절염','골절','건염','마비','부종')
        ) AS serious_injury_count_30d,
        COUNT(*) FILTER (
            WHERE record_date >= r.race_date - INTERVAL '90 days'
              AND condition IN ('파행','근육통','관절염','골절','건염','마비','부종')
        ) AS serious_injury_count_90d,
        (r.race_date - MAX(record_date) FILTER (
            WHERE condition IN ('파행','근육통','관절염','골절','건염','마비','부종')
        ))::int AS days_since_serious_injury,
        -- 전신 질환 (컨디션 저하): 감기/식욕부진/출혈/위궤양/비염
        COUNT(*) FILTER (
            WHERE record_date >= r.race_date - INTERVAL '30 days'
              AND condition IN ('감기','식욕부진','출혈','위궤양','비염')
        ) AS illness_count_30d,
        COUNT(*) AS total_injury_count
    FROM health_records
    WHERE horse_id = e.horse_id
      AND record_date < r.race_date
) hr ON true
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

    # Jockey change: did the jockey change from the previous race for this horse?
    df.sort_values(['horse_id', 'race_date', 'race_id'], inplace=True)
    df['_prev_jockey_id'] = df.groupby('horse_id')['jockey_id'].shift(1)
    df['_prev_jockey_win_rate'] = df.groupby('horse_id')['jockey_win_rate'].shift(1)
    df['jockey_changed'] = (
        df['_prev_jockey_id'].notna() & (df['jockey_id'] != df['_prev_jockey_id'])
    ).astype(int)
    df['jockey_win_rate_delta'] = (
        df['jockey_win_rate'] - df['_prev_jockey_win_rate']
    ).fillna(0.0)
    df.drop(columns=['_prev_jockey_id', '_prev_jockey_win_rate'], inplace=True)

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
    # Fill NaN odds with a large number so unknown-odds horses rank last
    df['_odds_filled'] = df.groupby('race_id')['morning_odds'].transform(
        lambda x: x.fillna(x.max() if x.notna().any() else 99.9)
    )
    df['morning_odds_rank'] = (
        df.groupby('race_id')['_odds_filled']
        .rank(method='min', ascending=True)
        .fillna(df['field_size'])
        .astype(int)
    )
    df['morning_odds'] = df['morning_odds'].fillna(df['_odds_filled'])
    df.drop(columns=['_odds_filled'], inplace=True)
    # Clip sentinel/garbage odds (e.g. 9999.9 in some 2021 rows, parse errors).
    # Real KRA win odds top out well under 200; clipping neutralises sentinels
    # without distorting the favourite/longshot ordering the model relies on.
    df['morning_odds'] = df['morning_odds'].clip(lower=1.0, upper=200.0)

    # Odds drift: (opening - closing) / opening
    # Positive = odds shortened (money came in = hot pick late)
    # Negative = odds drifted out (money went elsewhere)
    if 'opening_odds' in df.columns and 'closing_odds' in df.columns:
        df['opening_odds'] = df['opening_odds'].fillna(df['morning_odds'])
        df['closing_odds'] = df['closing_odds'].fillna(df['morning_odds'])
        df['odds_drift'] = (
            (df['opening_odds'] - df['closing_odds'])
            / df['opening_odds'].replace(0, np.nan)
        ).fillna(0.0).clip(-1.0, 2.0)
    else:
        df['odds_drift'] = 0.0

    # Workout features (NULL = no workout data recorded before this race)
    df['recent_workout_time_s'] = df['recent_workout_time_s'].fillna(70.0)   # slow = unknown
    df['recent_workout_rank'] = df['recent_workout_rank'].fillna(8).astype(int)
    df['swim_count_recent'] = df['swim_count_recent'].fillna(0).astype(int)
    df['recent_workout_count_30d'] = df['recent_workout_count_30d'].fillna(0).astype(int)

    # Start training features
    df['start_training_passed'] = (
        df['last_start_training_passed']
        .map({True: 1, False: 0})
        .fillna(-1)
        .astype(int)
    )
    if 'last_start_training_date' in df.columns:
        df['last_start_training_date'] = pd.to_datetime(df['last_start_training_date'])
        df['days_since_start_training'] = (
            (df['race_date'] - df['last_start_training_date'])
            .dt.days
            .fillna(999)
            .clip(upper=999)
            .astype(int)
        )
    else:
        df['days_since_start_training'] = 999

    # Health features (NULL = no health records in DB for this horse before this race)
    df['injury_count_30d'] = df['injury_count_30d'].fillna(0).astype(int)
    df['days_since_injury'] = df['days_since_injury'].fillna(999).astype(int)

    # Severity-tiered health features
    df['serious_injury_count_30d'] = df['serious_injury_count_30d'].fillna(0).astype(int)
    df['serious_injury_count_90d'] = df['serious_injury_count_90d'].fillna(0).astype(int)
    df['days_since_serious_injury'] = (
        df['days_since_serious_injury'].fillna(999).clip(upper=999).astype(int)
    )
    df['illness_count_30d'] = df['illness_count_30d'].fillna(0).astype(int)
    df['total_injury_count'] = df['total_injury_count'].fillna(0).astype(int)

    # Chronic fragility: lifetime health records ÷ career starts so far.
    # career_starts uses cumcount (0-based) over the time-sorted per-horse history,
    # so it counts ONLY prior races — no leakage from the current/future races.
    df.sort_values(['horse_id', 'race_date', 'race_id'], inplace=True)
    career_starts = df.groupby('horse_id').cumcount()  # 0 for first start
    df['chronic_injury_rate'] = (
        df['total_injury_count'] / (career_starts + 1)
    ).clip(upper=50.0).astype(float)

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

    # Dynamic cutoff: val = most recent 6 months, train = everything before that.
    # This ensures the latest data always trains the model regardless of the current year.
    today = pd.Timestamp.today().normalize()
    val_start = today - pd.DateOffset(months=6)
    train_mask = df['race_date'] < val_start
    val_mask   = df['race_date'] >= val_start
    train_df = df[train_mask].copy()
    val_df   = df[val_mask].copy()
    test_df  = pd.DataFrame(columns=df.columns)   # not used in production pipeline

    import logging as _logging
    _logging.getLogger(__name__).info(
        "Dataset split: train < %s  val >= %s  (train=%d val=%d)",
        val_start.date(), val_start.date(), len(train_df), len(val_df),
    )

    # Fall back to fractional split when val is too small
    if len(val_df) < 50:
        unique_races = df[['race_id','race_date']].drop_duplicates().sort_values('race_date')
        n_races = len(unique_races)
        cut85 = unique_races.iloc[int(n_races * 0.85)]['race_date']
        train_df = df[df['race_date'] <  cut85].copy()
        val_df   = df[df['race_date'] >= cut85].copy()
        test_df  = pd.DataFrame(columns=df.columns)
        _logging.getLogger(__name__).warning(
            "Val set too small — using 85%% quantile split: train<%.10s val>=%.10s",
            cut85, cut85,
        )

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
