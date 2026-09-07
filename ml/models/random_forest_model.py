"""Random Forest regression model for AeroCast-NCR.

Wraps sklearn's RandomForestRegressor with sensible AeroCast defaults,
scikit-learn compatible fit/predict interface, feature importance reporting,
and save/load via joblib.
"""

from typing import List, Optional

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score

from ..evaluation.metrics import compute_mae, compute_r2, compute_rmse

# Default hyperparameters chosen for AeroCast-NCR forecasting tasks.
# - n_estimators=200: good bias/variance trade-off for AQI data volume.
# - max_depth=15: caps tree depth to reduce overfitting on noisy pollution.
# - min_samples_split=5: requires enough samples to split, adds robustness.
DEFAULT_N_ESTIMATORS = 200
DEFAULT_MAX_DEPTH = 15
DEFAULT_MIN_SAMPLES_SPLIT = 5
DEFAULT_RANDOM_STATE = 42


class RandomForestModel:
    """Random Forest regressor wrapper with AeroCast-NCR defaults.

    Attributes:
        model: The underlying sklearn RandomForestRegressor instance.
        feature_names_: Feature names captured during fit, if available.
    """

    def __init__(
        self,
        n_estimators: int = DEFAULT_N_ESTIMATORS,
        max_depth: Optional[int] = DEFAULT_MAX_DEPTH,
        min_samples_split: int = DEFAULT_MIN_SAMPLES_SPLIT,
        random_state: int = DEFAULT_RANDOM_STATE,
        n_jobs: int = -1,
        **kwargs,
    ):
        """Configures the RandomForestRegressor.

        Args:
            n_estimators: Number of trees in the forest (default 200).
            max_depth: Maximum tree depth; None grows trees fully (default 15).
            min_samples_split: Min samples required to split a node (default 5).
            random_state: Seed for reproducible results (default 42).
            n_jobs: Parallel jobs; -1 uses all cores (default -1).
            **kwargs: Additional hyperparameters passed to RandomForestRegressor.
        """
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            random_state=random_state,
            n_jobs=n_jobs,
            **kwargs,
        )

    def fit(self, X, y, sample_weight=None):
        """Train the random forest.

        Args:
            X: Feature matrix (n_samples x n_features).
            y: Target values (n_samples,).
            sample_weight: Optional per-sample weights.

        Returns:
            self
        """
        self.model.fit(X, y, sample_weight=sample_weight)
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
        return self.model.predict(X)

    def get_feature_importance(self, feature_names: Optional[List[str]] = None) -> dict:
        """Return feature importances as a name -> value mapping.

        Args:
            feature_names: Optional list of feature names. If omitted, uses
                names captured during fit if available, otherwise positions.

        Returns:
            dict mapping feature name (or index) to importance score.
        """
        names = feature_names
        if names is None and hasattr(self, "feature_names_"):
            names = list(self.feature_names_)
        if names is None:
            names = [str(i) for i in range(self.model.n_features_in_)]
        return dict(zip(names, self.model.feature_importances_))

    def cross_validate(self, X, y, cv: int = 5, scoring: str = "neg_mean_squared_error"):
        """Run k-fold cross-validation and return per-fold scores.

        Args:
            X: Feature matrix.
            y: Target values.
            cv: Number of folds (default 5).
            scoring: sklearn scoring string (default neg_mean_squared_error).

        Returns:
            np.ndarray of per-fold scores.
        """
        return cross_val_score(self.model, X, y, cv=cv, scoring=scoring, n_jobs=-1)

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
        joblib.dump(self.model, path)

    @classmethod
    def load(cls, path: str) -> "RandomForestModel":
        """Load a fitted RandomForestModel from disk.

        Args:
            path: Path to a joblib-serialized model.

        Returns:
            A RandomForestModel wrapping the loaded estimator.
        """
        obj = cls.__new__(cls)
        obj.model = joblib.load(path)
        if hasattr(obj.model, "feature_names_in_"):
            obj.feature_names_ = obj.model.feature_names_in_
        return obj
