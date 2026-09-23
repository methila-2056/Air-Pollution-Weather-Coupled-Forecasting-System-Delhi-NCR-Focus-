"""Unit tests for the CTM engine layer NOAASH SIH26082 R6.

Covers CONTROL-file rendering, the binary cdump reader (validated against a
real ARL-produced file archived in utilhysplit), honest availability gating,
and the ``run_best_engine`` fallback contract.
"""

import datetime as dt

import numpy as np
import pytest

import ml.ctm.wrfchem_adapter  # noqa: F401  (registers WRF-Chem, mirroring app wiring)
from ml.ctm.ctm_interface import CtmUnavailable, available_engines, run_best_engine
from ml.ctm.hysplit_adapter import (
    HysplitAdapter,
    build_control_text,
    cdump_to_surface,
    read_cdump,
)

DOMAIN = {"lat_min": 28.2, "lat_max": 28.9, "lon_min": 76.6, "lon_max": 77.5}


def _mk_rec(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload + len(payload).to_bytes(4, "big")


def build_synthetic_cdump(n_hours: int = 3) -> bytes:
    body = bytearray()
    body += _mk_rec(b"GFSG" + np.array([16, 1, 7, 12, 0, 1, 1], dtype=">i4").tobytes())
    body += _mk_rec(
        np.array([16, 1, 7, 12], dtype=">i4").tobytes()
        + np.array([28.65, 77.29, 50.0], dtype=">f4").tobytes()
        + np.array([0], dtype=">i4").tobytes()
    )
    body += _mk_rec(
        np.array([301, 601], dtype=">i4").tobytes()
        + np.array([0.3, 0.3, 0.0, -156.0], dtype=">f4").tobytes()
    )
    body += _mk_rec(np.array([1, 500], dtype=">i4").tobytes())
    body += _mk_rec(np.array([1], dtype=">i4").tobytes() + b"PM25")
    for hr in range(n_hours):
        t0 = np.array([16, 1, 7, 12 + hr, 0, 0], dtype=">i4")
        t1 = np.array([16, 1, 7, 13 + hr, 0, 1], dtype=">i4")
        body += _mk_rec(t0.tobytes())
        body += _mk_rec(t1.tobytes())
        pts = np.zeros(4, dtype=">i2,>i2,>f4")
        pts["f0"] = [100, 110, 120, 115]
        pts["f1"] = [50, 50, 55, 60]
        pts["f2"] = [1.0e-4, 2.0e-4, 1.5e-4, 3.0e-4]
        body += _mk_rec(
            b"PM25" + np.array([500, 4], dtype=">i4").tobytes() + pts.tobytes()
        )
    return bytes(body)


class TestControlText:
    def test_line_layout_matches_hysplit(self):
        txt = build_control_text(
            start=dt.datetime(2026, 1, 7, 12),
            duration_hours=72,
            sources=[(28.6492, 77.2918, 50.0)],
            met_files=[("C:/met", "gdas1.jan26.w1")],
            center_lat=28.55,
            center_lon=77.05,
            grid_spacing=0.02,
            lat_span=0.7,
            lon_span=0.9,
            output_dir="C:/run",
        )
        lines = txt.strip().splitlines()
        assert lines[0] == "26 01 07 12 00"
        assert lines[1] == "1"
        assert lines[2] == "28.6492 77.2918 50.0"
        assert lines[3] == "72"
        assert lines[4] == "1"  # isosigma
        assert lines[5] == "10000"
        assert lines[6] == "1"
        assert lines[7] == "C:/met/"
        assert lines[8] == "gdas1.jan26.w1"
        assert lines[9] == "1"
        assert lines[10] == "PM25"
        assert lines[13] == "00 00 00 00 00"
        assert lines[14] == "1"  # one concentration grid
        assert lines[15].startswith("28.5500 77.0500")
        assert lines[16] == "0.020000 0.020000"
        assert lines[17] == "0.7000 0.9000"
        assert lines[18] == "C:/run/"
        assert lines[19] == "cdump"

    def test_multiple_sources_and_met(self):
        txt = build_control_text(
            start=dt.datetime(2026, 5, 1, 0),
            duration_hours=24,
            sources=[(28.6, 77.2, 10.0), (28.7, 77.3, 50.0)],
            met_files=[("m1/", "a.arl"), ("m2", "b.arl")],
            center_lat=28.55,
            center_lon=77.05,
            grid_spacing=0.02,
            lat_span=0.7,
            lon_span=0.9,
            output_dir="run",
        )
        lines = txt.strip().splitlines()
        assert lines[1] == "2"
        assert lines[2] == "28.6000 77.2000 10.0"
        assert lines[3] == "28.7000 77.3000 50.0"
        assert lines[4] == "24"
        assert lines[7] == "2"
        assert lines[8] == "m1/"
        assert lines[9] == "a.arl"
        assert lines[10] == "m2/"
        assert lines[11] == "b.arl"


class TestCdumpReader:
    def test_synthetic_round_trip(self, tmp_path):
        path = tmp_path / "cdump"
        path.write_bytes(build_synthetic_cdump(n_hours=3))
        c = read_cdump(path)
        assert c.model_id == "GFSG"
        assert (c.nlat, c.nlon) == (301, 601)
        assert c.dlat == pytest.approx(0.3)
        assert c.dlon == pytest.approx(0.3)
        assert c.llcrnr_lat == 0.0
        assert c.llcrnr_lon == pytest.approx(-156.0)
        assert c.levels == [500]
        assert c.species == ["PM25"]
        assert c.sample_time_hours == 1.0
        assert len(c.records) == 3
        for rec in c.records:
            assert rec.pollutant == "PM25"
            assert rec.level == 500
            assert len(rec.conc) == 4

    def test_surface_regrid_shape(self, tmp_path):
        path = tmp_path / "cdump"
        path.write_bytes(build_synthetic_cdump(n_hours=4))
        c = read_cdump(path)
        lat = np.arange(28.2, 28.9 + 1e-9, 0.02)
        lon = np.arange(76.6, 77.5 + 1e-9, 0.02)
        times, surface = cdump_to_surface(c, lat_axis=lat, lon_axis=lon)
        assert surface.shape == (4, len(lat), len(lon))
        assert len(times) == 4
        assert times == sorted(times)
        assert np.isfinite(surface).all()

    def test_asymmetric_record_raises(self, tmp_path):
        raw = bytearray(build_synthetic_cdump())
        # corrupt the trailing length marker of the first record
        raw[36] = 0x7F
        path = tmp_path / "cdump_bad"
        path.write_bytes(bytes(raw))
        with pytest.raises(CtmUnavailable):
            read_cdump(path)

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "cdump_empty"
        path.write_bytes(b"")
        with pytest.raises(CtmUnavailable):
            read_cdump(path)


class TestHysplitAdapterGating:
    def test_unavailable_without_config(self):
        adapter = HysplitAdapter(hysplit_home="", met_dir="")
        assert not adapter.is_available()
        assert adapter.unavailable_reasons()

    def test_run_raises_when_not_configured(self):
        adapter = HysplitAdapter(hysplit_home="", met_dir="")
        with pytest.raises(CtmUnavailable):
            adapter.run(dt.datetime(2026, 1, 1, 0), 72, DOMAIN, 0.02)

    def test_unavailable_without_executable(self, tmp_path):
        met = tmp_path / "met"
        met.mkdir()
        (met / "gdas1.jan26.w1").write_bytes(b"arl")
        adapter = HysplitAdapter(hysplit_home=str(tmp_path / "hysplit"), met_dir=str(met))
        assert not adapter.is_available()
        assert any("hycs_std" in r for r in adapter.unavailable_reasons())

    def test_unavailable_without_met_files(self, tmp_path):
        home = tmp_path / "hysplit"
        (home / "exec").mkdir(parents=True)
        exe = home / "exec" / "hycs_std.exe"
        exe.write_text("#!/bin/sh\n")
        adapter = HysplitAdapter(hysplit_home=str(home), met_dir=str(tmp_path / "nomet"))
        assert not adapter.is_available()
        assert any("met" in r.lower() for r in adapter.unavailable_reasons())


class TestWrfchemSpecInterface:
    """SIH26082 method names (validate_configuration / run_forecast / get_output)
    must exist and honour the honest contract: no wrfout output -> no fake run."""

    def test_methods_exist_and_validate_reports_missing(self):
        from ml.ctm.wrfchem_adapter import WRFChemAdapter

        adapter = WRFChemAdapter(output_dir="")
        assert callable(adapter.validate_configuration)
        assert callable(adapter.run_forecast)
        assert callable(adapter.get_output)
        reasons = adapter.validate_configuration()
        assert isinstance(reasons, list)
        assert any("WRF_OUTPUT_DIR" in r for r in reasons)

    def test_run_forecast_never_invents_fields(self):
        from ml.ctm.wrfchem_adapter import WRFChemAdapter

        adapter = WRFChemAdapter(output_dir="")
        with pytest.raises(CtmUnavailable):
            adapter.run_forecast(dt.datetime(2026, 1, 1, 0), 72, DOMAIN, 0.02)

    def test_get_output_raises_when_no_genuine_output(self):
        from ml.ctm.wrfchem_adapter import WRFChemAdapter

        adapter = WRFChemAdapter(output_dir="")
        with pytest.raises(CtmUnavailable):
            adapter.get_output()
        assert not adapter.is_available()


class TestEngineRegistry:
    def test_no_genuine_engine_raises_aggregated(self):
        assert available_engines(DOMAIN, 0.02) == []
        with pytest.raises(CtmUnavailable) as exc:
            run_best_engine(dt.datetime(2026, 1, 1, 0), 72, DOMAIN, 0.02)
        msg = str(exc.value)
        assert "analytic" in msg or "falling back" in msg.lower()

    def test_embedded_hysplit_registered(self):
        from ml.ctm.ctm_interface import engine_classes

        assert [c.name for c in engine_classes()].count("HYSPLIT (NOAA)") == 1
        assert [c.name for c in engine_classes()].count("WRF-Chem") == 1


class TestDispersionCtmComposite:
    def test_composite_blends_pattern_with_base(self):
        from backend.app.services.dispersion_service import _CTM_BLEND, _composite_from_ctm

        class FakeResult:
            engine = "HYSPLIT (NOAA)"
            n_frames = 2
            data = np.array([[[10.0, 20.0], [30.0, 40.0]],
                             [[0.0, 0.0], [0.0, 40.0]]])
            times_utc = [dt.datetime(2026, 1, 7, 12), dt.datetime(2026, 1, 7, 13)]

        initial_aqi = np.full((2, 2), 100.0)
        note, frames = _composite_from_ctm(FakeResult(), initial_aqi)
        assert "HYSPLIT (NOAA) plume pattern" in note
        assert len(frames) == 2
        base = 100.0
        assert frames[0]["aqi"][0, 0] == pytest.approx(base * (1 - _CTM_BLEND))
        assert frames[0]["aqi"][1, 1] == pytest.approx(base)  # pattern max -> full blend at max
        assert frames[1]["hour_of_day"] == 13
        assert np.isfinite(frames[1]["aqi"]).all()

    def test_genuine_ctm_gate_returns_none_when_unavailable(self):
        from backend.app.services.dispersion_service import _try_genuine_ctm

        # no HYSPLIT install / WRF-Chem output in this environment -> fallback.
        assert _try_genuine_ctm(dt.datetime(2026, 1, 1, 0), 72) is None
