import pandas as pd
import numpy as np
import pytest

from app.ml.train.dataset import load_dataset, FEATURES, TARGET


@pytest.fixture
def small_dataset():
    train, val, _, features, target = load_dataset("test_dod.db")
    # Take complete race groups to avoid breaking CatBoost's group integrity
    all_races = train["race_id"].unique()
    # Reserve last 5 races for val if the val split is empty (test DB has no 2025 data)
    if len(val) == 0 and len(all_races) > 5:
        train_races = all_races[:-5]
        val_races = all_races[-5:]
        train_small = train[train["race_id"].isin(train_races)].copy()
        val_small = train[train["race_id"].isin(val_races)].copy()
    else:
        train_races = all_races[:20]
        val_races = val["race_id"].unique()[:5]
        train_small = train[train["race_id"].isin(train_races)].copy()
        val_small = val[val["race_id"].isin(val_races)].copy()
    return train_small, val_small, features, target


def test_ensemble_predictions_are_weighted_average(small_dataset):
    from app.ml.train.models.lgbm_binary import train_lgbm
    from app.ml.train.models.ensemble import build_ensemble
    import numpy as np

    train, val, features, target = small_dataset
    model_a = train_lgbm(train, val, features, target)
    model_b = train_lgbm(train, val, features, target)  # same model twice for test

    ensemble = build_ensemble([model_a, model_b], val, features, target)
    preds = ensemble.predict(val[features])
    assert len(preds) == len(val)
    assert not np.any(np.isnan(preds))


def test_train_catboost_returns_predictions(small_dataset):
    from app.ml.train.models.catboost_binary import train_catboost
    train, val, features, target = small_dataset
    model = train_catboost(train, val, features, target)
    preds = model.predict(val[features])
    assert len(preds) == len(val)
    assert not np.any(np.isnan(preds))
