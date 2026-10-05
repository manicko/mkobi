"""Source contract for the index-DDL policy and the head rehearsal procedure.

No database is required: this module reads the policy document as text and
asserts the two safety properties a reader must be able to rely on. It pins
that the procedure names its forbidden targets explicitly and that it prescribes
no destructive Makefile target as part of the procedure.
"""

from pathlib import Path

_POLICY = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "09-database"
    / "migration-index-policy.md"
)

# Makefile targets that destroy state and must never appear as a rehearsal step.
# "test-reset", "test-fresh", "fullclean", "nuke", "clean", "restore" and
# "test-down" are all destructive to data or volumes; none belongs in a
# forward-from-head rehearsal or in a policy that an operator will paste.
_FORBIDDEN_DESTRUCTIVE_TARGETS = (
    "test-fresh",
    "test-reset",
    "test-down",
    "fullclean",
    "nuke",
    "clean",
    "restore",
)


def _policy_text() -> str:
    return _POLICY.read_text(encoding="utf-8")


def test_policy_exists() -> None:
    """The policy document is present where a maintainer will find it."""
    assert _POLICY.is_file(), f"missing policy document: {_POLICY}"


def test_forbids_bidb_and_bidb_test_names() -> None:
    """The procedure states ``bidb`` and every ``bidb_test*`` name as forbidden."""
    text = _policy_text()
    assert "bidb" in text
    assert "bidb_test" in text
    # The forbidden target set must be stated, not merely referenced by a prefix.
    assert "bidb_test*" in text


def test_names_no_destructive_makefile_target() -> None:
    """The procedure prescribes no destructive Makefile target."""
    lines = [line for line in _policy_text().splitlines() if "Makefile.ps1" in line]
    prescribed = "\n".join(lines)
    for target in _FORBIDDEN_DESTRUCTIVE_TARGETS:
        # Inspect only the invoked target, not prose: match the token as a
        # Makefile argument (".\\Makefile.ps1 <target>").
        asserted = f"Makefile.ps1 {target}"
        assert asserted not in prescribed, (
            f"policy prescribes destructive target '{target}': {asserted}"
        )
