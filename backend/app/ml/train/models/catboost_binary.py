import pandas as pd
import numpy as np


class ModelShim:
    def __init__(self, m, cat_cols):
        self.m = m
        self.cat_cols = cat_cols
        self.calibrator = None

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X.copy()
        for c in self.cat_cols:
            if c in X.columns:
                X[c] = X[c].astype(str)
        return self.m.predict(X)

def train_catboost(train_df: pd.DataFrame, val_df: pd.DataFrame,
                   features: list, target: str):
    """
    Train a CatBoostRanker (YetiRank listwise) on race data.
    group_id is derived from race_id — the model learns to rank horses within each race.
    Returns a ModelShim with .predict(X) -> np.ndarray interface.
    """
    from catboost import CatBoostRanker, Pool

    cat_features = ['jockey_id', 'trainer_id', 'horse_sex', 'track', 'track_condition', 'weather', 'surface', 'grade']
    # Only include cat features that are actually in the feature list
    cat_features_in_use = [c for c in cat_features if c in features]

    # Work on copies to avoid mutating caller's dataframes
    train_df = train_df.copy()
    val_df = val_df.copy()

    # Sort by race to ensure group_id is contiguous (required by CatBoostRanker)
    train_df = train_df.sort_values(by=['race_id'])
    val_df = val_df.sort_values(by=['race_id'])

    # Convert categorical features to str for CatBoost
    for c in cat_features_in_use:
        train_df[c] = train_df[c].astype(str)
        val_df[c] = val_df[c].astype(str)

    # Build integer group IDs (must be sorted/contiguous for CatBoostRanker)
    train_df['group_id'] = train_df['race_id'].astype('category').cat.codes
    val_df['group_id'] = val_df['race_id'].astype('category').cat.codes

    train_pool = Pool(
        data=train_df[features],
        label=train_df[target],
        group_id=train_df['group_id'],
        cat_features=cat_features_in_use,
    )
    val_pool = Pool(
        data=val_df[features],
        label=val_df[target],
        group_id=val_df['group_id'],
        cat_features=cat_features_in_use,
    )

    model = CatBoostRanker(
        iterations=500,
        learning_rate=0.05,
        depth=6,
        loss_function='YetiRank',
        eval_metric='NDCG',
        random_seed=42,
        od_type='Iter',
        od_wait=50,
        verbose=0,  # suppress output in production
    )
    model.fit(train_pool, eval_set=val_pool)

    return ModelShim(model, cat_features_in_use)
