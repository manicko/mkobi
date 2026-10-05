"""Source contract for the index-DDL policy and the head rehearsal procedure.

No database is required: this module reads the policy document as text and
asserts the safety properties a reader must be able to rely on. It pins that the
procedure names its forbidden targets explicitly, that it prescribes no
destructive Makefile target, and that it does not re-publish the concurrent
index recipe as a working shape.
"""

from __future__ import annotations

import re
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

# A fenced code block, captured with its language tag and body.
_FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<body>.*?)```", re.DOTALL)


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


# --- The concurrent-index claim -------------------------------------------
#
# The policy once published a recipe that claimed ``CREATE INDEX CONCURRENTLY``
# could run from inside an Alembic revision by ending the migration transaction
# and executing on the bound connection. It was proven not to work under this
# repository's async ``alembic/env.py``: the bound connection's driver
# transaction stays open, ``begin_transaction()`` returns a ``nullcontext``, and
# the naive form is refused with ``ActiveSQLTransactionError``.
#
# These two tests guard the **shape of the claim**, not incidental wording.


def _fenced_blocks() -> list[tuple[str, str]]:
    return [
        (match.group("lang"), match.group("body"))
        for match in _FENCE_RE.finditer(_policy_text())
    ]


def test_policy_states_concurrent_index_is_not_expressible() -> None:
    """The document must carry the verdict that the concurrent path cannot work.

    Guards the *claim*: if someone deletes the verdict and the document reads as
    if concurrent index DDL is available, this fails.
    """
    text = _policy_text().lower()
    assert "not expressible" in text or "is not possible" in text, (
        "migration-index-policy.md must state plainly that CREATE INDEX "
        "CONCURRENTLY is not expressible in a revision under this env.py"
    )


def test_no_fenced_upgrade_body_issues_a_concurrent_create() -> None:
    """No recommended recipe may issue ``CREATE INDEX CONCURRENTLY``.

    The shape of the false claim is a fenced ``upgrade()`` body that runs a
    concurrent create. Such a block is exactly what the policy must never carry
    again: it cannot execute on this stack.
    """
    offenders: list[str] = []
    for _lang, body in _fenced_blocks():
        if "def upgrade" in body and "CREATE INDEX CONCURRENTLY" in body:
            offenders.append(body.strip())
    assert not offenders, (
        "migration-index-policy.md presents a fenced upgrade() body that issues "
        "CREATE INDEX CONCURRENTLY, which cannot run under this async env.py. "
        f"Offending block(s): {offenders!r}"
    )
