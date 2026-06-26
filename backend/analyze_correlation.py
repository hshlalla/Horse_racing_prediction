import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from app.ml.train.dataset import load_dataset

# Set font for Korean
plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

def run_correlation():
    print("Loading dataset for correlation analysis...")
    train_df, val_df, test_df, features, target = load_dataset("test_dod.db")
    
    # Combine train and val for analysis
    df = pd.concat([train_df, val_df])
    
    # We want to see correlation with actual Win (finish_position == 1)
    df['is_win'] = (df['finish_position'] == 1).astype(int)
    
    # Select numerical features for correlation
    numeric_features = [
        'distance_m', 'field_size', 'carry_weight_kg', 'body_weight_kg', 'morning_odds', 
        'horse_age', 'days_since_last_race', 'horse_win_rate', 'jockey_win_rate', 
        'trainer_win_rate', 'sire_win_rate', 'past_avg_s1f_time', 'past_avg_g3f_time'
    ]
    
    analysis_df = df[numeric_features + ['is_win']].copy()
    
    # Calculate Spearman correlation (better for non-linear relationships like rank)
    corr = analysis_df.corr(method='spearman')
    
    # Plot Heatmap
    plt.figure(figsize=(12, 10))
    sns.heatmap(corr, annot=True, cmap='coolwarm', fmt=".2f", vmin=-1, vmax=1)
    plt.title("경마 피처 데이터 상관관계 히트맵 (Spearman Correlation)", fontsize=16)
    plt.tight_layout()
    
    # Save to artifacts directory
    artifact_dir = "/Users/studio/.gemini/antigravity-ide/brain/9e233ce7-2baf-47c5-b121-19b4b76849df/scratch"
    os.makedirs(artifact_dir, exist_ok=True)
    img_path = os.path.join(artifact_dir, "heatmap.png")
    plt.savefig(img_path, dpi=300)
    print(f"Heatmap saved to: {img_path}")
    
    # Print top correlations with is_win
    win_corr = corr['is_win'].sort_values(ascending=False)
    print("\n[상관관계 Top & Bottom]")
    for feat, val in win_corr.items():
        if feat != 'is_win':
            print(f"{feat:25s}: {val:.4f}")

if __name__ == "__main__":
    run_correlation()
