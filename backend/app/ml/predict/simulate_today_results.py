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

async def simulate_today():
    meet = "3"
    track_name = "BUSAN"
    today_str = "20260626"
    
    print("Loading historical data to compute features and train model...")
    train_df, val_df, test_df, features, target = load_dataset("test_dod.db")
    all_df = pd.concat([train_df, val_df, test_df])
    model = train_lgbm(all_df, all_df.iloc[:100], features, target)
    
    # 1. Get today's ACTUAL results
    print(f"Fetching actual results for {today_str} at {track_name}...")
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
        print("No actual results found yet for today.")
        return
        
    races_today = target_date_info['races']
    print(f"Found {len(races_today)} races completed today.")
    
    total_bet = 0
    total_payout_win = 0
    total_payout_place = 0
    
    bet_amount = 10000  # 10,000 KRW
    
    async with async_session_factory() as session:
        for rc_no in races_today:
            print(f"\n--- {track_name} Race {rc_no} ---")
            
            # Fetch Actual Results
            res_results = requests.post(
                "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
                headers={"User-Agent": "Mozilla/5.0"},
                data={"meet": meet, "realRcDate": today_str, "realRcNo": str(rc_no)},
                timeout=10
            )
            res_results.encoding = 'euc-kr'
            actual_results = KRALiveParser.parse_race_detail(res_results.text)
            
            if not actual_results:
                print("Could not parse actual results.")
                continue
                
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
            top_pick_no = sorted_pred.iloc[0]['horse_no']
            top_pick_name = sorted_pred.iloc[0]['horse_name']
            
            print(f"AI 1등 예상: 마번 {top_pick_no} ({top_pick_name})")
            
            # Find actual result for this horse
            actual_horse = next((h for h in actual_results if h['horse_no'] == top_pick_no), None)
            
            if actual_horse:
                rank = actual_horse['rank']
                odds_win = actual_horse['odds_win']
                odds_place = actual_horse['odds_place']
                print(f"-> 실제 도착 순위: {rank}등 (단승식 배당: {odds_win} / 연승식 배당: {odds_place})")
                
                # Bet on Win (단승식)
                total_bet += bet_amount
                if rank == 1:
                    total_payout_win += bet_amount * odds_win
                    print(f"  [단승식] 적중! 환급금: {bet_amount * odds_win:,.0f}원")
                else:
                    print(f"  [단승식] 미적중 (손실: 10,000원)")
                    
                # Bet on Place (연승식 - 3등 이내)
                total_bet += bet_amount
                if rank <= 3:
                    total_payout_place += bet_amount * odds_place
                    print(f"  [연승식] 적중! 환급금: {bet_amount * odds_place:,.0f}원")
                else:
                    print(f"  [연승식] 미적중 (손실: 10,000원)")
            else:
                print("-> 실제 결과에 이 말이 없습니다 (취소/제외)")
                
    print("\n==============================================")
    print("오늘의 실전 배팅 시뮬레이션 결과 (매 경주 1만원씩 배팅)")
    print("==============================================")
    print(f"단승식(1등 적중) 총 베팅금: {len(races_today) * bet_amount:,.0f}원")
    print(f"단승식 총 환급금: {total_payout_win:,.0f}원")
    print(f"단승식 순수익: {total_payout_win - (len(races_today) * bet_amount):,.0f}원\n")
    
    print(f"연승식(3등내 적중) 총 베팅금: {len(races_today) * bet_amount:,.0f}원")
    print(f"연승식 총 환급금: {total_payout_place:,.0f}원")
    print(f"연승식 순수익: {total_payout_place - (len(races_today) * bet_amount):,.0f}원")
    print("==============================================")
    print(f"최종 합산 순수익: {(total_payout_win + total_payout_place) - (total_bet):,.0f}원")

if __name__ == "__main__":
    asyncio.run(simulate_today())
