import lightgbm as lgb
import numpy as np
import pandas as pd


class ModelShim:
    def __init__(self, m, cat_cols=None, cat_mappings=None):
        self.m = m
        self.cat_cols = cat_cols or []
        self.cat_mappings = cat_mappings or {}  # col -> pd.Index of categories
        self.calibrator = None  # attached by training pipeline after calibration fit

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X.copy()
        for c in self.cat_cols:
            if c in X.columns:
                X[c] = pd.Categorical(X[c], categories=self.cat_mappings[c])
        return self.m.predict(X)


def train_lgbm(train_df: pd.DataFrame, val_df: pd.DataFrame,
               features: list, target: str) -> ModelShim:
    """
    Train a LGBMRanker (LambdaRank) on race data.
    group_id is race_id — the model learns to rank horses within each race.
    Returns a ModelShim with .predict(X) -> np.ndarray of ranking scores.
    """
    # Sort by race so groups are contiguous
    train_df = train_df.sort_values("race_id").copy()
    val_df = val_df.sort_values("race_id").copy()

    cat_features = ["jockey_id", "trainer_id", "horse_sex", "track",
                    "track_condition", "weather"]
    cat_in_use = [c for c in cat_features if c in features]

    X_train = train_df[features].copy()
    y_train = train_df[target].values
    # group = number of horses per race, in race order
    train_groups = (
        train_df.groupby("race_id", sort=False)["race_id"].count().values
    )

    X_val = val_df[features].copy()
    y_val = val_df[target].values
    val_groups = (
        val_df.groupby("race_id", sort=False)["race_id"].count().values
    )

    # Convert categoricals and capture the training categories for later prediction
    cat_mappings = {}
    for c in cat_in_use:
        X_train[c] = X_train[c].astype("category")
        cat_mappings[c] = X_train[c].cat.categories
        # val must use the same category set as train
        X_val[c] = pd.Categorical(X_val[c], categories=cat_mappings[c])

    model = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=5,
        random_state=42,
        verbose=-1,
    )
    model.fit(
        X_train, y_train,
        group=train_groups,
        eval_set=[(X_val, y_val)],
        eval_group=[val_groups],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=-1),
        ],
    )
    return ModelShim(model, cat_in_use, cat_mappings)
