"""Tests for the bounded, logged, session-scoped migration lock.

Two concerns: the retry logic driving the attempt callable (no database, no
Alembic, no real sleeps), and the source contract that keeps the lock statements in
``alembic/env.py`` bound as parameters rather than interpolated.
"""

from pathlib import Path

import pytest

from mkobi.db.migration_lock import retry_migration_lock_acquisition

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PY = _PROJECT_ROOT / "alembic" / "env.py"


class _WarningRecorder:
    """Collect ``logger.warning`` messages without touching global logging state.

    The helper emits only warnings that must always be visible; asserting on the
    calls to its own logger avoids depending on a root logger that other tests may
    have disabled or reconfigured.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str, *args: object) -> None:
        self.messages.append(message % args if args else message)


@pytest.mark.asyncio
class TestMigrationLockRetry:
    """The retry loop, driven by a stub attempt callable and a patched sleep."""

    async def test_lock_is_acquired_on_the_first_attempt(
        self, monkeypatch
    ) -> None:
        """A first-attempt success returns True, never sleeps and logs nothing."""
        sleep_calls: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("mkobi.db.migration_lock.asyncio.sleep", _fake_sleep)
        recorder = _WarningRecorder()
        monkeypatch.setattr("mkobi.db.migration_lock.logger.warning", recorder)
        calls = 0

        async def _stub() -> bool:
            nonlocal calls
            calls += 1
            return True

        result = await retry_migration_lock_acquisition(_stub)

        assert result is True
        assert calls == 1
        assert sleep_calls == []
        assert recorder.messages == []

    async def test_lock_is_acquired_after_several_refusals(
        self, monkeypatch
    ) -> None:
        """Two refusals then a success: three calls, two sleeps, two warnings."""
        sleep_calls: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("mkobi.db.migration_lock.asyncio.sleep", _fake_sleep)
        recorder = _WarningRecorder()
        monkeypatch.setattr("mkobi.db.migration_lock.logger.warning", recorder)
        calls = 0

        async def _stub() -> bool:
            nonlocal calls
            calls += 1
            return calls > 2

        result = await retry_migration_lock_acquisition(
            _stub, max_attempts=5, interval_seconds=0.0
        )

        assert result is True
        assert calls == 3
        assert len(sleep_calls) == 2
        assert len(recorder.messages) == 2

    async def test_permanent_refusal_returns_false_and_states_the_next_action(
        self, monkeypatch
    ) -> None:
        """A permanent refusal returns False and the last warning names the action."""
        sleep_calls: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("mkobi.db.migration_lock.asyncio.sleep", _fake_sleep)
        recorder = _WarningRecorder()
        monkeypatch.setattr("mkobi.db.migration_lock.logger.warning", recorder)
        calls = 0

        async def _stub() -> bool:
            nonlocal calls
            calls += 1
            return False

        result = await retry_migration_lock_acquisition(
            _stub, max_attempts=3, interval_seconds=0.0
        )

        assert result is False
        assert calls == 3
        final = recorder.messages[-1]
        assert str(42) in final
        assert "3" in final
        assert "re-run" in final
        assert "stuck" in final

    async def test_no_sleep_and_no_retry_warning_after_the_final_attempt(
        self, monkeypatch
    ) -> None:
        """max_attempts=1: one call, zero sleeps, exactly one final-refusal warning."""
        sleep_calls: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("mkobi.db.migration_lock.asyncio.sleep", _fake_sleep)
        recorder = _WarningRecorder()
        monkeypatch.setattr("mkobi.db.migration_lock.logger.warning", recorder)
        calls = 0

        async def _stub() -> bool:
            nonlocal calls
            calls += 1
            return False

        result = await retry_migration_lock_acquisition(
            _stub, max_attempts=1, interval_seconds=5.0
        )

        assert result is False
        assert calls == 1
        assert sleep_calls == []
        assert len(recorder.messages) == 1
        assert "retrying" not in recorder.messages[0]

    async def test_interval_is_passed_to_sleep_on_every_retry(
        self, monkeypatch
    ) -> None:
        """The configured interval is the argument of every retry sleep."""
        sleep_calls: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("mkobi.db.migration_lock.asyncio.sleep", _fake_sleep)
        calls = 0

        async def _stub() -> bool:
            nonlocal calls
            calls += 1
            return calls > 3

        result = await retry_migration_lock_acquisition(
            _stub, max_attempts=4, interval_seconds=0.25
        )

        assert result is True
        assert sleep_calls == [0.25, 0.25, 0.25]


class TestMigrationLockSourceContract:
    """The lock statements are bound as parameters, and the key is defined once."""

    def test_env_py_binds_the_lock_key_rather_than_interpolating_it(self) -> None:
        """env.py contains no f-string SQL and binds :lock_key on both statements."""
        source = _ENV_PY.read_text(encoding="utf-8")

        assert 'text(f"' not in source
        assert "pg_advisory_lock(42" not in source
        assert "pg_advisory_unlock(42" not in source
        assert "pg_try_advisory_lock(42" not in source

        assert 'text("SELECT pg_try_advisory_lock(:lock_key)")' in source
        assert 'text("SELECT pg_advisory_unlock(:lock_key)")' in source

    def test_env_py_defines_no_local_lock_key(self) -> None:
        """The lock key literal is defined exactly once, in the helper module."""
        search_paths = [_ENV_PY]
        search_paths.extend(sorted((_PROJECT_ROOT / "src" / "mkobi" / "db").glob("*.py")))

        definitions = [
            path
            for path in search_paths
            if "MIGRATION_ADVISORY_LOCK_KEY = 42" in path.read_text(encoding="utf-8")
        ]

        assert definitions == [
            _PROJECT_ROOT / "src" / "mkobi" / "db" / "migration_lock.py"
        ]
