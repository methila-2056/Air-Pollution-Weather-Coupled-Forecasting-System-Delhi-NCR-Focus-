"""Unit tests for scripts/clean_generated.py (make clean-data)."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "clean_generated.py"

_spec = importlib.util.spec_from_file_location("clean_generated", SCRIPT)
clean_generated = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(clean_generated)


def _run(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(clean_generated, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["clean_generated.py", *argv])
    clean_generated.main()


def test_dry_run_does_not_delete(monkeypatch, tmp_path):
    junk = tmp_path / "nested" / "junk.pyc"
    junk.parent.mkdir(parents=True)
    junk.write_bytes(b"\x00")

    _run(monkeypatch, tmp_path, [])

    assert junk.exists()


def test_exec_deletes_regenerable_artifacts(monkeypatch, tmp_path):
    pyc = tmp_path / "x.pyc"
    pyc.write_bytes(b"\x00")
    db = tmp_path / "local.db"
    db.write_bytes(b"\x00")

    _run(monkeypatch, tmp_path, ["--exec"])

    assert not pyc.exists()
    assert not db.exists()


def test_exec_does_not_delete_source(monkeypatch, tmp_path):
    keep = tmp_path / "README.md"
    keep.write_text("keep", encoding="utf-8")

    _run(monkeypatch, tmp_path, ["--exec"])

    assert keep.exists()


def test_exec_never_touches_virtualenv(monkeypatch, tmp_path):
    venv_pyc = tmp_path / ".venv" / "Lib" / "site-packages" / "pkg.pyc"
    venv_pyc.parent.mkdir(parents=True)
    venv_pyc.write_bytes(b"\x00")

    _run(monkeypatch, tmp_path, ["--exec"])

    assert venv_pyc.exists()
