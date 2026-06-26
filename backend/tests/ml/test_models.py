import pandas as pd
import numpy as np
import pytest

from app.ml.train.dataset import load_dataset, FEATURES, TARGET


@pytest.fixture
def small_dataset():
    train, val, _, features, target = load_dataset("test_dod.db")
    return train.head(200), val.head(50), features, target


def test_train_catboost_returns_predictions(small_dataset):
    from app.ml.train.models.catboost_binary import train_catboost
    train, val, features, target = small_dataset
    model = train_catboost(train, val, features, target)
    preds = model.predict(val[features])
    assert len(preds) == len(val)
    assert not np.any(np.isnan(preds))
