import asyncio
import datetime
import requests
import warnings
import pandas as pd
from scipy.special import softmax
from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.crawl import Horse, Jockey, Trainer
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.train.dataset import load_dataset
from app.ml.train.models.lgbm_binary import train_lgbm

warnings.filterwarnings('ignore')

async def check_trio():
    meet = "3"
    track_name = "BUSAN"
    today_str = "20260626"
    
    print("Loading historical data to compute features and train model...")
    train_df, val_df, test_df, features, target = load_dataset("test_dod.db")
    all_df = pd.concat([train_df, val_df, test_df])
    model = train_lgbm(all_df, all_df.iloc[:100], features, target)
    
    res_list = requests.post(
        "https://race.kra.co.kr/raceScore/ScoretableScoreList.do",
        headers={"User-Agent": "Mozilla/5.0"},
        data={"Act": "04", "Sub": "1", "meet": meet, "rcDate": today_str},
        timeout=10
    )
    res_list.encoding = 'euc-kr'
    live_races = KRALiveParser.parse_chulma_list(res_list.text)
    
    target_date_info = next((r for r in live_races if r['date'] == today_str), None)
    if not target_date_info or not target_date_info['races']:
        return
        
    races_today = target_date_info['races']
    
    async with async_session_factory() as session:
        for rc_no in races_today:
            
            # Fetch Actual Results
            res_results = requests.post(
                "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
                headers={"User-Agent": "Mozilla/5.0"},
                data={"meet": meet, "realRcDate": today_str, "realRcNo": str(rc_no)},
                timeout=10
            )
            res_results.encoding = 'euc-kr'
            actual_results = KRALiveParser.parse_race_detail(res_results.text)
            
            # Get actual Top 3
            actual_top3 = [h['horse_no'] for h in sorted(actual_results, key=lambda x: x['rank']) if h['rank'] <= 3]
            
            # Fetch Upcoming Entries (for prediction)
            res_entries = requests.post(
                "https://race.kra.co.kr/chulmainfo/chulmaDetailInfoChulmapyo.do",
                headers={"User-Agent": "Mozilla/5.0"},
                data={"meet": meet, "rcDate": today_str, "rcNo": str(rc_no)},
                timeout=10
            )
            res_entries.encoding = 'euc-kr'
            entries = KRALiveParser.parse_upcoming_race(res_entries.text)
            
            pred_data = []
            for entry in entries:
                stmt = select(Horse.id).filter_by(name=entry['horse_name'])
                horse_id = (await session.execute(stmt)).scalars().first()
                stmt = select(Jockey.id).filter_by(name=entry['jockey'])
                jockey_id = (await session.execute(stmt)).scalars().first()
                stmt = select(Trainer.id).filter_by(name=entry['trainer'])
                trainer_id = (await session.execute(stmt)).scalars().first()
                
                h_win_rate, j_win_rate, t_win_rate = 0.0, 0.0, 0.0
                days_since = 30.0
                past_s1f = 14.0
                
                if horse_id:
                    hist_h = all_df[all_df['horse_id'] == horse_id]
                    if len(hist_h) > 0:
                        h_win_rate = hist_h.iloc[-1]['horse_win_rate']
                        days_since = (pd.Timestamp.today() - hist_h.iloc[-1]['race_date']).days
                        past_s1f = hist_h.iloc[-1]['past_avg_s1f_time']
                if jockey_id:
                    hist_j = all_df[all_df['jockey_id'] == jockey_id]
                    if len(hist_j) > 0:
                        j_win_rate = hist_j.iloc[-1]['jockey_win_rate']
                if trainer_id:
                    hist_t = all_df[all_df['trainer_id'] == trainer_id]
                    if len(hist_t) > 0:
                        t_win_rate = hist_t.iloc[-1]['trainer_win_rate']
                        
                sex_map = {"수": "M", "암": "F", "거": "G"}
                pred_data.append({
                    "horse_name": entry['horse_name'],
                    "horse_no": entry['horse_no'],
                    "jockey_id": jockey_id if jockey_id else 0,
                    "trainer_id": trainer_id if trainer_id else 0,
                    "distance_m": 1200,
                    "field_size": len(entries),
                    "carry_weight_kg": entry['weight'],
                    "body_weight_kg": 500.0,
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
            
            raw_scores = model.predict(pred_df[features])
            pred_df['win_prob'] = softmax(raw_scores)
            
            sorted_pred = pred_df.sort_values(by='win_prob', ascending=False).reset_index(drop=True)
            pred_top3 = sorted_pred.iloc[:3]['horse_no'].tolist()
            
            is_trio_hit = set(pred_top3) == set(actual_top3)
            
            print(f"--- R{rc_no} ---")
            print(f"AI 예상 1,2,3등 마번: {pred_top3}")
            print(f"실제 결과 1,2,3등 마번: {actual_top3}")
            if is_trio_hit:
                print("🎯 삼복승 적중!!!")
            else:
                matched = set(pred_top3).intersection(set(actual_top3))
                print(f"❌ 실패 (맞춘 마리 수: {len(matched)}마리 - {list(matched)})")
                
if __name__ == "__main__":
    asyncio.run(check_trio())
