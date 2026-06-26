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

def evaluate_last_week():
    # 1. Load data
    print("Loading feature matrix...")
    train_df, val_df, test_df, features, target = load_dataset("test_dod.db")
    
    # Recombine to easily filter by exact dates
    df = pd.concat([train_df, val_df, test_df])
    
    # 2. Split data: train on everything before last week
    start_date = datetime.date(2026, 6, 19)
    end_date = datetime.date(2026, 6, 21)
    
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    
    train_df = df[df['race_date'] < start_ts]
    test_df = df[(df['race_date'] >= start_ts) & (df['race_date'] <= end_ts)]
    
    print(f"Training on {len(train_df)} rows. Testing on {len(test_df)} rows ({start_date} to {end_date}).")
    
    if len(test_df) == 0:
        print("No races found for last week.")
        return
    
    # 3. Train model
    model = train_lgbm(train_df, train_df.iloc[:100], features, target)
    
    # 4. Evaluate on last week's races
    print("\n--- Last Week's Races Simulation ---")
    test_df = test_df.copy()
    test_df['pred_raw'] = model.predict(test_df[features])
    
    bankroll = 1000000.0
    win_hits = 0
    total_races = 0
    
    if 'final_odds' not in test_df.columns:
        test_df['final_odds'] = test_df['morning_odds']
        
    for race_id, group in test_df.groupby('race_id'):
        total_races += 1
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
            print(f"{race_date} | {track} R{race_id} | Bet {bet_amount:,.0f} KRW on Horse {horse_id} (Prob {probs[best_idx]*100:.1f}%, Odds {odds[best_idx]:.1f}) | {res_str} | Bankroll: {bankroll:,.0f} KRW")
        else:
            print(f"{race_date} | {track} R{race_id} | No positive expectation bets found. | Bankroll: {bankroll:,.0f} KRW")
            
    if total_races > 0:
        print(f"\nSummary: Hit Rate: {win_hits}/{total_races} ({(win_hits/total_races)*100:.1f}%) | Final Bankroll: {bankroll:,.0f} KRW")
    else:
        print("No races tested.")

if __name__ == "__main__":
    evaluate_last_week()
