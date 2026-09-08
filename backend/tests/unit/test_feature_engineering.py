"""Unit tests for the feature engineering pipeline."""

import numpy as np
import pandas as pd
import pytest

from ml.features.feature_engineering import (
    add_composite_features,
    add_humidity_lags,
    add_pollution_lags,
    add_pollution_rate_of_change,
    add_rolling_means,
    add_rolling_std,
    add_temperature_lags,
    add_temporal_features,
    add_wind_decomposition,
    get_feature_documentation,
    run_feature_engineering,
    standardize_column_names,
)


def _base_frame(n=30):
    ts = pd.date_range("2025-11-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "station": ["Anand Vihar"] * n,
        "pm25": np.linspace(40, 220, n),
        "pm10": np.linspace(80, 340, n),
        "o3": np.linspace(30, 90, n),
        "no2": np.linspace(40, 120, n),
        "so2": np.linspace(8, 22, n),
        "co": np.linspace(1.2, 3.0, n),
        "temperature": np.linspace(14, 28, n),
        "humidity": np.linspace(40, 80, n),
        "wind_speed": np.linspace(1, 6, n),
        "wind_direction": np.linspace(0, 360, n),
        "pbl_height": np.linspace(150, 900, n),
        "boundary_layer_height": np.linspace(150, 900, n),
    })


class TestStandardize:
    def test_renames_open_meteo_columns(self):
        out = standardize_column_names(_base_frame())
        assert "pbl_height" in out.columns
        assert "boundary_layer_height" not in out.columns


class TestTemporal:
    def test_cyclic_encodings_added(self):
        out = add_temporal_features(_base_frame())
        for col in ("hour", "day_of_week", "month", "season", "hour_sin", "hour_cos",
                    "month_sin", "month_cos", "is_weekend"):
            assert col in out.columns

    def test_hour_sin_cos_obey_unit_circle(self):
        out = add_temporal_features(_base_frame())
        assert ((out["hour_sin"] ** 2 + out["hour_cos"] ** 2) - 1).abs().max() < 1e-9


class TestLagsAndRolling:
    def test_pollution_lag_created(self):
        out = add_pollution_lags(_base_frame(), cols=["pm25"], lags=[1, 6])
        assert "pm25_lag1" in out.columns
        assert "pm25_lag6" in out.columns
        assert out.loc[1, "pm25_lag1"] == pytest.approx(_base_frame().loc[0, "pm25"])

    def test_rolling_mean_naming(self):
        out = add_rolling_means(_base_frame(), cols=["pm25"], windows=[3])
        assert "pm25_roll_mean_3h" in out.columns

    def test_rolling_std_added(self):
        out = add_rolling_std(_base_frame(), cols=["pm25"], windows=[6])
        assert "pm25_roll_std_6h" in out.columns

    def test_rate_of_change_added(self):
        out = add_pollution_rate_of_change(_base_frame())
        assert "pm25_delta_1h" in out.columns

    def test_temp_and_humidity_lags(self):
        out = add_temperature_lags(add_humidity_lags(_base_frame()), lags=[1])
        assert "temperature_lag1" in out.columns
        assert "humidity_lag1" in out.columns


class TestWindAndComposite:
    def test_wind_decomposition(self):
        out = add_wind_decomposition(_base_frame())
        assert "wind_dir_sin" in out.columns
        assert "wind_dir_cos" in out.columns

    def test_composite_features(self):
        out = add_composite_features(_base_frame())
        assert "ventilation_index" in out.columns
        assert "pm_ratio" in out.columns
        assert "temp_humidity_index" in out.columns


class TestPipeline:
    def test_run_feature_engineering_end_to_end(self, tmp_path):
        out = run_feature_engineering(df=_base_frame(n=12), output_path=tmp_path / "features.csv")
        assert out.shape[1] > _base_frame(n=12).shape[1]
        for col in ("inversion_detected", "fire_impact_score", "stability_coupling_index"):
            assert col in out.columns
        assert (tmp_path / "features.csv").exists()

    def test_feature_documentation_is_populated(self):
        doc = get_feature_documentation()
        assert "hour" in doc
        assert "stability_coupling_index" in doc
