"""Unit tests for the GRAP (Graded Response Action Plan) stage engine."""

import pytest
from app.services.grap_service import (
    GRAP_STAGES,
    assess_grap,
    get_grap_stages,
    reasonable_aqi,
    stage_from_aqi,
)


def test_stage_matrix_has_four_operative_stages_plus_stage_zero():
    stages = get_grap_stages()
    assert stages[0]["stage"] == 0
    assert [s["stage"] for s in stages] == [0, 1, 2, 3, 4]
    assert len(GRAP_STAGES) == 4


def test_stage_matrix_bands_are_contiguous_and_monotonic():
    lo = [s["aqi_range_low"] for s in GRAP_STAGES]
    assert lo == sorted(lo)
    for prev, stage in zip(GRAP_STAGES, GRAP_STAGES[1:], strict=False):
        assert stage["aqi_range_low"] == prev["aqi_range_high"] + 1
    assert GRAP_STAGES[0]["aqi_range_low"] == 201  # Stage I starts at Poor band
    assert GRAP_STAGES[-1]["aqi_range_high"] is None  # Stage IV is open-ended


@pytest.mark.parametrize("aqi,expected_stage", [
    (None, 0),
    (0, 0),
    (200, 0),
    (201, 1), (250, 1), (300, 1),
    (301, 2), (350, 2), (400, 2),
    (401, 3), (425, 3), (450, 3),
    (451, 4), (500, 4), (999, 4),
])
def test_stage_from_aqi_boundaries(aqi, expected_stage):
    assert stage_from_aqi(aqi)["stage"] == expected_stage


def test_assess_not_invoked_below_200():
    result = assess_grap(aqi=150)
    assert result["status"] == "NOT_INVOKED"
    assert result["stage"] == 0
    assert "below the Stage I trigger" in result["rationale"][0]


def test_assess_stage_i_rationale_and_measures():
    result = assess_grap(aqi=214)
    assert result["status"] == "ACTIVE"
    assert result["stage"] == 1
    assert result["title"] == "Stage I — Poor"
    assert result["measures"]
    assert "214" in result["rationale"][0]


def test_assess_stage_iv_open_ended_band():
    result = assess_grap(aqi=480)
    assert result["stage"] == 4
    assert "> 450" in result["rationale"][0]


def test_assess_high_inversion_adds_trapping_note_and_advisory():
    result = assess_grap(aqi=214, inversion_strength=0.75)
    assert result["inversion_note"] is not None
    assert "trapped" in result["inversion_note"].lower()
    assert any("extra advisory" in m.lower() for m in result["measures"])
    assert result["inversion_strength"] == 0.75


def test_assess_moderate_inversion_note():
    result = assess_grap(aqi=214, inversion_strength=0.4)
    assert "Moderate inversion" in result["inversion_note"]
    assert not any("extra advisory" in m.lower() for m in result["measures"])


def test_assess_elevated_fire_context():
    result = assess_grap(aqi=214, fire_mean_frp_mw=95.0)
    assert "stubble burning" in result["fire_note"].lower()
    assert any("mean FRP" in r for r in result["rationale"])


def test_assess_no_context_is_clean():
    result = assess_grap(aqi=214)
    assert result["inversion_note"] is None
    assert result["fire_note"] is None
    assert result["inversion_strength"] is None
    assert result["fire_mean_frp_mw"] is None


def test_assess_no_aqi_is_advisory_only():
    result = assess_grap(aqi=None)
    assert result["status"] == "NOT_INVOKED"
    assert "advisory only" in result["rationale"][0]


def test_reasonable_aqi_clamps_and_handles_nan():
    assert reasonable_aqi(None) is None
    assert reasonable_aqi(float("nan")) is None
    assert reasonable_aqi(-5) is None
    assert reasonable_aqi(150.6) == 151
    assert reasonable_aqi(9999) == 500


def test_stages_are_immutable_copies():
    a = stage_from_aqi(250)
    a["measures"] = []
    b = stage_from_aqi(250)
    assert b["measures"]
