import asyncio
import datetime
import warnings
warnings.filterwarnings('ignore')

from app.ml.train.dataset import load_dataset
from app.ml.train.models.lgbm_binary import train_lgbm
from scipy.special import softmax
import pandas as pd

def fractional_kelly(p_win, odds_win, fraction=0.1):
    b_win = odds_win - 1.0
    q_win = 1.0 - p_win
    if b_win <= 0:
        return 0.0
    kelly_f_win = (p_win * b_win - q_win) / b_win
    return max(0, min(0.1, kelly_f_win * fraction))

def evaluate_2026():
    # 1. Load data
    print("Loading feature matrix from SQLite (including real 2026 data)...")
    train_df, val_df, test_df, features, target = load_dataset("test_dod.db")
    
    # Recombine to easily filter by exact dates
    df = pd.concat([train_df, val_df, test_df])
    
    # 2. Split data: train on 2021-2025 (synthetic), test on 2026 (real)
    start_ts = pd.Timestamp(datetime.date(2026, 1, 1))
    
    train_df = df[df['race_date'] < start_ts]
    test_df = df[df['race_date'] >= start_ts]
    
    print(f"Training on {len(train_df)} rows (2021~2025). Testing on {len(test_df)} rows (2026 Real Data).")
    
    if len(test_df) == 0:
        print("No races found for 2026. Wait for crawler to finish.")
        return
    
    # 3. Train model
    print("Training LightGBM model...")
    model = train_lgbm(train_df, train_df.iloc[:100], features, target)
    
    # 4. Evaluate on 2026 real races
    print("\n--- 2026 Real Races Kelly Betting Simulation ---")
    test_df = test_df.copy()
    test_df['pred_raw'] = model.predict(test_df[features])
    
    bankroll = 1000000.0
    win_hits = 0
    total_bets = 0
    
    if 'final_odds' not in test_df.columns:
        test_df['final_odds'] = test_df['morning_odds']
        
    for race_id, group in test_df.groupby('race_id'):
        race_date = group['race_date'].iloc[0].strftime('%Y-%m-%d')
        track = group['track'].iloc[0]
        
        odds = group['final_odds'].values
        raw_scores = group['pred_raw'].values
        probs = softmax(raw_scores)
        
        best_idx = -1
        best_f = 0
        
        for i in range(len(probs)):
            p = probs[i]
            o = odds[i]
            f = fractional_kelly(p, o, fraction=0.1)
            if f > best_f:
                best_f = f
                best_idx = i
                
        winner_idx = group['finish_position'].values.argmin()
        
        if best_idx != -1:
            total_bets += 1
            bet_amount = bankroll * best_f
            bankroll -= bet_amount
            
            if best_idx == winner_idx:
                win_hits += 1
                payout = bet_amount * odds[best_idx]
                bankroll += payout
                res_str = f"✅ SUCCESS (Payout: {payout:,.0f} KRW)"
            else:
                res_str = f"❌ FAIL"
                
            horse_id = group.iloc[best_idx]['horse_id']
            # Only print every 10th bet or if bankroll changes drastically to avoid console spam for a whole year
            if total_bets % 10 == 0:
                print(f"{race_date} | R{race_id} | Bet {bet_amount:,.0f} KRW on H{horse_id} | {res_str} | Bankroll: {bankroll:,.0f} KRW")
            
    print(f"\nFinal Summary for 2026 Real Data:")
    print(f"Total Bets Placed: {total_bets} / {test_df['race_id'].nunique()} races")
    if total_bets > 0:
        print(f"Hit Rate: {win_hits}/{total_bets} ({(win_hits/total_bets)*100:.1f}%)")
    print(f"Starting Bankroll: 1,000,000 KRW")
    print(f"Final Bankroll: {bankroll:,.0f} KRW")
    print(f"ROI: {((bankroll - 1000000) / 1000000) * 100:.1f}%")

if __name__ == "__main__":
    evaluate_2026()
