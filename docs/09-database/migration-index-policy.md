---
id: migration-index-policy
domain: database
tags:
  - migrations
  - alembic
  - index-ddl
  - create-index-concurrently
  - drift
  - rehearsal
related:
  - indexes
  - schema-core
  - schema-processing
  - enums
---

# Migration Index-DDL Policy and Head Rehearsal

This document records two operating rules for schema change in this repository:
how index DDL must be written under the current Alembic setup, and how to
rehearse a new revision forward from the current head on a disposable database.
It is a policy document. It creates no database object by itself.

The two canonical quality-gate and database targets it relies on are:

- `.\Makefile.ps1 migration-check` — the mandatory post-landing drift assertion
  (defined in `Makefile.ps1`, target `Invoke-MigrationCheck`).
- `.\Makefile.ps1 test-up` — starts the hermetic test stack
  (`test-db` on host port 5434) that the rehearsal below targets.

---

## 1. Index DDL under this setup

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block, and this
repository wraps every migration body in one. The escape below is the only way
to express concurrent index DDL here, and it must stay narrow.

### 1.1 Why the naive form cannot work

`alembic/env.py` runs migrations through a sync connection proxy
(`Connection.run_sync(do_run_migrations)`), and `do_run_migrations` wraps the run:

```python
def do_run_migrations(sync_connection: Connection) -> None:
    context.configure(connection=sync_connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
```

`context.begin_transaction()` is entered before any revision body executes, so
every statement in an `op.execute(...)` runs inside that open transaction. The
offline path (`run_migrations_offline`) does the same. PostgreSQL refuses
`CREATE INDEX CONCURRENTLY` when a transaction block is in progress, and the
refusal is `CREATE INDEX CONCURRENTLY cannot run inside a transaction block`.
A revision that calls `op.execute("CREATE INDEX CONCURRENTLY ...")` therefore
fails on the server, whatever the connection's autocommit setting is: the
transaction is already open.

### 1.2 The escape: a narrow autocommit window

The statement must execute on a connection that is genuinely outside the
migration transaction. In a revision, reach the driver connection through the
bound context, commit the migration transaction, and let SQLAlchemy execute the
one concurrent statement in autocommit before normal operation resumes:

```python
import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    """Create one index concurrently, outside the migration transaction."""
    # 1. End the transaction Alembic opened in env.py. On the async stack the
    #    Alembic run wraps the whole revision body in pool.acquire()'s
    #    "begin once" block, so ending it here is what lets a later statement
    #    start its own.
    op.get_context().begin_transaction().commit()

    # 2. Take the DBAPI connection directly. execute_driver_sql runs in
    #    autocommit when the Connection is in SQLAlchemy 2.0 "autobegin"
    #    state and no Transaction is held on it.
    conn = op.get_bind()
    conn.execute_driver_sql(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "idx_processing_logs_status_finished_at "
        "ON processing_logs (status, finished_at)"
    )

def downgrade() -> None:
    """Drop the index concurrently, outside the migration transaction."""
    op.get_context().begin_transaction().commit()
    conn = op.get_bind()
    conn.execute_driver_sql(
        "DROP INDEX CONCURRENTLY IF EXISTS idx_processing_logs_status_finished_at"
    )
```

### 1.3 Why the escape works here, and the bounds you must keep

This shape is compatible with how `env.py` runs migrations, for three reasons
visible in `alembic/env.py`:

1. **`op.get_bind()` yields the sync proxy's DBAPI connection.** `do_run_migrations`
   is invoked through `await connection.run_sync(do_run_migrations)`
   (`alembic/env.py:151`), so within a revision `op.get_bind()` is the SA
   `Connection` that Alembic configures — `env.py` passes `connection=sync_connection`
   at `alembic/env.py:92`. Reaching the driver from it is supported.
2. **The migration's own statements are always sent as raw text.** Every index
   revision in this chain uses `op.execute("...")`; none uses `op.create_index`,
   whose online implementation necessarily issues the statement on the in-transaction
   connection. `op.execute` is how index DDL is already written here.
3. **The advisory lock is held on the session, not the transaction** (`env.py:129`,
   `pg_try_advisory_lock`, session-scoped). Committing or ending the migration
   transaction inside a revision does not release it, so the exclusion `env.py`
   establishes is preserved across the autocommit window.

Bounds that keep the escape narrow — treat each as a requirement:

