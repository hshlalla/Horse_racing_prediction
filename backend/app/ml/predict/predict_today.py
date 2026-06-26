import asyncio
import datetime
import requests
import warnings
warnings.filterwarnings('ignore')

from app.db.session import async_session_factory
from app.db.models.crawl import Horse, Jockey, Trainer
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.train.dataset import load_dataset
from app.ml.train.models.lgbm_binary import train_lgbm
from sqlalchemy import select
from scipy.special import softmax
import pandas as pd

async def predict_today_races(meet: str = "3", track_name: str = "BUSAN"):
    # 1. Train Model First
    print("Loading historical data to compute features and train model...")
    train_df, val_df, test_df, features, target = load_dataset("test_dod.db")
    
    # We train on everything up to yesterday to get the most accurate model
    all_df = pd.concat([train_df, val_df, test_df])
    model = train_lgbm(all_df, all_df.iloc[:100], features, target)
    
    # 2. Fetch today's upcoming races
    today_str = datetime.date.today().strftime("%Y%m%d")
    # For testing, since today is June 26, 2026.
    
    print(f"Fetching upcoming races for {today_str} at {track_name}...")
    res_list = requests.post(
        "https://race.kra.co.kr/chulmainfo/ChulmaDetailInfoList.do",
        headers={"User-Agent": "Mozilla/5.0"},
        data={"Act": "02", "Sub": "1", "meet": meet, "rcDate": today_str},
        timeout=10
    )
    res_list.encoding = 'euc-kr'
    
    # We just need to find how many races there are today
    # "javascript:goChulmapyo("3","20260626","1")"
    races_today = []
    for line in res_list.text.split('\n'):
        if 'goChulmapyo' in line and today_str in line:
            parts = line.split('"')
            if len(parts) >= 8:
                rc_no = parts[7]
                if rc_no.isdigit() and int(rc_no) not in races_today:
                    races_today.append(int(rc_no))
                    
    races_today = sorted(races_today)
    if not races_today:
        print("No races scheduled for today.")
        return
        
    print(f"Found {len(races_today)} races scheduled for today.")
    
    # 3. For each race, generate features and predict
    async with async_session_factory() as session:
        for rc_no in races_today:
            print(f"\n--- {track_name} Race {rc_no} ---")
            res = requests.post(
                "https://race.kra.co.kr/chulmainfo/chulmaDetailInfoChulmapyo.do",
                headers={"User-Agent": "Mozilla/5.0"},
                data={"meet": meet, "rcDate": today_str, "rcNo": str(rc_no)},
                timeout=10
            )
            res.encoding = 'euc-kr'
            entries = KRALiveParser.parse_upcoming_race(res.text)
            
            if not entries:
                print("Could not parse entries.")
                continue
                
            pred_data = []
            
            for entry in entries:
                # Lookup IDs
                stmt = select(Horse.id).filter_by(name=entry['horse_name'])
                horse_id = (await session.execute(stmt)).scalars().first()
                
                stmt = select(Jockey.id).filter_by(name=entry['jockey'])
                jockey_id = (await session.execute(stmt)).scalars().first()
                
                stmt = select(Trainer.id).filter_by(name=entry['trainer'])
                trainer_id = (await session.execute(stmt)).scalars().first()
                
                # Fetch historical stats if ID exists
                h_win_rate, j_win_rate, t_win_rate = 0.0, 0.0, 0.0
                days_since = 30.0
                past_s1f = 14.0
                
                if horse_id is not None:
                    hist_h = all_df[all_df['horse_id'] == horse_id]
                    if len(hist_h) > 0:
                        h_win_rate = hist_h.iloc[-1]['horse_win_rate']
                        days_since = (pd.Timestamp.today() - hist_h.iloc[-1]['race_date']).days
                        past_s1f = hist_h.iloc[-1]['past_avg_s1f_time']
                
                if jockey_id is not None:
                    hist_j = all_df[all_df['jockey_id'] == jockey_id]
                    if len(hist_j) > 0:
                        j_win_rate = hist_j.iloc[-1]['jockey_win_rate']
                        
                if trainer_id is not None:
                    hist_t = all_df[all_df['trainer_id'] == trainer_id]
                    if len(hist_t) > 0:
                        t_win_rate = hist_t.iloc[-1]['trainer_win_rate']
                
                # Default unknown categorical IDs to 0
                horse_id = horse_id if horse_id else 0
                jockey_id = jockey_id if jockey_id else 0
                trainer_id = trainer_id if trainer_id else 0
                
                sex_map = {"수": "M", "암": "F", "거": "G"}
                
                pred_data.append({
                    "horse_name": entry['horse_name'],
                    "horse_no": entry['horse_no'],
                    "jockey_id": jockey_id,
                    "trainer_id": trainer_id,
                    "distance_m": 1200, # mock distance
                    "field_size": len(entries),
                    "carry_weight_kg": entry['weight'],
                    "body_weight_kg": 500.0, # mock
                    "morning_odds": entry['odds_win'],
                    "horse_age": entry['age'] if entry['age'] else 3,
                    "horse_sex": sex_map.get(entry['sex'], "M"),
                    "track": track_name,
                    "track_condition": "DRY",
                    "days_since_last_race": days_since,
                    "horse_win_rate": h_win_rate,
                    "jockey_win_rate": j_win_rate,
                    "trainer_win_rate": t_win_rate,
                    "sire_win_rate": 0.0,
                    "past_avg_s1f_time": past_s1f
                })
                
            pred_df = pd.DataFrame(pred_data)
            pred_df['horse_sex'] = pred_df['horse_sex'].astype('category')
            pred_df['track'] = pred_df['track'].astype('category')
            pred_df['track_condition'] = pred_df['track_condition'].astype('category')
            
            # Predict
            raw_scores = model.predict(pred_df[features])
            probs = softmax(raw_scores)
            
            pred_df['win_prob'] = probs
            
            # Sort by win prob
            sorted_pred = pred_df.sort_values(by='win_prob', ascending=False).reset_index(drop=True)
            
            print(f"Top 3 Predictions for Race {rc_no}:")
            for i in range(min(3, len(sorted_pred))):
                print(f"  {i+1}등 예상: 마번 {sorted_pred.iloc[i]['horse_no']} - {sorted_pred.iloc[i]['horse_name']} (우승 확률: {sorted_pred.iloc[i]['win_prob']*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(predict_today_races())
