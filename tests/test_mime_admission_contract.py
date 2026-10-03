"""Contract tests for MIME admission and the libmagic detector.

These tests are host-independent: they never rely on the host's libmagic
presence. They pin the two surviving defects of the retired finding:

- the doubly dead ``allowed_mime_types`` configuration key (settings surface and
  shipped YAML), and
- the detector, which must delegate to libmagic unconditionally with no
  heuristic fallback whose verdict depends on the image.
"""

import builtins
import inspect
from pathlib import Path
from collections.abc import Iterator

import pytest

import mkobi.config
import mkobi.main
import mkobi.startup
from mkobi.config import Settings, UploadSettings, clear_config_cache, get_config
from mkobi.models.enums import MimeTypeEnum
from mkobi.services import file_processing


@pytest.fixture
def restored_config_cache() -> Iterator[None]:
    """Clear the global config cache before and after a test.

    The tests below set permissive environment variables and clear the cache so
    the settings surface is re-evaluated. Without restoring the cache, later
    settings tests would inherit the monkeypatched environment through the
    cached singleton.
    """
    clear_config_cache()
    try:
        yield
    finally:
        clear_config_cache()


class TestSingleDeclarationSite:
    """The allow-list is declared in exactly one place: MimeTypeEnum."""

    def test_allowed_values_are_the_three_members(self) -> None:
        assert MimeTypeEnum.allowed_values() == [
            "text/csv",
            "application/gzip",
            "application/x-gzip",
        ]

    def test_key_absent_from_settings_surface(self) -> None:
        assert not hasattr(Settings(), "allowed_mime_types")
        assert "allowed_mime_types" not in UploadSettings.model_fields

    def test_key_absent_from_shipped_yaml(self) -> None:
        import yaml

        yaml_path = Path(mkobi.config.__file__).parent / "settings" / "app.yaml"
        parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert "allowed_mime_types" not in parsed["upload"]


class TestInertEnvironmentVariable:
    """UPLOAD__ALLOWED_MIME_TYPES is absent and cannot reach admission."""

    def test_env_var_does_not_reach_settings_surface(
        self, monkeypatch: pytest.MonkeyPatch, restored_config_cache: None
    ) -> None:
        monkeypatch.setenv(
            "UPLOAD__ALLOWED_MIME_TYPES",
            '["text/plain", "application/octet-stream"]',
        )
        clear_config_cache()
        config = get_config()
        assert not hasattr(config, "allowed_mime_types")
        assert not hasattr(config.upload, "allowed_mime_types")

    def test_permissive_env_var_cannot_admit_plain_text(
        self, monkeypatch: pytest.MonkeyPatch, restored_config_cache: None, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(
            "UPLOAD__ALLOWED_MIME_TYPES",
            '["text/plain", "application/octet-stream"]',
        )
        clear_config_cache()
        monkeypatch.setattr(
            file_processing,
            "detect_mime_type_from_content",
            lambda _path: "text/plain",
        )

        candidate = tmp_path / "plain.csv"
        candidate.write_bytes(b"just some plain text")

        from mkobi.models.enums import ErrorCode
        from mkobi.utils.exceptions import AppException

        with pytest.raises(AppException) as exc_info:
            file_processing.validate_mime_type(candidate)
        assert exc_info.value.code == ErrorCode.INVALID_FILE_TYPE


class TestCheckDependencies:
    """libmagic is a hard startup dependency."""

    def test_magic_is_required(self) -> None:
        assert "magic" in mkobi.main.APP_REQUIRED_MODULES

    def test_missing_magic_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "magic":
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        # The application's logging setup runs with disable_existing_loggers=True
        # and propagate=False, so caplog is not reliable in a full session.
        # Attach a collector directly to the emitting logger instead.
        import logging

        main_logger = mkobi.startup.logger
        captured: list[logging.LogRecord] = []

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        collector = _Collector(level=logging.DEBUG)
        original_level = main_logger.level
        was_disabled = main_logger.disabled
        main_logger.addHandler(collector)
        main_logger.setLevel(logging.DEBUG)
        main_logger.disabled = False

        monkeypatch.setattr(builtins, "__import__", fake_import)
        try:
            with pytest.raises(SystemExit) as exc_info:
                mkobi.main.check_dependencies(mkobi.main.APP_REQUIRED_MODULES)
        finally:
            main_logger.removeHandler(collector)
            main_logger.setLevel(original_level)
            main_logger.disabled = was_disabled

        assert exc_info.value.code == 1
        assert any("magic" in record.getMessage() for record in captured)

    def test_all_required_modules_present(self) -> None:
        mkobi.main.check_dependencies(mkobi.main.APP_REQUIRED_MODULES)


class _MagicSentinel:
    """Stand-in for the ``magic`` module that records its call."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, bool]] = []

    def from_buffer(self, buffer: bytes, mime: bool = False) -> str:
        self.calls.append((buffer, mime))
        return "text/x-sentinel"


class TestDetectorDelegatesToLibmagic:
    """The detector reads the module attribute and has no fallback arm."""

    def test_detector_returns_sentinel_for_heuristic_favourite(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        sentinel = _MagicSentinel()
        monkeypatch.setattr(file_processing, "magic", sentinel)

        # The deleted heuristic admitted this buffer as text/csv; a resurrected
        # ``except ImportError`` arm would ignore the module attribute and return
        # text/csv. The sentinel proves the libmagic path is the only one taken.
        candidate = tmp_path / "heuristic.csv"
        candidate.write_bytes(b"category;sales\nA;1\n")

        detected = file_processing.detect_mime_type_from_content(candidate)

        assert detected == "text/x-sentinel"
        assert len(sentinel.calls) == 1
        _buffer, mime = sentinel.calls[0]
        assert mime is True

    def test_module_has_no_import_error_arm(self) -> None:
        source = inspect.getsource(file_processing)
        assert "ImportError" not in source


class TestEnforcementSiteMembership:
    """validate_mime_type admits exactly MimeTypeEnum.allowed_values()."""

    @pytest.mark.parametrize("allowed", MimeTypeEnum.allowed_values())
    def test_allowed_member_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, allowed: str
    ) -> None:
        monkeypatch.setattr(
            file_processing,
            "detect_mime_type_from_content",
            lambda _path: allowed,
        )
        candidate = tmp_path / "candidate.csv"
        candidate.write_bytes(b"x")

        file_processing.validate_mime_type(candidate)

    def test_plain_text_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            file_processing,
            "detect_mime_type_from_content",
            lambda _path: "text/plain",
        )
        candidate = tmp_path / "candidate.csv"
        candidate.write_bytes(b"x")

        from mkobi.models.enums import ErrorCode
        from mkobi.utils.exceptions import AppException

        with pytest.raises(AppException) as exc_info:
            file_processing.validate_mime_type(candidate)
        assert exc_info.value.code == ErrorCode.INVALID_FILE_TYPE
