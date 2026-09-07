"""XGBoost regression model for AeroCast-NCR.

Wraps xgboost.XGBRegressor with AeroCast-NCR defaults, early stopping,
feature importance ranking, save/load via joblib, and optional SHAP
explainability via get_shap_values.
"""

from typing import List, Optional, Tuple, Union

import joblib
import numpy as np

from ..evaluation.metrics import compute_mae, compute_r2, compute_rmse

# Default hyperparameters chosen for AeroCast-NCR forecasting tasks.
# - n_estimators=300: enough rounds with early stopping to avoid overfit.
# - max_depth=8: moderate tree depth for tabular AQI/weather features.
# - learning_rate=0.1: standard compromise between speed and accuracy.
# - subsample=0.8: random row sampling per tree for regularization.
# - colsample_bytree=0.8: random column sampling per tree for regularization.
# - reg_alpha=0.1 / reg_lambda=1.0: L1/L2 regularization on leaf weights.
DEFAULT_N_ESTIMATORS = 300
DEFAULT_MAX_DEPTH = 8
DEFAULT_LEARNING_RATE = 0.1
DEFAULT_SUBSAMPLE = 0.8
DEFAULT_COLSAMPLE_BYTREE = 0.8
DEFAULT_REG_ALPHA = 0.1
DEFAULT_REG_LAMBDA = 1.0
DEFAULT_RANDOM_STATE = 42


