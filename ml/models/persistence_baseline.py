"""Persistence baseline model for AeroCast-NCR.

The persistence baseline stores the last known observed value and uses it as
the prediction for any forecast horizon. It is the simplest forecasting model
that can be built, and any useful ML model should outperform it.
"""

from typing import Union

import numpy as np

from ..evaluation.metrics import compute_mae, compute_r2, compute_rmse


class PersistenceBaseline:
    """Persistence forecast: prediction equals the last observed value.

    This model serves as the minimal baseline to beat. Regardless of the
    requested horizon, the predicted value for every sample is simply the most
    recently observed value of the target variable.

    Attributes:
        last_value: The last observed value stored during fit.
        n_features_: Number of input features seen during fit.
    """

    def __init__(self, horizon: int = 1):
        """Initialize the persistence baseline.

        Args:
            horizon: Forecast horizon in hours (informational; predictions
                do not change with horizon since it is a naive baseline).
        """
        self.horizon = horizon
        self.last_value: Union[float, None] = None
        self.n_features_: Union[int, None] = None

    def fit(self, X, y):
        """Store the last observed value as the persistent prediction.

        Args:
            X: Feature matrix (shape n_samples x n_features). Only used to
                record the feature count.
            y: Target values; the last element becomes the prediction for
                any future horizon.

        Returns:
            self
        """
        y = np.asarray(y, dtype=float).ravel()
        if y.size == 0:
            raise ValueError("y must contain at least one sample to fit a persistence baseline")

        self.last_value = float(y[-1])
        X = np.asarray(X)
        self.n_features_ = X.shape[1] if X.ndim == 2 else 1
        return self

    def predict(self, X):
        """Return the last observed value for every sample.

        Args:
            X: Feature matrix; any shape is accepted. Each row is assigned
                the stored last value as its prediction.

        Returns:
            np.ndarray of the stored last value broadcast to len(X).
        """
        X = np.asarray(X)
        n_samples = X.shape[0] if X.ndim == 2 else (X.shape[0] if X.ndim == 1 else 1)
        if self.last_value is None:
            raise RuntimeError("PersistenceBaseline must be fit before predict")
        return np.full(n_samples, self.last_value, dtype=float)

    def evaluate(self, X, y):
        """Compute MAE, RMSE and R2 against true values.

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
        """Save the fitted model state to a file (joblib).

        Args:
            path: Destination file path for the serialized model.
        """
        import joblib

        joblib.dump(
            {
                "horizon": self.horizon,
                "last_value": self.last_value,
                "n_features_": self.n_features_,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "PersistenceBaseline":
        """Load a fitted PersistenceBaseline from a file.

        Args:
            path: Path to a serialized persistence baseline.

        Returns:
            A new PersistenceBaseline instance with the stored state.
        """
        import joblib

        state = joblib.load(path)
        obj = cls(horizon=state["horizon"])
        obj.last_value = state["last_value"]
        obj.n_features_ = state["n_features_"]
        return obj
