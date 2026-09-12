"""GRU time-series regression model for AeroCast-NCR.

A stacked-GRU regressor that consumes hourly sequential windows of the same
44 engineered features used by the tabular models, and predicts the PM2.5
concentration at a fixed future horizon.

Design notes
------------
- The GRU is a *direct per-horizon* model (one network per horizon), matching
  the direct strategy of the deployed XGBoost system. It is trained on the
  same chronological train split and evaluated on the same held-out test rows.
- Input shape is (n_windows, seq_len, n_features). A window that predicts
  `pm25[t+h]` uses only rows with timestamp <= t (issued at time t), so it
  carries no future information.
- Preprocessing (imputation + standardization) is NOT done here; the caller
  supplies already-imputed, standardized numeric arrays fit on the train split
  only.

PyTorch is an optional dependency: it is imported lazily, and GRUModel raises
an informative error when the framework is absent.
"""

from __future__ import annotationsimport joblibimport numpy as npfrom ..evaluation.metrics import compute_mae, compute_r2, compute_rmsedef _require_torch():
    try:
        import torch
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PyTorch is required for GRUModel but is not installed. "
            "Install it with: pip install torch --index-url https://download.pytorch.org/whl/cpu"
        ) from exc
    return torch


class GRUModel:
    """GRU regressor wrapper with an AeroCast-NCR compatible interface.

    Attributes:
        input_size: Number of features per timestep; inferred at fit time.
        hidden_size: Hidden units per GRU layer.
        num_layers: Number of stacked GRU layers.
        dropout: Dropout between GRU layers (ignored when num_layers == 1).
        lr: AdamW learning rate.
        batch_size: Training batch size.
        max_epochs: Hard cap on training epochs.
        patience: Early-stopping patience (in epochs).
        seed: Random seed for reproducibility.
        feature_names_: Feature names captured during fit, if available.
    """

    def __init__(
        self,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.1,
        lr: float = 1e-3,
        batch_size: int = 512,
        max_epochs: int = 60,
        patience: int = 12,
        seed: int = 42,
    ):
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.lr = lr
        self.batch_size = batch_size
        self.max_epochs = max_epochs
        self.patience = patience
        self.seed = seed
        self.input_size: int | None = None
        self.net = None
        self.feature_names_ = None
        self.train_history_: list[float] = []
        self.val_history_: list[float] = []
        self.best_epoch_: int | None = None

    def _build_net(self, torch):
        class GRURegressor(torch.nn.Module):
            def __init__(self, in_size, hidden, layers, drop):
                super().__init__()
                self.gru = torch.nn.GRU(
                    in_size,
                    hidden,
                    num_layers=layers,
                    dropout=drop if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.head = torch.nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.gru(x)
                return self.head(out[:, -1, :])

        return GRURegressor(self.input_size, self.hidden_size, self.num_layers, self.dropout)

    def fit(self, X, y, X_val=None, y_val=None) -> GRUModel:
        """Train the GRU with optional early stopping on a validation window.

        Args:
            X: (n_train, seq_len, n_features) float array.
            y: (n_train,) target values.
            X_val: Optional (n_val, seq_len, n_features) validation array.
            y_val: Optional (n_val,) validation targets.

        Returns:
            self
        """
        torch = _require_torch()
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.float32).reshape(-1, 1)
        self.input_size = X.shape[2]

        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self.seed)

        self.net = self._build_net(torch)
        optimizer = torch.optim.AdamW(self.net.parameters(), lr=self.lr)
        loss_fn = torch.nn.MSELoss()

        train_ds = torch.utils.data.TensorDataset(
            torch.from_numpy(X), torch.from_numpy(y)
        )
        train_loader = torch.utils.data.DataLoader(
            train_ds, batch_size=self.batch_size, shuffle=True
        )

        has_val = X_val is not None and y_val is not None
        if has_val:
            X_val = np.asarray(X_val, dtype=np.float32)
            y_val = np.asarray(y_val, dtype=np.float32).reshape(-1, 1)
            val_ds = torch.utils.data.TensorDataset(
                torch.from_numpy(X_val), torch.from_numpy(y_val)
            )
            val_loader = torch.utils.data.DataLoader(
                val_ds, batch_size=self.batch_size, shuffle=False
            )

        self.train_history_ = []
        self.val_history_ = []
        best = float("inf")
        best_state = None
        patience_left = self.patience
        self.best_epoch_ = None

        for epoch in range(self.max_epochs):
            self.net.train()
            epoch_loss = 0.0
            n = 0
            for xb, yb in train_loader:
                optimizer.zero_grad()
                loss = loss_fn(self.net(xb), yb)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item() * xb.size(0)
                n += xb.size(0)
            train_mse = epoch_loss / max(n, 1)
            self.train_history_.append(train_mse)

            if has_val:
                val_mse = self._eval_mse(torch, loss_fn, val_loader)
                self.val_history_.append(val_mse)
                monitor = val_mse
            else:
                monitor = train_mse

            if monitor < best - 1e-9:
                best = monitor
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
                self.best_epoch_ = epoch + 1
                patience_left = self.patience
            else:
                patience_left -= 1
                if patience_left <= 0:
                    if best_state is not None:
                        self.net.load_state_dict(best_state)
                    break

        if best_state is not None:
            self.net.load_state_dict(best_state)
        self.net.eval()
        return self

    def _eval_mse(self, torch, loss_fn, loader) -> float:
        self.net.eval()
        total = 0.0
        n = 0
        with torch.no_grad():
            for xb, yb in loader:
                loss = loss_fn(self.net(xb), yb)
                total += loss.item() * xb.size(0)
                n += xb.size(0)
        return total / max(n, 1)

    def predict(self, X) -> np.ndarray:
        """Predict targets for sequential samples.

        Args:
            X: (n, seq_len, n_features) float array.

        Returns:
            np.ndarray of shape (n,).
        """
        if self.net is None:
            raise RuntimeError("GRUModel.predict called before fit()")
        torch = _require_torch()
        X = np.asarray(X, dtype=np.float32)
        if X.ndim != 3:
            raise ValueError(f"predict expected 3D input (n, seq_len, n_features), got {X.shape}")

        loader = torch.utils.data.DataLoader(
            torch.utils.data.TensorDataset(torch.from_numpy(X)),
            batch_size=self.batch_size,
            shuffle=False,
        )
        self.net.eval()
        preds = []
        with torch.no_grad():
            for (xb,) in loader:
                preds.append(self.net(xb).numpy().ravel())
        if not preds:
            return np.array([], dtype=np.float32)
        return np.concatenate(preds)

    def evaluate(self, X, y) -> dict:
        """Compute MAE, RMSE and R2 on a sequential dataset."""
        y_true = np.asarray(y, dtype=float).ravel()
        y_pred = self.predict(X)
        return {
            "mae": compute_mae(y_true, y_pred),
            "rmse": compute_rmse(y_true, y_pred),
            "r2": compute_r2(y_true, y_pred),
        }

    def save(self, path: str) -> None:
        """Serialize the fitted model (weights + config) via joblib."""
        if self.net is None:
            raise RuntimeError("GRUModel.save requires a fitted model")
        payload = {
            "class": "GRUModel",
            "config": {
                "input_size": self.input_size,
                "hidden_size": self.hidden_size,
                "num_layers": self.num_layers,
                "dropout": self.dropout,
                "lr": self.lr,
                "batch_size": self.batch_size,
                "max_epochs": self.max_epochs,
                "patience": self.patience,
                "seed": self.seed,
                "best_epoch": self.best_epoch_,
                "feature_names": self.feature_names_,
            },
            "state_dict": {k: v.numpy() for k, v in self.net.state_dict().items()},
        }
        joblib.dump(payload, path)

    @classmethod
    def load(cls, path: str) -> GRUModel:
        """Load a fitted GRUModel from disk."""
        torch = _require_torch()
        payload = joblib.load(path)
        cfg = payload["config"]
        obj = cls(
            hidden_size=cfg["hidden_size"],
            num_layers=cfg["num_layers"],
            dropout=cfg["dropout"],
            lr=cfg["lr"],
            batch_size=cfg["batch_size"],
            max_epochs=cfg["max_epochs"],
            patience=cfg["patience"],
            seed=cfg["seed"],
        )
        obj.input_size = cfg["input_size"]
        obj.feature_names_ = cfg.get("feature_names")
        net = obj._build_net(torch)
        state = {k: torch.from_numpy(v) for k, v in payload["state_dict"].items()}
        net.load_state_dict(state)
        net.eval()
        obj.net = net
        return obj
