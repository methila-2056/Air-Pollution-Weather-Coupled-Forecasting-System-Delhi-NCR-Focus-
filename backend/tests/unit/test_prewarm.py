"""Unit tests for the cold-start control-room cache pre-warm."""

import threading

import pytest


def test_entries_use_the_same_keys_as_the_http_layer():
    """A pre-warm under the wrong key fills a cache nobody reads.

    The keys are duplicated (not imported) so a rename on either side fails
    loudly here instead of silently costing a cold start.
    """
    from app.api import dispersion
    from app.services import prewarm

    entries = {key: (label, ttl) for label, key, ttl, _builder in prewarm._entries()}

    for key in (
        "atmosphere:current",
        "summary",
        "data-quality",
        "grap:current",
        "fire-activity",
        "fire-hotspots",
        "plume-risk",
        "grid:forecast:24",
        "transport-risk:current:72",
        "alerts:all_stations",
    ):
        assert key in entries, key

    # The dispersion key is assembled in two places; an unfiltered 72 h request
    # must hit the entry the pre-warm fills.
    unfiltered = dispersion._parse_frame_hours(None)
    assert f"dispersion:72:8:{'all' if unfiltered is None else 'x'}" == "dispersion:72:8:all"
    assert "dispersion:72:8:all" in entries

    # Cheap high-traffic panels are warmed before the solver-heavy one.
    labels = [label for label, _key, _ttl, _builder in prewarm._entries()]
    assert labels.index("summary") < labels.index("dispersion:72:8:all")


def test_prewarm_populates_cache_and_survives_a_failing_entry(monkeypatch):
    from app.services import prewarm, ttl_cache

    calls: list[str] = []

    def boom(_db):
        raise RuntimeError("boom")

    entries = [
        ("one", "one", 60, lambda _db: {"label": "one"}),
        ("broken", "broken", 60, boom),
        ("two", "two", 60, lambda _db: {"label": "two"}),
    ]

    def fake_entries():
        calls.append("built")
        return entries

    monkeypatch.setattr(prewarm, "_entries", fake_entries)
    monkeypatch.setattr(prewarm, "_ENTRY_GAP_S", 0)
    monkeypatch.setattr(ttl_cache, "_cache_enabled", lambda: True)
    ttl_cache.invalidate_all()

    prewarm.prewarm_control_room()

    # A failing entry is logged and skipped; the sweep continues and the good
    # entries still land in the cache.
    assert calls == ["built"]
    assert ttl_cache.cache_info()["entries"] == 2


def test_prewarm_honours_the_stop_event(monkeypatch):
    from app.services import prewarm

    ran: list[str] = []

    def builder(_db):
        ran.append("built")
        return {}

    monkeypatch.setattr(
        prewarm, "_entries", lambda: [(f"e{i}", f"e{i}", 60, builder) for i in range(3)]
    )
    monkeypatch.setattr(prewarm, "_ENTRY_GAP_S", 0)

    stop = threading.Event()
    stop.set()
    prewarm.prewarm_control_room(stop=stop)
    assert ran == []


@pytest.mark.parametrize("value,expected", [
    ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
    ("false", False), ("0", False), ("no", False), ("off", False),
])
def test_prewarm_setting_parses_from_the_environment(value, expected):
    from app.config import Settings

    assert Settings(control_room_prewarm=value).control_room_prewarm is expected


def test_prewarm_is_off_by_default():
    """Local dev, pytest and CI must never pay for the sweep unasked."""
    from app.config import Settings

    assert Settings().control_room_prewarm is False