- **Exactly one concurrent statement** between the `commit()` and the end of the
  function. A `CREATE INDEX CONCURRENTLY` cannot participate in the migration's
  transaction, **cannot be rolled back** once started, and **must not be mixed**
  with any transactional statement in the same window.
- **The window closes with the function.** The next statement in the revision
  body opens a fresh transaction on the bound connection; do not carry the
  autocommit connection outside the one call and do not reuse it.
- **`CONCURRENTLY` implies idempotency by itself; keep the `IF NOT EXISTS` guard
  anyway.** A concurrent create that fails leaves an `INVALID` index behind, and
  a retry needs the guard to be expressible. Verify staleness with
  `SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE NOT indisvalid;`.
- **A failed concurrent build is not transactionally undone.** `CONCURRENTLY`
  is inherently non-atomic: on failure you must
  `DROP INDEX CONCURRENTLY IF EXISTS` the invalid index before retrying. That is
  the reason the rollback below is a compensating procedure, not a transaction.
- **This recipe is for `CREATE/DROP INDEX CONCURRENTLY` only.** Ordinary,
  in-transaction index DDL keeps using `op.execute` with no escape.

> Verified against the current `alembic/env.py`: the mechanism described is
> compatible with how migrations run here. If `env.py` is later changed to stop
> using `context.begin_transaction()` around `context.run_migrations()` — or to
> drop the sync-proxy path — this recipe must be re-verified before use.

---

## 2. Rehearsal: apply the chain forward from the current head

Run this against a **uniquely named, disposable database on the test stack's
PostgreSQL** (host port 5434), never against any live database. It applies the
chain **from the current head forward**, not from `base`, so it exercises the
incremental step a new revision adds.

### 2.1 Forbidden targets

These names are forbidden as rehearsal targets and must never be created,
dropped, migrated, or restored into by this procedure:

- `bidb` — the shared development database.
- **every** `bidb_test*` name, explicitly including `bidb_test` and every
  per-run `bidb_test_<token>` database.
- `postgres`, `template0`, `template1` — PostgreSQL's own system databases.

The only database this procedure writes is its own disposably-named scratch
database, dropped on every exit path.

### 2.2 Copy-pasteable procedure

Prerequisites: `.\Makefile.ps1 test-up` has run (test stack healthy), and the new
revision is committed and is the chain head.

```powershell
# 2.2.1 — Pick a unique scratch name. This symbol never collides with bidb,
#         bidb_test, or bidb_test_<token>.
$scratch = "mkobi_migrehearse_$([guid]::NewGuid().ToString('N').Substring(0, 8))"
$dc = 'docker compose -p mkobi-test -f docker/docker-compose.test.yml'

# 2.2.2 — Resolve the current head from the committed chain (source of truth,
#         read from Alembic, not from the database).
$head = (uv run alembic heads | Select-String -Pattern '^\w+' | ForEach-Object {
    ($_ -split '\s+')[0]
}) | Select-Object -First 1
Write-Host "Current head: $head"

# 2.2.3 — Create the disposable database on the test cluster.
& $dc exec -T test-db psql -U postgres -d postgres -c "CREATE DATABASE `"$scratch`""
if ($LASTEXITCODE -ne 0) { throw "scratch create failed" }

try {
    # 2.2.4 — Apply the chain FROM THE CURRENT HEAD FORWARD. Do NOT use `base`.
    #         A deliberate, narrow escape: MKOBI_TEST_RUN_ID is unique so this
    #         run never shares a per-run database with another run.
    $env:MKOBI_TEST_RUN_ID = "migrehearse_$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    & $dc run --rm --no-deps `
        -e MKOBI_TEST_RUN_ID=$env:MKOBI_TEST_RUN_ID `
        -e DATABASE_URL="postgresql+asyncpg://postgres:postgres@test-db:5432/$scratch" `
        test-migrate alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "upgrade head failed" }

    # 2.2.5 — Verify alembic_version equals the head resolved in 2.2.2.
    $rev = (& $dc exec -T test-db psql -U postgres -d $scratch -tAc `
        "SELECT version_num FROM alembic_version") -join ''
    if ($rev.Trim() -ne $head) { throw "version $($rev.Trim()) != head $head" }
    Write-Host "alembic_version = $($rev.Trim()) (expected $head)"

    # 2.2.6 — Verify the objects THIS revision creates actually exist. Replace
    #         the query with the index/column/table the new revision adds.
    & $dc exec -T test-db psql -U postgres -d $scratch -c `
        "SELECT indexname FROM pg_indexes WHERE tablename = 'processing_logs' ORDER BY indexname"
    if ($LASTEXITCODE -ne 0) { throw "object verification failed" }
}
finally {
    # 2.2.7 — Drop the disposable database on EVERY exit path, including failure.
    & $dc exec -T test-db psql -U postgres -d postgres -c `
        "DROP DATABASE IF EXISTS `"$scratch`" WITH (FORCE)" | Out-Null
    Remove-Item Env:\MKOBI_TEST_RUN_ID -ErrorAction SilentlyContinue
}

