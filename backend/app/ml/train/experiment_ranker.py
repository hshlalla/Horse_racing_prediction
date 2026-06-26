import pandas as pd
from scipy.special import softmax
import warnings
warnings.filterwarnings('ignore')

from app.ml.train.dataset import load_dataset
from app.ml.train.models.lgbm_binary import train_lgbm
from catboost import CatBoostRanker, Pool

def fractional_kelly(p_win, odds_win, fraction=0.1):
    b_win = odds_win - 1.0
    q_win = 1.0 - p_win
    if b_win <= 0:
        return 0.0
    kelly_f_win = (p_win * b_win - q_win) / b_win
    return max(0, min(0.1, kelly_f_win * fraction))

def simulate_bets(test_df, model, features, model_name, is_ranker=False):
    print(f"\n--- Simulating Bets for {model_name} ---")
    df = test_df.copy()
    
    # Predict
    raw_scores = model.predict(df[features])
    df['pred_raw'] = raw_scores
    
    bankroll = 1000000.0
    total_bets = 0
    win_hits = 0
    
    if 'final_odds' not in df.columns:
        df['final_odds'] = df['morning_odds']
        
    for race_id, group in df.groupby('race_id'):
        odds = group['final_odds'].values
        raw = group['pred_raw'].values
        
        probs = softmax(raw)
        
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
                bankroll += bet_amount * odds[best_idx]
                
    roi = ((bankroll - 1000000) / 1000000) * 100
    hit_rate = (win_hits / total_bets * 100) if total_bets > 0 else 0.0
    print(f"Total Bets: {total_bets} / {df['race_id'].nunique()} races")
    print(f"Hit Rate: {win_hits}/{total_bets} ({hit_rate:.1f}%)")
    print(f"Final Bankroll: {bankroll:,.0f} KRW (ROI: {roi:.1f}%)")
    return hit_rate, roi

def run_experiment():
    print("Loading dataset...")
    train_df, val_df, test_df, features, target = load_dataset("test_dod.db")
    
    print(f"Features in use: {features}")
    
    # -----------------------------------------------------
    # Model A: Baseline Pointwise (HistGradientBoostingRegressor)
    # -----------------------------------------------------
    print("\nTraining Model A (Baseline Pointwise - HistGradientBoosting)...")
    model_a = train_lgbm(train_df, val_df, features, target)
    
    # -----------------------------------------------------
    # Model B: Challenger Listwise Ranker (CatBoost YetiRank)
    # -----------------------------------------------------
    print("\nTraining Model B (Challenger Listwise Ranker - CatBoost)...")
    
    train_df = train_df.sort_values(by=['race_date', 'race_id'])
    val_df = val_df.sort_values(by=['race_date', 'race_id'])
    
    cat_features = ['jockey_id', 'trainer_id', 'horse_sex', 'track', 'track_condition', 'weather']
    cat_features_in_use = [f for f in cat_features if f in features]
    
    # Convert cat_features to string for CatBoost
    for c in cat_features_in_use:
        train_df[c] = train_df[c].astype(str)
        val_df[c] = val_df[c].astype(str)
        test_df[c] = test_df[c].astype(str)
        
    # We need a group ID column for Ranker
    # Use race_id, but it needs to be an integer
    train_df['group_id'] = train_df['race_id'].astype('category').cat.codes
    val_df['group_id'] = val_df['race_id'].astype('category').cat.codes
    
    train_pool = Pool(data=train_df[features], label=train_df[target], group_id=train_df['group_id'], cat_features=cat_features_in_use)
    val_pool = Pool(data=val_df[features], label=val_df[target], group_id=val_df['group_id'], cat_features=cat_features_in_use)
    
    model_b = CatBoostRanker(
        iterations=500,
        learning_rate=0.05,
        depth=6,
        loss_function='YetiRank',
        eval_metric='NDCG',
        random_seed=42,
        od_type='Iter',
        od_wait=50,
        verbose=100
    )
    
    model_b.fit(train_pool, eval_set=val_pool)
    
    # -----------------------------------------------------
    # Evaluation
    # -----------------------------------------------------
    simulate_bets(test_df, model_a, features, "Model A (Baseline Pointwise)")
    simulate_bets(test_df, model_b, features, "Model B (CatBoost YetiRank)", is_ranker=True)
    
    # -----------------------------------------------------
    # Feature Importance
    # -----------------------------------------------------
    print("\n--- Feature Importance (Model B - CatBoost) ---")
    importance = model_b.get_feature_importance(train_pool)
    imp_df = pd.DataFrame({'feature': features, 'importance': importance}).sort_values('importance', ascending=False)
    
    for idx, row in imp_df.iterrows():
        print(f"{row['feature']:20s} : {row['importance']:.4f}")

    # -----------------------------------------------------
    # Ensemble & Promote
    # -----------------------------------------------------
    from app.ml.train.models.ensemble import build_ensemble, _race_log_loss
    from app.ml.train.promote import promote_if_better, compute_kelly_roi
    
    print("\n--- Building Ensemble ---")
    ensemble_model = build_ensemble([model_a, model_b], val_df, features, target)
    
    simulate_bets(test_df, ensemble_model, features, "Ensemble Model")
    
    val_ll = _race_log_loss(ensemble_model, val_df, features, target)
    roi = compute_kelly_roi(ensemble_model, val_df, features)
    
    print(f"Ensemble Val LogLoss: {val_ll:.4f}")
    print(f"Ensemble Val ROI: {roi*100:.1f}%")
    
    # Promote for BUSAN
    import os
    os.makedirs("models", exist_ok=True)
    promote_if_better("BUSAN", ensemble_model, val_ll, roi, "models/ensemble_busan.pkl")
    # Also promote for SEOUL and JEJU just in case
    promote_if_better("SEOUL", ensemble_model, val_ll, roi, "models/ensemble_seoul.pkl")
    promote_if_better("JEJU", ensemble_model, val_ll, roi, "models/ensemble_jeju.pkl")

if __name__ == "__main__":
    run_experiment()
