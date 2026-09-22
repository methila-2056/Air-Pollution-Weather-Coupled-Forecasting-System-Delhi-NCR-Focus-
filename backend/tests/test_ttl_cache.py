"""Tests for the TTL cache used to speed up control-room aggregations.

The cache is intentionally bypassed on SQLite (tests/local), so these cases
force ``_cache_enabled`` on and exercise the TTL + invalidation behaviour
directly.
"""
import time

from app.services import ttl_cache


def test_cached_builds_once_until_ttl(monkeypatch):
    monkeypatch.setattr(ttl_cache, "_cache_enabled", lambda: True)
    builds = {"n": 0}

    def builder():
        builds["n"] += 1
        return {"value": builds["n"]}

    first = ttl_cache.cached("k1", 60, builder)
    second = ttl_cache.cached("k1", 60, builder)
    assert first == {"value": 1}
    assert second == {"value": 1}
    assert builds["n"] == 1


def test_cached_rebuilds_after_ttl_expiry(monkeypatch):
    monkeypatch.setattr(ttl_cache, "_cache_enabled", lambda: True)
    builds = {"n": 0}

    def builder():
        builds["n"] += 1
        return builds["n"]

    assert ttl_cache.cached("k2", 0.05, builder) == 1
    time.sleep(0.06)
    assert ttl_cache.cached("k2", 0.05, builder) == 2


def test_cached_distinguishes_keys(monkeypatch):
    monkeypatch.setattr(ttl_cache, "_cache_enabled", lambda: True)
    assert ttl_cache.cached("a", 60, lambda: "A") == "A"
    assert ttl_cache.cached("b", 60, lambda: "B") == "B"
    assert ttl_cache.cached("a", 60, lambda: "A2") == "A"


def test_invalidate_all_clears_every_key(monkeypatch):
    monkeypatch.setattr(ttl_cache, "_cache_enabled", lambda: True)
    ttl_cache.cached("x", 60, lambda: 1)
    ttl_cache.cached("y", 60, lambda: 2)
    assert ttl_cache.cache_info()["entries"] >= 2
    ttl_cache.invalidate_all()
    assert ttl_cache.cache_info()["entries"] == 0
    assert ttl_cache.cached("x", 60, lambda: 100) == 100


def test_cached_bypasses_when_sqlite_backend(monkeypatch):
    monkeypatch.setattr(ttl_cache, "_cache_enabled", lambda: False)
    builds = {"n": 0}

    def builder():
        builds["n"] += 1
        return builds["n"]

    assert ttl_cache.cached("z", 60, builder) == 1
    assert ttl_cache.cached("z", 60, builder) == 2
    assert builds["n"] == 2


def teardown_module(_module):
    ttl_cache.invalidate_all()