class XGBoostModel:
    """XGBoost regressor wrapper with AeroCast-NCR defaults.

    Attributes:
        model: The underlying xgboost.XGBRegressor instance.
        feature_names_: Feature names captured during fit, if available.
    """

    def __init__(
        self,
        n_estimators: int = DEFAULT_N_ESTIMATORS,
        max_depth: int = DEFAULT_MAX_DEPTH,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        subsample: float = DEFAULT_SUBSAMPLE,
        colsample_bytree: float = DEFAULT_COLSAMPLE_BYTREE,
        reg_alpha: float = DEFAULT_REG_ALPHA,
        reg_lambda: float = DEFAULT_REG_LAMBDA,
        random_state: int = DEFAULT_RANDOM_STATE,
        n_jobs: int = -1,
        **kwargs,
    ):
        """Configures the XGBRegressor.

        Args:
            n_estimators: Number of boosting rounds (default 300).
            max_depth: Maximum tree depth (default 8).
            learning_rate: Learning rate / shrinkage (default 0.1).
            subsample: Row sampling ratio per tree (default 0.8).
            colsample_bytree: Column sampling ratio per tree (default 0.8).
            reg_alpha: L1 regularization on leaf weights (default 0.1).
            reg_lambda: L2 regularization on leaf weights (default 1.0).
            random_state: Seed for reproducible results (default 42).
            n_jobs: Parallel workers; -1 uses all cores (default -1).
            **kwargs: Additional hyperparameters passed to XGBRegressor.
        """
        self.model = None
        self.params = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "random_state": random_state,
            "n_jobs": n_jobs,
            "tree_method": "hist",
            **kwargs,
        }
        self.best_iteration_ = None
        self.evals_result_ = None

    def _build_model(self):
        """Instantiate the XGBRegressor from the stored params."""
        from xgboost import XGBRegressor

        return XGBRegressor(**self.params)

    def fit(
        self,
        X,
        y,
        eval_set: Optional[List[Tuple]] = None,
        early_stopping_rounds: Optional[int] = None,
        verbose: Union[bool, int, None] = False,
    ):
        """Train the XGBoost model with optional early stopping.

        Args:
            X: Feature matrix (n_samples x n_features).
            y: Target values (n_samples,).
            eval_set: Optional list of (X_val, y_val) tuples used for
                early stopping and eval logging.
            early_stopping_rounds: Stop training if eval metric fails to
                improve for this many rounds.
            verbose: Verbosity for training output.

        Returns:
            self
        """
        if early_stopping_rounds is not None:
            self.params = {**self.params, "early_stopping_rounds": early_stopping_rounds}
        model = self._build_model()
        model.fit(X, y, eval_set=eval_set, verbose=verbose)
        self.model = model
        if (early_stopping_rounds is not None or eval_set is not None) and model.best_iteration is not None:
            self.best_iteration_ = model.best_iteration
            if getattr(model, "evals_result", None) is not None:
                self.evals_result_ = model.evals_result()
        if hasattr(self.model, "feature_names_in_"):
            self.feature_names_ = self.model.feature_names_in_
        return self

    def predict(self, X):
        """Predict target values for new samples.

        Args:
            X: Feature matrix (n_samples x n_features).

        Returns:
            np.ndarray of predictions.
        """
        if self.model is None:
            raise RuntimeError("XGBoostModel must be fit before predict")
        return self.model.predict(X)

    def get_feature_importance(
        self,
        importance_type: str = "weight",
        feature_names: Optional[List[str]] = None,
    ) -> dict:
        """Return a name -> importance mapping.

        Args:
            importance_type: One of xgboost importance types:
                'weight' (default), 'gain', 'cover', 'total_gain',
                'total_cover'.
            feature_names: Optional feature names. Falls back to names
                captured during fit, then positional indices.

        Returns:
            dict mapping feature name (or index) to importance score.
        """
        if self.model is None:
            raise RuntimeError("XGBoostModel must be fit before requesting importances")

        importances = self.model.feature_importances_
        importance_type = (importance_type or "weight").lower()
        if importance_type != "weight":
            try:
                importances = self.model.get_booster().get_score(
                    importance_type=importance_type if importance_type != "total_gain" else "total_gain"
                )
                importances = np.array(
                    [importances.get(f"f{i}", 0.0) for i in range(self.model.n_features_in_)]
                )
            except Exception:
                importances = self.model.feature_importances_

        names = feature_names
        if names is None and hasattr(self, "feature_names_"):
            names = list(self.feature_names_)
        if names is None:
            names = [str(i) for i in range(self.model.n_features_in_)]
        return dict(zip(names, importances))

    def get_feature_importance_ranking(
        self,
        importance_type: str = "weight",
        n_top: Optional[int] = None,
    ) -> List[Tuple[str, float]]:
        """Return features sorted by importance, descending.

        Args:
            importance_type: Importance metric to rank by ('weight', 'gain',
                'cover', 'total_gain', 'total_cover').
            n_top: Optional limit on number of top features returned.

        Returns:
            List of (feature_name, importance) tuples ordered from most to
            least important.
        """
        importance = self.get_feature_importance(importance_type=importance_type)
        ranking = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)
        if n_top is not None:
            ranking = ranking[:n_top]
        return ranking

    def get_shap_values(self, X):
        """Return SHAP values for the given samples.

        Requires the 'shap' package to be installed.

        Args:
            X: Feature matrix (n_samples x n_features).

        Returns:
            np.ndarray of SHAP values (n_samples x n_features).
        """
        if self.model is None:
            raise RuntimeError("XGBoostModel must be fit before requesting SHAP values")
        try:
            import shap
        except ImportError:
            raise ImportError(
                "SHAP explainability requires the 'shap' package. "
                "Install it with: pip install shap"
            )
        if isinstance(X, (list, tuple)):
            X = np.asarray(X, dtype=float)
        model = getattr(self.model, "get_booster", lambda: self.model)()
        try:
            return shap.TreeExplainer(model).shap_values(X)
        except Exception:
            return shap.TreeExplainer(self.model).shap_values(X)

    def evaluate(self, X, y) -> dict:
        """Compute MAE, RMSE and R2 on a dataset.

        Args:
            X: Feature matrix.
            y: True target values.

        Returns:
            dict with keys 'mae', 'rmse', 'r2'.
        """
        y_true = np.asarray(y, dtype=float).ravel()
        y_pred = self.predict(X)
        return {
            "mae": compute_mae(y_true, y_pred),
            "rmse": compute_rmse(y_true, y_pred),
            "r2": compute_r2(y_true, y_pred),
        }

    def save(self, path: str) -> None:
        """Serialize the fitted model to disk via joblib.

        Args:
            path: Destination file path.
        """
        joblib.dump(
            {
                "params": self.params,
                "best_iteration_": self.best_iteration_,
                "evals_result_": self.evals_result_,
                "model": self.model,
                "feature_names_": getattr(self, "feature_names_", None),
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "XGBoostModel":
        """Load a fitted XGBoostModel from disk.

        Args:
            path: Path to a joblib-serialized model.

        Returns:
            A XGBoostModel wrapping the loaded estimator.
        """
        state = joblib.load(path)
        obj = cls.__new__(cls)
        obj.params = state["params"]
        obj.model = state["model"]
        obj.best_iteration_ = state.get("best_iteration_")
        obj.evals_result_ = state.get("evals_result_")
        if state.get("feature_names_"):
            obj.feature_names_ = state["feature_names_"]
        return obj