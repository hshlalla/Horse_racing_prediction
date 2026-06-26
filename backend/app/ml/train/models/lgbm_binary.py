import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

class ModelShim:
    def __init__(self, m):
        self.m = m
    def predict(self, X):
        return self.m.predict(X)

def train_lgbm(train_df: pd.DataFrame, val_df: pd.DataFrame, features: list, target: str):
    print("Training Gradient Boosting Pointwise Ranker Model (Fallback for LightGBM/XGBoost)...")
    
    categorical_features = ['jockey_id', 'trainer_id', 'horse_sex', 'track', 'track_condition']
    
    # Ensure categorical types for HistGradientBoosting
    for c in categorical_features:
        if c in features:
            train_df[c] = train_df[c].astype('category')
            val_df[c] = val_df[c].astype('category')
            
    X_train = train_df[features]
    y_train = train_df[target]
    
    X_val = val_df[features]
    y_val = val_df[target]
    
    model = HistGradientBoostingRegressor(
        loss='squared_error',
        learning_rate=0.05,
        max_leaf_nodes=31,
        max_iter=1000,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=50,
        random_state=42,
        categorical_features='from_dtype',
        verbose=0
    )
    
    model.fit(X_train, y_train)
    return ModelShim(model)
