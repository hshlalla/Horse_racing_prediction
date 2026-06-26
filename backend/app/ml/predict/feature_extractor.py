import os
import datetime
import pandas as pd
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from catboost import CatBoostRanker
from scipy.special import softmax

from app.db.models.crawl import Race, RaceEntry, Horse, Jockey, Trainer, RaceResult, InraceTiming

# Load Model once globally
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "catboost_ranker.cbm")
model = None
if os.path.exists(MODEL_PATH):
    model = CatBoostRanker()
    model.load_model(MODEL_PATH)

async def extract_inference_features(db: AsyncSession, race_id: int):
    # Fetch Race
    result = await db.execute(select(Race).filter_by(id=race_id))
    race = result.scalars().first()
    if not race:
        return None, None
        
    # Fetch Entries
    result = await db.execute(select(RaceEntry).filter_by(race_id=race_id))
    entries = result.scalars().all()
    
    if not entries:
        return None, None
        
    features_list = []
    
    for e in entries:
        # Load horse
        res_h = await db.execute(select(Horse).filter_by(id=e.horse_id))
        horse = res_h.scalars().first()
        
        # Calculate historical stats (mocking the exact EWMA logic for speed, using simple averages of last 5)
        # In a real production system, this would be a materialized view or pre-computed.
        query_history = text("""
            SELECT r.race_date, res.finish_position, t.s1f_time, t.g3f_time
            FROM race_results res
            JOIN races r ON res.race_id = r.id
            LEFT JOIN inrace_timings t ON res.race_id = t.race_id AND res.horse_id = t.horse_id
            WHERE res.horse_id = :horse_id AND r.race_date < :current_date
            ORDER BY r.race_date DESC
            LIMIT 5
        """)
        history_res = await db.execute(query_history, {"horse_id": e.horse_id, "current_date": race.race_date})
        history = history_res.fetchall()
        
        wins = 0
        s1f_sum = 0
        g3f_sum = 0
        s1f_cnt = 0
        g3f_cnt = 0
        last_race_date = None
        
        for idx, row in enumerate(history):
            if idx == 0:
                last_race_date = datetime.datetime.strptime(row[0], '%Y-%m-%d').date() if isinstance(row[0], str) else row[0]
            if row[1] == 1:
                wins += 1
            if row[2] is not None:
                s1f_sum += row[2]
                s1f_cnt += 1
            if row[3] is not None:
                g3f_sum += row[3]
                g3f_cnt += 1
                
        horse_win_rate = wins / len(history) if history else 0.0
        past_avg_s1f = s1f_sum / s1f_cnt if s1f_cnt > 0 else 14.0
        past_avg_g3f = g3f_sum / g3f_cnt if g3f_cnt > 0 else 38.0
        
        days_since = 30.0
        if last_race_date:
            days_since = (race.race_date - last_race_date).days
            
        # Simplified jocky/trainer win rates for inference speed
        j_query = text("""
            SELECT AVG(CASE WHEN finish_position = 1 THEN 1 ELSE 0 END) 
            FROM race_results res JOIN races r ON res.race_id = r.id JOIN race_entries e ON res.race_id = e.race_id AND res.horse_id = e.horse_id
            WHERE e.jockey_id = :j_id AND r.race_date < :current_date
        """)
        j_res = await db.execute(j_query, {"j_id": e.jockey_id, "current_date": race.race_date})
        j_win_rate = j_res.scalar() or 0.0
        
        t_query = text("""
            SELECT AVG(CASE WHEN finish_position = 1 THEN 1 ELSE 0 END) 
            FROM race_results res JOIN races r ON res.race_id = r.id JOIN race_entries e ON res.race_id = e.race_id AND res.horse_id = e.horse_id
            WHERE e.trainer_id = :t_id AND r.race_date < :current_date
        """)
        t_res = await db.execute(t_query, {"t_id": e.trainer_id, "current_date": race.race_date})
        t_win_rate = t_res.scalar() or 0.0
        
        feat = {
            'jockey_id': str(e.jockey_id),
            'trainer_id': str(e.trainer_id),
            'program_number': e.program_number,
            'distance_m': race.distance_m,
            'field_size': race.field_size or 10,
            'carry_weight_kg': e.carry_weight_kg or 55.0,
            'body_weight_kg': e.body_weight_kg or 500.0,
            'morning_odds': e.morning_odds or 10.0,
            'horse_age': horse.age or 3,
            'horse_sex': str(horse.sex),
            'track': str(race.track),
            'track_condition': str(race.track_condition or '건조'),
            'weather': str(race.weather or '맑음'),
            'days_since_last_race': days_since,
            'horse_win_rate': horse_win_rate,
            'jockey_win_rate': j_win_rate,
            'trainer_win_rate': t_win_rate,
            'sire_win_rate': 0.1, # mock sire for speed
            'past_avg_s1f_time': past_avg_s1f,
            'past_avg_g3f_time': past_avg_g3f
        }
        features_list.append(feat)
        
    df = pd.DataFrame(features_list)
    return df, entries