# 2.2.8 — Post-landing drift assertion (mandatory, see section 4).
.\Makefile.ps1 migration-check
```

Notes on the copy-pasteable form:

- Steps 2.2.4 and 2.2.7 mirror the scratch-database create/drop shape already
  used by `Invoke-RehearseRestore` in `Makefile.ps1` (`CREATE DATABASE`, then
  `DROP DATABASE IF EXISTS ... WITH (FORCE)` in a `finally`).
- Setting `MKOBI_TEST_RUN_ID` to a fresh value for this run is required: it is
  the documented contract for a per-run test database, and reusing another run's
  value would share — and let this run drop — that run's database.
- The `try/finally` is the guarantee that step 2.2.7 runs even when 2.2.4–2.2.6
  throw.

---

## 3. The half-migration hazard

A migration body is not atomic across every revision in this chain. When a
migration **succeeds on some of its objects and fails on others**, the chain
stops at the previous revision — `alembic_version` still shows the **old**
revision — while part of the new work **is already applied to the database**. The
version table tells you where Alembic thinks it is; it does **not** tell you what
the previous attempt actually did.

This is exactly the situation a partially applied `CREATE TYPE` or
`DROP TYPE` can leave (see `4479eb53fd4e`), and exactly what `CONCURRENTLY`
makes possible by design, since it cannot be rolled back.

Before re-running `alembic upgrade head`, the operator must check the objects the
failed revision creates or drops, not just the revision number:

```sql
-- Did the new table/column/index land?
SELECT indexname FROM pg_indexes WHERE tablename = '<table>';
SELECT column_name FROM information_schema.columns WHERE table_name = '<table>';
-- Did an enum recreate half-succeed?
SELECT enumlabel FROM pg_enum
  JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
 WHERE pg_type.typname = '<type>'
 ORDER BY pg_enum.enumsortorder;
-- Did a concurrent build leave an INVALID index behind?
SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE NOT indisvalid;
```

If any of those show a partially applied state, the remedy is **a new forward
revision** that reconciles the type to the desired shape — never `alembic
downgrade`. Downgrade assumes the previous revision's work is fully applied,
which a half-applied upgrade has already falsified.

---

## 4. Drift assertion: `.\Makefile.ps1 migration-check`

The mandatory post-landing drift assertion is:

```powershell
.\Makefile.ps1 migration-check
```

Not `uv run alembic check`. This repository does not run Alembic from the host
against an unset `sqlalchemy.url`; `Invoke-MigrationCheck` runs
`alembic check` as a one-shot inside the hermetic test compose
(`docker compose -p mkobi-test ... run --rm test-migrate alembic check`), which
pins the target to `bidb_test` and makes a request against the dev `bidb`
structurally impossible.

### 4.1 Honest expectation: this is not yet a clean result

`alembic check` has **still never been run against a real database in this
repository** — the target exists but its output has not been observed. The honest
expectation is **not** a clean result. At least two indexes in the chain are
declared by **no** model in `target_metadata`:

- `uq_dashboard_filter_values` (`dashboard_filter_values`)
- `idx_dashboard_filter_values_lookup` (`dashboard_filter_values`)

`alembic check` compares the models to the migrated schema and reports
model/schema drift; an index that exists in the database but is declared by no
model is a reported difference. Both are exercised by the chain (`000000000002`)
and expected to surface here.

Recording the drift is the whole scope of this section. Reconciling it — whether
by declaring the missing indexes on the models or by an explicit, recorded
decision — is a later wave, not this one.

---

## Cross-References

- [Database Indexes](./indexes.md) — index inventory
- [Enums](./enums.md) — StrEnum definitions
- [Core Schema](./schema-core.md) — table definitions
- `Makefile.ps1` — `migration-check`, `test-up`, `rehearse-restore`
- `alembic/env.py` — migration transaction and lock ownership
