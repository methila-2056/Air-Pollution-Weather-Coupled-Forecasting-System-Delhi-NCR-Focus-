"""Unit tests for the SIH26082 coupling-engine features (ml/features/coupling_engine.py).

The engine must be deterministic, pure, and honestly signal unavailable inputs
rather than inventing values.
"""


from ml.features.coupling_engine import (
    CouplingInputs,
    band_label,
    compute_coupling_features,
)

FEATURES = {
    "dispersion_potential",
    "accumulation_potential",
    "inversion_trapping_potential",
    "pollution_stagnation_index",
    "aerosol_accumulation_potential",
    "fire_transport_influence",
    "regional_transport_potential",
    "ozone_photochemical_potential",
    "meteorology_pollution_interaction",
}


def _full_inputs() -> CouplingInputs:
    return CouplingInputs(
        temperature_c=30.0,
        humidity_pct=55.0,
        pressure_hpa=1004.0,
        wind_speed_mps=5.0,
        wind_direction_deg=210.0,
        pbl_height_m=900.0,
        pm25_ugm3=180.0,
        pm10_ugm3=260.0,
        no2_ugm3=80.0,
        o3_ugm3=45.0,
        inversion_detected=True,
        inversion_strength=0.2,
        inversion_category="weak",
        fire_count=120,
        upwind_fire_count=30,
        nearest_fire_distance_km=60.0,
        fire_impact_score=0.5,
        wind_alignment_pct=60.0,
        transport_time_hours=6.0,
    )


class TestEngineContract:
    def test_returns_all_nine_named_features(self):
        result = compute_coupling_features(_full_inputs())
        assert set(result["features"]) == FEATURES

    def test_each_feature_has_value_available_basis(self):
        result = compute_coupling_features(_full_inputs())
        for name in FEATURES:
            f = result["features"][name]
            assert set(f) == {"value", "available", "basis"}
            assert isinstance(f["basis"], str) and f["basis"]

    def test_includes_inputs_and_methodology(self):
        result = compute_coupling_features(_full_inputs())
        assert "inputs" in result and "methodology" in result

    def test_deterministic(self):
        a = compute_coupling_features(_full_inputs())
        b = compute_coupling_features(_full_inputs())
        assert a == b

    def test_values_all_in_unit_interval_when_available(self):
        result = compute_coupling_features(_full_inputs())
        for name in FEATURES:
            v = result["features"][name]["value"]
            assert v is None or 0.0 <= v <= 1.0, name


class TestMissingDataHonesty:
    def test_all_missing_inputs_yield_none_values(self):
        result = compute_coupling_features(CouplingInputs())
        for name in FEATURES:
            assert result["features"][name]["value"] is None, name
            assert result["features"][name]["available"] is False

    def test_missing_pm25_never_invents_aerosol_feature(self):
        """The observed PM2.5 load is a real input; without it the feature must be null."""
        inputs = CouplingInputs(pm25_ugm3=None, wind_speed_mps=7.0, pbl_height_m=1500.0)
        result = compute_coupling_features(inputs)
        aero = result["features"]["aerosol_accumulation_potential"]
        assert aero["value"] is None
        assert "never overwritten" in aero["basis"]

    def test_basis_describes_missing_input(self):
        result = compute_coupling_features(CouplingInputs())
        assert "requires" in result["features"]["dispersion_potential"]["basis"]


class TestPhysicalBehavior:
    def test_good_ventilation_gives_high_dispersion(self):
        r = compute_coupling_features(
            CouplingInputs(wind_speed_mps=7.0, pbl_height_m=1500.0, inversion_strength=0.0)
        )
        assert r["features"]["dispersion_potential"]["value"] >= 0.9
        assert r["features"]["accumulation_potential"]["value"] <= 0.1

    def test_inversion_trapping_increases_with_inversion_strength(self):
        weak = compute_coupling_features(
            CouplingInputs(inversion_strength=0.0, pbl_height_m=1500.0)
        )["features"]["inversion_trapping_potential"]["value"]
        strong = compute_coupling_features(
            CouplingInputs(inversion_strength=1.0, pbl_height_m=1500.0)
        )["features"]["inversion_trapping_potential"]["value"]
        assert strong > weak

    def test_stagnation_highest_when_calm_shallow_inverted(self):
        stagnant = compute_coupling_features(
            CouplingInputs(wind_speed_mps=0.5, pbl_height_m=150.0, inversion_strength=0.9)
        )["features"]["pollution_stagnation_index"]["value"]
        ventilated = compute_coupling_features(
            CouplingInputs(wind_speed_mps=9.0, pbl_height_m=1800.0, inversion_strength=0.0)
        )["features"]["pollution_stagnation_index"]["value"]
        assert stagnant > 0.6
        assert ventilated < 0.3

    def test_fire_influence_stronger_with_near_upwind_high_impact_fires(self):
        near = compute_coupling_features(
            CouplingInputs(
                fire_count=300, upwind_fire_count=40, nearest_fire_distance_km=30.0,
                fire_impact_score=0.9, wind_alignment_pct=90.0,
            )
        )["features"]["fire_transport_influence"]["value"]
        far = compute_coupling_features(
            CouplingInputs(
                fire_count=2, upwind_fire_count=0, nearest_fire_distance_km=480.0,
                fire_impact_score=0.05, wind_alignment_pct=5.0,
            )
        )["features"]["fire_transport_influence"]["value"]
        assert near > far

    def test_ozone_photochemical_potential_rises_with_heat_and_warm_stagnation(self):
        hot = compute_coupling_features(
            CouplingInputs(temperature_c=40.0, wind_speed_mps=1.0, no2_ugm3=90.0)
        )["features"]["ozone_photochemical_potential"]["value"]
        cool = compute_coupling_features(
            CouplingInputs(temperature_c=15.0, wind_speed_mps=8.0, no2_ugm3=10.0)
        )["features"]["ozone_photochemical_potential"]["value"]
        assert hot > cool

    def test_feedback_surrogate_between_component_bounds(self):
        result = compute_coupling_features(_full_inputs())
        interactions = [
            "accumulation_potential",
            "pollution_stagnation_index",
            "ozone_photochemical_potential",
            "fire_transport_influence",
        ]
        comps = [result["features"][k]["value"] for k in interactions]
        mpi = result["features"]["meteorology_pollution_interaction"]["value"]
        assert mpi is not None
        assert min(comps) <= mpi <= max(comps)


class TestBandLabel:
    def test_bands(self):
        assert band_label(0.1) == "Low"
        assert band_label(0.5) == "Moderate"
        assert band_label(0.9) == "High"
        assert band_label(None) is None
