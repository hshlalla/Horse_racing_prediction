"""
가치 베팅 모델 (Approach B)

"시장이 틀린" 경우를 탐지하는 이진 분류기.
타겟: finish_position == 1 AND morning_odds > 5.0 (배당 5배 이상인데 실제로 우승)

주 랭킹 모델이 잘 맞추는 인기마와 달리, 이 모델은 시장 과소평가 말을 찾는다.
"""

import numpy as np
import pandas as pd
import lightgbm as lgb

UPSET_ODDS_THRESHOLD = 5.0  # 배당 5배 이상을 "업셋" 기준으로


class ValueModelShim:
    def __init__(self, m, cat_cols=None, cat_mappings=None, calibrator=None):
        self.m = m
        self.cat_cols = cat_cols or []
        self.cat_mappings = cat_mappings or {}
        # Optional isotonic calibrator mapping raw P(class=1) → true upset rate.
        # LGBM with scale_pos_weight produces inflated scores (median ~0.28 for a
        # ~5% base rate); calibration makes upset_probability an absolute number.
        self.calibrator = calibrator

    def _raw_proba(self, X: pd.DataFrame) -> np.ndarray:
        X = X.copy()
        for c in self.cat_cols:
            if c in X.columns:
                X[c] = pd.Categorical(X[c], categories=self.cat_mappings[c])
        # LGBMClassifier.predict() returns 0/1 class labels; predict_proba()[:,1]
        # is the actual P(class=1). Using .predict() collapsed this to a binary
        # label and made upset_probability meaningless.
        return self.m.predict_proba(X)[:, 1]

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated P(upset_win) for each horse. Shape: (n,)"""
        raw = self._raw_proba(X)
        cal = getattr(self, "calibrator", None)
        if cal is not None:
            return np.clip(cal.predict(raw), 0.0, 1.0)
        return raw


def train_value_model(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    features: list,
    odds_threshold: float = UPSET_ODDS_THRESHOLD,
) -> ValueModelShim:
    """
    이진 분류기 학습.

    타겟: 배당이 odds_threshold 이상인데 실제로 1착한 경우 → 1, 나머지 → 0

    Parameters
    ----------
    train_df, val_df : 주 모델과 동일한 데이터프레임 (finish_position, morning_odds 포함)
    features         : 주 모델과 동일한 피처 리스트
    odds_threshold   : 업셋 기준 배당 (기본 5.0배)

    Returns
    -------
    ValueModelShim — .predict_proba(X) → np.ndarray of P(upset_win)
    """
    train_df = train_df.copy()
    val_df = val_df.copy()

    # 업셋 타겟 생성
    train_df["_value_target"] = (
        (train_df["finish_position"] == 1) & (train_df["morning_odds"] > odds_threshold)
    ).astype(int)
    val_df["_value_target"] = (
        (val_df["finish_position"] == 1) & (val_df["morning_odds"] > odds_threshold)
    ).astype(int)

    pos_count = int(train_df["_value_target"].sum())
    neg_count = int((train_df["_value_target"] == 0).sum())

    if pos_count < 10:
        # 학습 데이터에 양성 케이스가 너무 적으면 스킵
        return None

    # 클래스 불균형 보정: 음성이 훨씬 많음
    scale_pos_weight = neg_count / max(pos_count, 1)

    cat_features = ["jockey_id", "trainer_id", "horse_sex", "track",
                    "track_condition", "weather", "surface", "grade"]
    cat_in_use = [c for c in cat_features if c in features]

    X_train = train_df[features].copy()
    y_train = train_df["_value_target"].values
    X_val = val_df[features].copy()
    y_val = val_df["_value_target"].values

    cat_mappings = {}
    for c in cat_in_use:
        X_train[c] = X_train[c].astype("category")
        cat_mappings[c] = X_train[c].cat.categories
        X_val[c] = pd.Categorical(X_val[c], categories=cat_mappings[c])

    model = lgb.LGBMClassifier(
        objective="binary",
        metric="auc",
        n_estimators=1000,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        verbose=-1,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=-1),
        ],
    )

    # Fit an isotonic calibrator on the val set so predict_proba returns an
    # absolute upset rate rather than the inflated scale_pos_weight score.
    calibrator = None
    try:
        from sklearn.isotonic import IsotonicRegression
        raw_val = model.predict_proba(X_val)[:, 1]
        if len(set(y_val.tolist())) == 2:
            calibrator = IsotonicRegression(out_of_bounds="clip")
            calibrator.fit(raw_val, y_val)
    except Exception:
        calibrator = None

    return ValueModelShim(model, cat_in_use, cat_mappings, calibrator=calibrator)
