import pandas as pd
from app.ml.train.dataset import load_dataset
from app.ml.train.models.lgbm_binary import train_lgbm
from sklearn.metrics import log_loss, accuracy_score
import numpy as np
import os

from sklearn.metrics import mean_squared_error

from scipy.special import softmax

def evaluate_test_set(model, test_df, features):
    print("\n--- Evaluating on 2026 Test Data ---")
    categorical_features = ['jockey_id', 'trainer_id', 'horse_sex', 'track', 'track_condition']
    for c in categorical_features:
        if c in features:
            test_df[c] = test_df[c].astype('category')
            
    X_test = test_df[features]
    
    # Predict LTR scores (Higher is better)
    preds = model.predict(X_test)
    test_df['pred_score'] = preds
    
    races = test_df.groupby('race_id')
    total_races = len(races)
    
    # Starting Bankrolls
    roi_win = 1000000.0
    roi_place = 1000000.0
    
    correct_win = 0
    correct_place = 0
    
    print("\n--- Detailed Race-by-Race Predictions (Kelly Simulation) ---")
    
    for race_id, race_df in races:
        if race_df['is_win'].sum() == 0 or len(race_df) < 2:
            total_races -= 1
            continue
            
        # Softmax probabilities over the race
        race_df = race_df.copy()
        race_df['pred_prob'] = softmax(race_df['pred_score'].values)
        
        race_df = race_df.sort_values(by='pred_score', ascending=False)
        top1 = race_df.iloc[0]
        
        actual_winner = race_df[race_df['is_win'] == 1]
        actual_winner_id = int(actual_winner.iloc[0]['horse_id']) if len(actual_winner) > 0 else "None"
        race_date_str = pd.to_datetime(top1['race_date']).strftime('%Y-%m-%d') if 'race_date' in top1 else 'Unknown'
        
        # Kelly Strategy for WIN
        p_win = top1['pred_prob']
        odds_win = max(1.1, top1['morning_odds'])
        b_win = odds_win - 1.0
        q_win = 1.0 - p_win
        kelly_f_win = (p_win * b_win - q_win) / b_win if b_win > 0 else 0
        
        # Fractional Kelly (10%) to prevent ruin
        bet_frac_win = max(0, min(0.1, kelly_f_win * 0.1))
        bet_amount_win = roi_win * bet_frac_win
        roi_win -= bet_amount_win
        
        is_success = False
        if top1['finish_position'] == 1:
            roi_win += bet_amount_win * odds_win
            correct_win += 1
            is_success = True
            
        # Kelly Strategy for PLACE
        p_place = min(0.99, p_win * 2.5) # Rough approx for place prob
        odds_place = max(1.1, top1['morning_odds'] / 3.0)
        b_place = odds_place - 1.0
        q_place = 1.0 - p_place
        kelly_f_place = (p_place * b_place - q_place) / b_place if b_place > 0 else 0
        
        bet_frac_place = max(0, min(0.1, kelly_f_place * 0.1))
        bet_amount_place = roi_place * bet_frac_place
        roi_place -= bet_amount_place
        
        if top1['finish_position'] <= 3:
            roi_place += bet_amount_place * odds_place
            correct_place += 1
            
        result_str = "✅ SUCCESS" if is_success else "❌ FAIL"
        if bet_amount_win > 0:
            print(f"Race {int(race_id):<4} | Pred Win: {int(top1['horse_id']):<4} (Prob: {p_win:>6.2%}, Bet: {int(bet_amount_win):>6}원) | Actual Win: {actual_winner_id:<4} | {result_str}")
            
    win_acc = correct_win / total_races if total_races > 0 else 0
    place_acc = correct_place / total_races if total_races > 0 else 0
    
    print("\n--- Overall 2026 LTR & Kelly Test Metrics ---")
    print(f"Total 2026 Races Tested: {total_races}")
    print(f"단승(Win) Hit Rate:   {win_acc:.2%}  | Final Bankroll: {int(roi_win):,} KRW (ROI: {((roi_win - 1000000) / 1000000 * 100):.2f}%)")
    print(f"연승(Place) Hit Rate: {place_acc:.2%}  | Final Bankroll: {int(roi_place):,} KRW (ROI: {((roi_place - 1000000) / 1000000 * 100):.2f}%)")
    

def execute():
    # Fix the db path since the script might run from app/ml/cli.py context
    db_path = os.path.join(os.getcwd(), "test_dod.db")
    if not os.path.exists(db_path):
        db_path = "test_dod.db" # fallback
        
    print("Loading data...")
    train_df, val_df, test_df, features, target = load_dataset(db_path)
    
    print(f"Training Data (2021-2024): {len(train_df)} rows")
    print(f"Validation Data (2025): {len(val_df)} rows")
    print(f"Test Data (2026): {len(test_df)} rows")
    
    # Train Model
    model = train_lgbm(train_df, val_df, features, target)
    
    # Evaluate
    evaluate_test_set(model, test_df, features)
    
if __name__ == "__main__":
    execute()
