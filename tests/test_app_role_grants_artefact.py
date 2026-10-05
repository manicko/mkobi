"""Contract for the single referenced definition of the mkobi_app role grants.

No database is required: this module reads the artefact, the init script and the
``alembic/`` tree as text and asserts the properties a reader must be able to
rely on - one artefact, referenced by the loader, idempotent-shaped, and no role
DDL under ``alembic/``.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ARTEFACT = _REPO_ROOT / "docker" / "init-scripts" / "shared" / "app-role-grants.sql"
_INIT_SCRIPT = _REPO_ROOT / "docker" / "init-scripts" / "01-create-app-role.sh"
_ALEMBIC_DIR = _REPO_ROOT / "alembic"

# Role DDL that must never appear under alembic/. A role is cluster-global; a
# per-database migration cannot describe it, and a role created by a migration
# would break the per-environment grant model.
_FORBIDDEN_ALEMBIC_DDL = (
    "GRANT",
    "REVOKE",
    "CREATE ROLE",
    "ALTER DEFAULT PRIVILEGES",
)


def _artefact_text() -> str:
    return _ARTEFACT.read_text(encoding="utf-8")


def test_artefact_exists() -> None:
    """The single referenced grant artefact is present."""
    assert _ARTEFACT.is_file(), f"missing artefact: {_ARTEFACT}"


def test_init_script_references_the_artefact() -> None:
    """The init script loads the artefact rather than transcribing the grants."""
    script = _INIT_SCRIPT.read_text(encoding="utf-8")
    assert "shared/app-role-grants.sql" in script
    # The loader supplies the psql variables the artefact consumes.
    assert "app_password" in script
    assert "dbname" in script


def _sql_lines() -> str:
    """The artefact's executable SQL: comments (whole-line and trailing) removed."""
    lines = []
    for line in _artefact_text().splitlines():
        stripped = re.sub(r"--.*$", "", line).strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def test_artefact_is_idempotent_shaped() -> None:
    """CREATE ROLE is guarded so a re-run cannot abort on an existing role."""
    sql = _sql_lines()
    # The existence guard reuses the pg_roles shape Makefile.ps1 and the starter
    # use, and it must precede the CREATE ROLE it conditions.
    guard = "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname"
    assert guard in sql
    assert sql.index(guard) < sql.index("CREATE ROLE")
    # The CREATE ROLE lives inside that guard: it is indented within the DO
    # block, never issued at top level.
    for line in _artefact_text().splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("CREATE ROLE"):
            assert line != line.lstrip(), f"unguarded (top-level) CREATE ROLE: {line!r}"


def test_artefact_holds_the_full_grant_set() -> None:
    """The artefact carries the role, schema/table/sequence grants and defaults."""
    text = _artefact_text()
    assert "GRANT CONNECT ON DATABASE" in text
    assert "GRANT USAGE ON SCHEMA public" in text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public" in text
    assert "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public" in text
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public" in text


def test_artefact_documents_the_per_tier_difference() -> None:
    """The header explains why USAGE differs from the test tier's USAGE, CREATE."""
    text = _artefact_text()
    assert "USAGE, CREATE" in text
    assert "starter.py" in text
    assert "CREATE" in text


def test_artefact_header_states_no_alembic_role_ddl() -> None:
    """The artefact records that roles are not migrations."""
    text = _artefact_text()
    assert "alembic/" in text


def test_alembic_contains_no_role_ddl() -> None:
    """Zero matches for role DDL anywhere under alembic/."""
    offending: list[tuple[str, str]] = []
    for path in _ALEMBIC_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_ALEMBIC_DDL:
            if token in source:
                offending.append((str(path.relative_to(_REPO_ROOT)), token))
    assert offending == [], offending


def test_deployment_doc_records_the_restore_contract() -> None:
    """The deployment doc states the role is not in a dump and the remedy."""
    doc = (
        _REPO_ROOT / "docs" / "10-deployment" / "deployment.md"
    ).read_text(encoding="utf-8")
    assert "app-role-grants.sql" in doc
    assert "not part of a database dump" in doc
    assert "failed grants" in doc
