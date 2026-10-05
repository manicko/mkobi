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

**`CREATE INDEX CONCURRENTLY` is not expressible in a revision under this
project's async `alembic/env.py` today.** Every plausible way to reach an
out-of-transaction connection fails, and this document records the failures as
measured, not as assumed. The project therefore uses the same in-transaction
`CREATE INDEX IF NOT EXISTS` shape as every other index revision in the chain.

### 1.1 Why the naive form cannot work

`alembic/env.py` runs migrations through a sync connection proxy
(`Connection.run_sync(do_run_migrations)`), and `do_run_migrations` wraps the run
(`alembic/env.py:88-96`):

```python
def do_run_migrations(sync_connection: Connection) -> None:
    context.configure(connection=sync_connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
```

The offline path (`run_migrations_offline`, `alembic/env.py:84-85`) wraps the run
in `context.begin_transaction()` too. So every statement in an `op.execute(...)`
runs inside that open transaction. PostgreSQL refuses `CREATE INDEX
CONCURRENTLY` when a transaction block is in progress:

```
asyncpg.exceptions.ActiveSQLTransactionError:
  CREATE INDEX CONCURRENTLY cannot run inside a transaction block
```

That refusal is not cosmetic: it aborts the transaction, and the advisory-lock
release that follows then fails too (`InFailedSQLTransactionError`), because the
connection is in an aborted transaction. The migration process exits non-zero and
`alembic_version` stays at the previous revision.

### 1.2 The escape that was tried, and why it does not work here

An earlier revision of this document published a recipe: end Alembic's migration
transaction with `op.get_context().begin_transaction().commit()`, then run the
one concurrent statement through the bound connection's driver, then commit. **It
was proven not to work and must not be re-published as working.** The three
failure modes, each measured on this repository's stack:

1. **`op.get_context().begin_transaction()` is not the transaction.** In this
   async setup the call returns Alembic's `nullcontext`, not a transactional
   context with a `commit()` method:
   `AttributeError: 'nullcontext' object has no attribute 'commit'`. The recipe's
   first line raises before any concurrent statement is reached.
2. **Committing on the bound SQLAlchemy connection does not end the driver's
   transaction.** The async migration connection holds the transaction on the
   driver, so `op.get_bind().commit()` followed by
   `op.get_bind().exec_driver_sql("CREATE INDEX CONCURRENTLY ...")` still raises
   `asyncpg.exceptions.ActiveSQLTransactionError: CREATE INDEX CONCURRENTLY
   cannot run inside a transaction block`. The driver transaction is still open.
3. **The raw-driver and fresh-engine routes deadlock or cannot see the chain's
   work.** Reaching the raw asyncpg connection directly raises
   `ActiveSQLTransactionError` for the same reason; opening a fresh engine
   deadlocks against the connection `run_sync` is holding; and a separate
   autocommit connection cannot see a table the chain has created but not yet
   committed.

No variant of the recipe is a working escape under the current `env.py`.

### 1.3 What the project does instead

Every index revision in this chain uses the same in-transaction shape:

```python
from alembic import op

def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_example "
        "ON some_table (some_column)"
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_example")
```

This is transactional, so it participates in the migration's transaction and is
rolled back with it on failure. The `IF NOT EXISTS` / `IF EXISTS` guards keep the
statement idempotent when a database already carries the object.

### 1.4 The cost, stated honestly

A non-concurrent `CREATE INDEX` takes a **write lock on the table for the
duration of the build**. On an empty or low-traffic table that lock is
imperceptible and the in-transaction form is the right choice. On a large, live
table the lock blocks writes for the whole build and is **not** acceptable during
traffic.

That trade-off is the operator's decision, and this document exists to give them
the information to make it:

- Applying a non-concurrent index revision on a large live table means a write
  outage for the build's duration, inside the migration's transaction.
- There is currently no in-revision way to avoid that with `CONCURRENTLY` (see
  1.2). Building the index out of band — via `psql` with `CREATE INDEX
  CONCURRENTLY` outside Alembic, then landing a revision that only records the
  state — is the only concurrent route available today, and it is a manual
  operation with its own supervision and idempotency requirements.

### 1.5 What would have to change for the concurrent path to become possible

Enabling `CREATE INDEX CONCURRENTLY` in a revision is **not a small change**. It
requires at least:

- `alembic/env.py` to stop wrapping every run in `context.begin_transaction()`
  (or to expose a migration mode in which the transaction is not opened for a
  revision that needs autocommit), and
- the async connection lifecycle to expose a genuinely autocommit driver
  connection that is the same session that sees the chain's uncommitted work, so
  a concurrent build can run against a schema the chain has just created.

Until both hold, the in-transaction form in 1.3 remains the only expressible
shape, and any document or revision claiming otherwise is wrong.

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

### 4.1 Current verdict: clean

`.\Makefile.ps1 migration-check` reports **"No new upgrade operations
detected."** The model metadata and the migrated schema match: the two
filter-value indexes (`uq_dashboard_filter_values`,
`idx_dashboard_filter_values_lookup`, both created by revision `000000000002`)
are declared in `src/mkobi/db/models/dashboard_filter_values.py::__table_args__`,
so an index that exists in the database but is declared by no model does not
surface as drift. The one index not declared by a model is
`alembic_version_pkc`, which belongs to Alembic's own version table, not to the
application schema.

The measured census — 13 base tables, 13 foreign-key constraints, 6 PostgreSQL
ENUM types, 37 indexes — is recorded in
[Database Indexes](./indexes.md#modelchain-index-census).

The drift assertion is still mandatory before every landing, not because it is
expected to fail but because a schema-only revision that forgets its matching
model change (or its inverse) would be caught here.

---

## Cross-References

- [Database Indexes](./indexes.md) — index inventory
- [Enums](./enums.md) — StrEnum definitions
- [Core Schema](./schema-core.md) — table definitions
- `Makefile.ps1` — `migration-check`, `test-up`, `rehearse-restore`
- `alembic/env.py` — migration transaction and lock ownership
