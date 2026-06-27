"""
SHAP-based feature importance analysis for horse racing models.

Uses TreeExplainer for LightGBM/CatBoost to:
1. Compute SHAP values for validation data
2. Rank features by mean |SHAP|
3. Identify low-importance features to drop
4. Save summary plot image for reporting
"""

import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def run_shap_analysis(model, X_val, features: list[str], output_dir: str = "models"):
    """
    Run SHAP analysis on a trained model.

    Parameters
    ----------
    model : trained model with .predict() method
    X_val : DataFrame of validation features
    features : list of feature column names
    output_dir : directory to save the SHAP summary plot

    Returns
    -------
    dict with:
        - 'importance': {feature_name: mean_abs_shap_value}
        - 'drop_candidates': list of features with < 1% total importance
        - 'plot_path': path to saved summary plot image
    """
    try:
        import shap
    except ImportError:
        logger.warning("shap not installed. Install with: pip install shap")
        return {"importance": {}, "drop_candidates": [], "plot_path": None}

    logger.info("Computing SHAP values for %d samples, %d features...", len(X_val), len(features))

    # Use TreeExplainer for tree-based models
    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_val[features])
    except Exception as e:
        logger.warning("TreeExplainer failed (%s), falling back to Explainer", e)
        try:
            explainer = shap.Explainer(model, X_val[features])
            shap_values = explainer(X_val[features]).values
        except Exception as e2:
            logger.error("SHAP analysis failed: %s", e2)
            return {"importance": {}, "drop_candidates": [], "plot_path": None}

    # If multi-class, take class 1 (win)
    if isinstance(shap_values, list):
        shap_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]

    # Compute mean absolute SHAP values
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    importance = dict(zip(features, mean_abs_shap.tolist()))

    # Sort by importance
    sorted_importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))

    # Find features contributing less than 1% of total importance
    total = sum(sorted_importance.values())
    threshold = total * 0.01
    drop_candidates = [f for f, v in sorted_importance.items() if v < threshold]

    logger.info("Top 5 features: %s", list(sorted_importance.items())[:5])
    logger.info("Drop candidates (%d): %s", len(drop_candidates), drop_candidates)

    # Save summary plot
    plot_path = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 8))
        shap.summary_plot(shap_values, X_val[features], show=False, max_display=20)
        plt.tight_layout()

        os.makedirs(output_dir, exist_ok=True)
        plot_path = str(Path(output_dir) / "shap_summary.png")
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        plt.close()
        logger.info("SHAP summary plot saved to %s", plot_path)
    except Exception as e:
        logger.warning("Could not save SHAP plot: %s", e)

    return {
        "importance": sorted_importance,
        "drop_candidates": drop_candidates,
        "plot_path": plot_path,
    }



