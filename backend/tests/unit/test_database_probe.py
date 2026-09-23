"""Unit tests for the shared database-liveness probe (``database_reachable``)."""

from unittest import mock

from app.database import database_reachable

from app import database as db_module


def test_reports_connected_when_engine_answers(db_session):
    assert database_reachable() is True


def test_reports_disconnected_when_engine_connect_raises():
    with mock.patch.object(
        db_module.engine, "connect", side_effect=RuntimeError("database down")
    ):
        assert database_reachable() is False


def test_reports_disconnected_when_execute_raises():
    def _boom():
        raise RuntimeError("SELECT 1 failed")

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        execute = _boom

    with mock.patch.object(db_module.engine, "connect", return_value=_Conn()):
        # the exception inside execute must be swallowed, not propagated
        assert database_reachable() is False
