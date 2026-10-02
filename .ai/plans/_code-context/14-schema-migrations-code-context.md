---
audit_phase: 14-schema-migrations
finding_prefix: MIG-
validation_prefix: VAL-14-
report: .ai/audit/99-validation/14-schema-migrations-validated-findings.md
phase_findings: .ai/audit/14-schema-migrations/findings.md
code_context_authority: Phase-1 Auditor (overrides every report anchor)
read_head: 863b81b
status: complete
---

# Phase 14 — Code context (schema and migrations)

Analysis only. No production code, audit file, or sibling plan was modified; no migration was
run, no revision created, no database altered, no Docker state changed.

---

## 1. Scope and method

### 1.1 What the ID namespaces actually are

| Namespace | Count | Source |
|---|---|---|
| `MIG-001` … `MIG-008` | 8 | `audited-namespace: MIG-` in the report front matter; declared at `.kilo/commands/audit/phases/14-audit-schema-migrations.md:143` |
| `VAL-14-001` … `VAL-14-005` | 5 | `validation-namespace: VAL-14-`; a declared deviation from the flat `VAL-` form |
| Adjudicated prior findings | 6 | `TOPO-004`, `TOPO-007` (phase 01) · `QLT-008` (phase 08) · `TST-012` (phase 09) · `DP-003` (phase 05) · `PERF-001` (phase 11) |

The audited prefix is **`MIG-`**, not `SCHEMA-`, `MIG14-` or `14-`. A repository search for
in-source `MIG-` markers returns nothing, so no provenance migration is owed.

### 1.2 HEAD-vs-worktree split (measured, not assumed)

| Item | Measured value | Note |
|---|---|---|
| `git rev-parse HEAD` | **`863b81bb7a0296dc3ddd422388db693f742aef94`** | The brief said `ab76989`; that is now the **parent**. `863b81b` is `test(advisory-lock): make the lock_timeout leak guard non-vacuous` and touches `docs/06-backend/configuration.md`, `src/mkobi/db/advisory_lock.py`, `src/mkobi/workers/data_worker.py`, `tests/test_advisory_lock.py`, `tests/test_config.py` — **no phase-14 symbol**. |
| Dirty production files at audit start | **none** | `git status --short -- src/ tests/ alembic/ frontend/src/ docs/ pyproject.toml Makefile.ps1` returned **empty**. The "uncommitted production edits in a set-based write region" the brief described are **committed** in `ab76989` / `2174895`; nothing in that region was uncommitted when this run began. **A later edit to `src/mkobi/workers/data_worker.py` appeared mid-run** (§6) — transaction/lock only, no schema symbol. |
| Dirty paths | 41 deletions + 14 untracked | all under `.ai/` (audit corpus, plans, tasks) and `frontend/coverage/**`. The `frontend/coverage/**` deletions are a known hazard of `npm run test` (plan-13 front matter). **No production or schema file is dirty.** |
| Report baseline | `0717b65` (report front matter) | HEAD is 3 commits ahead (`cea2d06`→`2174895`→`ab76989`→`863b81b`, plus the report's own `0717b65`). None touches `alembic/`, `db/models/`, or the repositories this phase names. |

The report's own Baseline section records the same dirty shape at `0717b65` and notes a
concurrent peer editing `src/mkobi/config.py`. That edit is committed in `863b81b`; both anchors
the report cites (`config.py:221` `dbname`, `:224` `test_dbname`) resolve as cited.

### 1.3 Alembic head — verified against the live database, not only by reading

`.\Makefile.ps1 migration-status` (read-only `alembic current`, no upgrade) and
`.\Makefile.ps1 psql-c` were run against the running dev stack (`mkobi-db-1` / `bidb` /
PostgreSQL 18.x, compose project `mkobi`).

| Query | Result |
|---|---|
| `alembic current` | `82739c97fde1 (head)` |
| `SELECT version_num FROM alembic_version` | `82739c97fde1` |
| Public tables | 13 (`aggregated_data`, `alembic_version`, `dashboard_access`, `dashboard_filter_values`, `dashboard_filters`, `dashboards`, `filters`, `graphs`, `layouts`, `processing_configs`, `processing_logs`, `registration_requests`, `users`) |
| Chain on disk | 8 revision files, linear, single head `82739c97fde1` — **matches the report exactly** |
| Row counts | `processing_logs` **5**, `aggregated_data` **0**, `users` 8 |

**Head confirmed: `82739c97fde1`.** It is the target any new phase-14 revision must set as
`down_revision`, and it is where the live dev database already sits.

The chain, in order, with the exact `down_revision` read from each file:

| # | Revision | Revises | Body |
|---|---|---|---|
| 1 | `000000000000` `_initial_migration` | `None` | all 13 tables, 6 enum types, 4 triggers, 1 CHECK |
| 2 | `000000000001` `_add_missing_fk_indexes` | `000000000000` | **`pass` / `pass`** |
| 3 | `000000000002` `_add_dashboard_filter_values_table` | `000000000001` | `dashboard_filter_values` + 2 indexes |
| 4 | `4479eb53fd4e` `_remove_unused_success_value_from_` | `000000000002` | rename/recreate/`DROP TYPE` on `processing_status` |
| 5 | `b749bc53b1ee` `_add_processing_logs_status_index` | `4479eb53fd4e` | `CREATE INDEX (status, finished_at)` |
| 6 | `f47ac18b5b9e` `_remove_redundant_dashboard_filters_index` | `b749bc53b1ee` | `DROP INDEX IF EXISTS idx_dashboard_filters_dashboard_id` |
| 7 | `c5d6e7f8a9b0` `_add_processing_logs_started_at_index` | `f47ac18b5b9e` | `CREATE INDEX (status, started_at)` |
| 8 | `82739c97fde1` `_add_error_code_column_to_processing_` | `c5d6e7f8a9b0` | `add_column('processing_logs', 'error_code', String(50))` |

`4479eb53fd4e`'s **downgrade order is different from its upgrade order** — upgrade creates
`('started','uploaded','processing','completed','failed')`, downgrade creates
`('started','uploaded','processing','success','failed','completed')`. This is a real asymmetry
the report does not name, and it is a `MIG-003`-class fact about a *different* revision (§5).

### 1.4 What was verified live vs read only

| Verified against the live database | Read only from disk |
|---|---|
| `alembic current` and `alembic_version` | every `alembic/versions/*.py` body, `alembic/env.py` |
| `pg_indexes` for `processing_logs`, `aggregated_data`, `dashboard_filters` | `src/mkobi/db/repositories/*` predicate construction |
| `pg_constraint` for all `contype IN ('c','u')` | `src/mkobi/db/models/*` `__table_args__` |
| `pg_type`/`pg_enum` for all 6 enum types | `src/mkobi/models/enums.py` |
| `information_schema.tables` (13) | `tests/conftest.py`, `tests/test_starter.py`, `tests/test_enum_db_consistency.py` |
| row counts for 3 tables | `docs/09-database/*`, `Makefile.ps1`, `docker/init-scripts/*` |
| `uv run ruff check alembic/` (host, read-only) | `pyproject.toml`, `AGENTS.md`, `.kilo/rules/*` |

**Not attempted** (and stated as a limit, not a gap): no `EXPLAIN` was re-run, no
`pg_dump` was taken, no temporary probe table was created, no downgrade/re-upgrade cycle was
attempted, no test suite was run.

---

## 2. Per-finding context

Anchor rule for this section: **revision / migration module / model class / table / column /
index or constraint / data type / enum value / model-vs-migration mismatch.** Line numbers appear
only where they are drift evidence.

### MIG-001 — the admin processing-log list's date filter and default sort have no access path

| Item | Anchored value |
|---|---|
| Verdict | **substantiated** (report HIGH; band unchanged) |
| Repository | `ProcessingLogRepository.get_filtered` — `src/mkobi/db/repositories/processing_log_repo.py` |
| Predicates | `dashboard_id` → `ProcessingLog.dashboard_id`; `status` → `ProcessingLog.status`; `date_from` → `started_at >= …`; `date_to` → `started_at <= end_of_day` |
| Sort | **unconditional** `order_by(ProcessingLog.started_at.desc())` — applied whether or not any filter is present |
| Paging | `offset(filters.skip)` then `limit(filters.limit)`; `limit` only when `> 0` |
| Live indexes on `processing_logs` (measured) | `processing_logs_pkey` btree(id) · `idx_processing_logs_dashboard_id` btree(dashboard_id) · `idx_processing_logs_status_finished_at` btree(status, finished_at) · `idx_processing_logs_status_started_at` btree(status, started_at) |
| Model class | `ProcessingLog` — `src/mkobi/db/models/processing_logs.py`, `__table_args__` declares exactly those three non-PK indexes; **no** index leads with `started_at` |
| Model-vs-migration match | **consistent** — the four live indexes are exactly PK + the three declared in the model, created by `000000000000` (dashboard_id), `b749bc53b1ee` (status, finished_at), `c5d6e7f8a9b0` (status, started_at) |
| Rows in the live dev table | **5** (was 3 at the report's baseline) |

**Seams an implementor would touch.** A new revision on top of `82739c97fde1` issuing
`CREATE INDEX … ON processing_logs (started_at)`. The model class **must change in the same
commit** — `ProcessingLog.__table_args__` is the ORM half of the same object, and the
project's own comment at `000000000000:104` / `:247` says indexes are "matching ORM
`__table_args__`". A migration without the model edit produces exactly the drift
`alembic check` is supposed to catch. `downgrade()` carries `DROP INDEX`. No test anywhere
asserts a plan shape (confirmed: no test file matches `migrat|alembic|index`; only
`test_starter.py` and `test_enum_db_consistency.py` are schema-adjacent), so nothing breaks —
and equally nothing verifies the fix.

`VAL-14-001` applies: the report's proof is a static inventory, not the `Sort` node; and with a
`LIMIT` PostgreSQL top-N sorts rather than fully sorting. The **conclusion** and the
**recommendation** survive both corrections.

### MIG-002 — the declared GIN index on `aggregated_data.dims` cannot serve the operator the code issues

| Item | Anchored value |
|---|---|
| Verdict | **substantiated** (report HIGH; band unchanged) |
| Operator the code issues | `->>` — extraction. `AggregatedData.dims[key].astext == str(value)` in a loop over `filters.items()` (renders `(dims ->> 'k') = 'v'`), and `select(distinct(AggregatedData.dims[dim_name].astext))` in `get_dims_values` |
| Repo file | `src/mkobi/db/repositories/aggregated_data_repo.py` — a repository-wide grep for `@>` over the repositories returns **zero hits** |
| Live index (measured `pg_indexes`) | `CREATE INDEX idx_aggregated_data_dims_gin ON public.aggregated_data USING gin (dims)` — no opclass named |
| Resolved opclass | **`jsonb_ops`** (per the report's `pg_opclass` read: membership `? ?& ?| @> @? @@`; `->>` absent) |
| Sibling access path | `uq_aggregated_data_dashboard_graph_dims` — `btree (dashboard_id, graph_id, ((dims)::text))`, an expression index on the whole document's text rendering; cannot serve `->> 'k'` either |
| Remaining index | `idx_aggregated_data_graph_id` btree(graph_id) — single column, no `dims` |
| Model class | `AggregatedData` — `src/mkobi/db/models/aggregated_data.py`; `__table_args__` declares the GIN as `Index("idx_aggregated_data_dims_gin", "dims", postgresql_using="gin")` — **no `postgresql_ops`, so the model and the chain agree and both bind `jsonb_ops`** |
| Rows | `aggregated_data` = **0** in the live dev database (0 in test at the report's baseline) |

**The report's claim that "no `@>`, `?` or `@@` is emitted anywhere against this column" is
independently confirmed** by a repository grep. The opclass-membership argument is a static
catalog fact and does not depend on row count; the *magnitude* does, and remains unmeasurable
while the table is empty.

**Seams.** Dropping `idx_aggregated_data_dims_gin` is a schema migration; making the *code* able
to use an index is `aggregated_data_repo.py`. The report routes the smaller edit to **phase 05**
and keeps the DDL here, and phase 11's `DP-11-E` independently reaches the same place ("(b) Drop
the index — A schema migration — phase 14's"). Whichever side lands, **both the model and the
migration must move together** (`AggregatedData.__table_args__` is the ORM half).
`docs/09-database/indexes.md` §4 asserts the index "enables efficient JSONB containment queries
(`@>`, `?`, `?|`, `?&`)" and that "the backend queries `dims` using JSONB containment operators" —
**false today** — and `schema-processing.md:90` repeats it. Phase 11 `PRF-1` requires that
documentation fix **under every option**, so two phases touch one file.

### MIG-003 — `f47ac18b5b9e` drops an object no revision creates, and its reverse recreates a different object

| Item | Anchored value |
|---|---|
| Verdict | **substantiated on facts 1 and 3; fact 2 is refuted by its own quoted docstring (`VAL-14-003`)** |
| Forward | one statement: `DROP INDEX IF EXISTS idx_dashboard_filters_dashboard_id` |
| Reverse | one statement: `CREATE INDEX IF NOT EXISTS idx_dashboard_filters_dashboard_id ON dashboard_filters (dashboard_id, filter_id)` — a **two-column** index |
| `idx_dashboard_filters_dashboard_id` repository-wide | **5 hits, all inside `f47ac18b5b9e`** (docstring ×2, forward, docstring in `downgrade`, reverse). No model declares it. |
| Creating revision | `000000000000` creates `dashboard_filters` with `PRIMARY KEY (dashboard_id, filter_id)` and **no** additional index; its comment reads "No additional index needed - PK index already covers all queries" |
| Live table (measured `pg_indexes`) | **exactly one**: `dashboard_filters_pkey btree (dashboard_id, filter_id)` |
| `ON DELETE` on the two FKs | both `CASCADE` (from `000000000000`) |

**The `VAL-14-003` correction is confirmed against the code.** The reverse creates
`(dashboard_id, filter_id)`. The PK is `(dashboard_id, filter_id)`. The docstring's phrase
"covers the same column set as the PK" therefore denotes the **two-column** set, and the
docstring and the reverse **agree**. The only evidence for the single-column reading is the
index *name*, which the finding does not cite. The report's prohibition on branch one
("change the reverse to single-column `(dashboard_id)`") is correct and must survive into the
plan: taking branch one would make the reverse contradict the very prose the finding relies on.

**Seams.** Two shapes, and only one is safe: (i) retire the revision by folding its rationale
into `000000000000`'s docstring — comment-only, no DDL, no downgrade to write; (ii) keep the
revision and **reconcile** the docstring with the reverse. Both are comment-level. Live blast
radius is nil — the index does not exist on any database this chain can build. Nothing in
`docs/09-database/` names the index by that name; `indexes.md:142` names a *different*
object, `idx_dashboard_filters_dashboard_filter`, which **does not exist in code or in the
database** (a doc defect of its own — see §5).

### MIG-004 — the application role and every privilege are established outside the chain

| Item | Anchored value |
|---|---|
| Verdict | **substantiated on the load-bearing half (no `CREATE ROLE` anywhere in the chain); one stated mechanism refuted (`VAL-14-004`)** |
| `alembic/` search for `GRANT\|REVOKE\|CREATE ROLE\|ALTER DEFAULT PRIVILEGES` | **no files found** |
| Outside-chain site 1 | `docker/init-scripts/01-create-app-role.sh` — `CREATE ROLE mkobi_app WITH LOGIN PASSWORD`, `GRANT CONNECT ON DATABASE`, `GRANT USAGE ON SCHEMA public`, table + sequence grants, two `ALTER DEFAULT PRIVILEGES` |
| Outside-chain site 2 | `src/mkobi/db/starter.py` :: `recreate_test_database` — `GRANT CONNECT ON DATABASE` after `CREATE DATABASE`; then `GRANT USAGE, CREATE ON SCHEMA public`, `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES`, `GRANT USAGE ON ALL SEQUENCES`, two `ALTER DEFAULT PRIVILEGES` |
| **Divergence the report names — confirmed** | the shell script grants `USAGE` on the schema; `starter.py` grants **`USAGE, CREATE`**. Two transcriptions of one grant set, differing. |
| Live evidence at report baseline | `pg_dump --schema-only` filtered in place: `CREATE ROLE` = 0, `ALTER DEFAULT PRIVILEGES` = 2, `OWNER TO` = 22, `GRANT … mkobi_app` = 16 |

**Not re-measured here** (no `pg_dump` was run by this context) — the four counts are the
report's measurements at `0717b65`; the code sites were re-read directly. The `VAL-14-004`
correction stands: the forward-looking `ALTER DEFAULT PRIVILEGES` rule **does** survive a
dump/restore round trip; the *role* does not. A restore onto a server whose volume was never
initialised fails on the first `GRANT … TO mkobi_app` and, because `Makefile.ps1:304` runs
`pg_restore` **without `--exit-on-error`**, the restore continues and reports rather than
aborting.

**Seams.** A single referenced SQL artefact must exist **before** the restore path is pointed at
it. `src/mkobi/db/starter.py` is under active phase-03/04 remediation (plan-08 `C08-5`) and
**phase 01 owns `db/starter.py`/`config.py`** — the most contended file in the phase. The "the
role is not part of a dump" note belongs in `docs/10-deployment/deployment.md`. **No migration
can fix this**: creating a role from a revision would need a superuser the chain does not
assume, and the report says so.

### MIG-005 — the only path that creates a database is not in the chain and nothing checks its target

| Item | Anchored value |
|---|---|
| Verdict | **substantiated — but its central premise is now half-fixed; see below** |
| Routine | `DatabaseStarter.recreate_test_database` — `src/mkobi/db/starter.py` |
| Order, as it stands now | environment gate → parse URL → **name gate** → SQL-injection shape check → `pg_terminate_backend` → `DROP DATABASE IF EXISTS` / `CREATE DATABASE` → grants → `_apply_migrations` |
| **Guards that already exist** | `UnsafeTestDatabaseRecreationError` raised when (a) `get_config().environment != TEST`, (b) the target name fails `TEST_DATABASE_NAME_PATTERN = re.compile(r"^bidb_test(_[A-Za-z0-9]+)?$")` |
| Origin of those guards | commit **`8178610` "fix(starter): guard destructive test-database recreation"**, which `git merge-base --is-ancestor` confirms is in HEAD; it changed `src/mkobi/db/starter.py` and `tests/test_starter.py` |
| Pinned by | `tests/test_starter.py::TestRecreateTestDatabaseGuards` — `test_recreates_guarded_test_database`, `test_refuses_production_tier`, `test_refuses_non_test_database_name`, `test_accepts_convention_names` (parametrized over `bidb_test`, `bidb_test_gw0`, `bidb_test_w1`) and `TestRecreateTestDatabaseCliGuard::test_cli_refuses_production_tier` |
| Advisory lock | acquired in `alembic/env.py` (`MIGRATION_ADVISORY_LOCK_KEY = 42`) inside `run_async_migrations`, i.e. **inside the chain replay, strictly after the drop** — the report's placement claim is confirmed |
| Second door | `DatabaseStarter.startup()` calls `recreate_test_database()` when the tier is test or `recreate_test_db` is set; `python -m mkobi.db.starter --recreate-test-db` is the third |

**This is the single most important drift in the phase and it cuts two ways.**

*Against the report:* the finding's observation "nothing checks that its target is a test
database" is **no longer true**. A name-convention gate and an environment gate both exist, they
run **before any statement is issued against the target**, they are pinned by five tests, and
`8178610` is committed. The report's recommended "target-identity check in `config.py`" is
**largely delivered** — though the delivered form is a *regex gate on the name* in
`db/starter.py`, not an *equality check in `config.py`*. The report's own Rollout Safety warns
that an equality check `db_name == config.database.test_dbname` would refuse every xdist run;
the shipped regex `^bidb_test(_[A-Za-z0-9]+)?$` is precisely the answer to that trap, and
`test_accepts_convention_names` pins the worker-suffixed forms.

*For the report:* the **mutual-exclusion half is entirely unaddressed.** Nothing takes a lock
before `pg_terminate_backend`; the only advisory lock is taken later, inside `alembic/env.py`,
on a connection to a database that has by then already been dropped and recreated. Two
concurrent sessions can therefore still interleave through the drop. And because the two
`bidb_test` targets under xdist are *different* databases, a plain advisory lock keyed on the
database would not by itself serialise the fixture.

**Seams.** `src/mkobi/db/starter.py` (`recreate_test_database`) and `tests/test_starter.py`
must move together; both are named in plan-08 `C08-5` as phase-03/04 territory. The
`re.create_test_database` docstring and `docs/06-backend/architecture.md:148-151` document the
guards. The remaining work is a lock acquired **on the target before `pg_terminate_backend`**,
which by construction **cannot** delegate to `alembic/env.py`.

### MIG-006 — `000000000001` performs nothing in either direction

| Item | Anchored value |
|---|---|
| Verdict | **substantiated** (LOW; band unchanged) |
| File | `alembic/versions/000000000001_add_missing_fk_indexes.py` — 28 lines, `upgrade()` is `pass`, `downgrade()` is `pass` |
| Its docstring's claim | "Kept for backward compatibility - existing databases may have already applied the indexes via this migration" |
| The indexes its predecessor already creates | `000000000000`: `idx_dashboards_layout_id`, `idx_dashboards_created_by`, the five `aggregated_data` indexes, `idx_registration_requests_reviewed_by`; plus the remaining unique/FK indexes |
| Live confirmation | measured `pg_indexes` matches the chain exactly on all three probed tables — no extra index exists that this revision could have created |
| Model-vs-migration | consistent; no model declares an index this revision names |

**Seams.** Comment-only: correct the module docstring to state that the indexes are created in
`000000000000` and the revision is a retained no-op. **The identifier must not be renumbered** —
it is a stamped row in `alembic_version` on every deployed database, and a rename orphans that
row. No DDL, no downgrade, no model change, no test change. `docs/09-database/indexes.md:22`
attributes the index set to a *different, non-existent* migration file and will need the same
correction (see §5).

### MIG-007 — `b749bc53b1ee` names, documents and performs three different index shapes

| Item | Anchored value |
|---|---|
| Verdict | **substantiated, with the report's own artefact count corrected** |
| Filename | `b749bc53b1ee_add_processing_logs_status_index.py` — says **`status`** |
| Module docstring title (line 1) | "Add index on processing_logs.**status** for cleanup query performance" — says **`status`** |
| `upgrade()` docstring | "Add **composite** index on processing_logs (status, finished_at) for cleanup queries" — **correct**, and this is why the artefact count is **two**, not three |
| Executed body | `CREATE INDEX IF NOT EXISTS idx_processing_logs_status_finished_at ON processing_logs (status, finished_at)` |
| Live index (measured) | `idx_processing_logs_status_finished_at` btree(status, finished_at) — **composite**; there is no single-column `(status)` index |
| Model class | `ProcessingLog.__table_args__` declares `(status, finished_at)` and `(status, started_at)` and `dashboard_id` — **no** `(status)` |
| `alembic history` output (report) | `b749bc53b1ee -> f47ac18b5b9e, Add index on processing_logs.status for cleanup query performance.` — the misdescription is reproduced in the chain's own reader-facing output |

**Seams.** Comment-only. Correct the **docstring title** (which is what `alembic history`
prints); leave the identifier, the filename, and the `upgrade()` docstring alone. The
`upgrade()` docstring correction is optional because it is already right. No DDL, no model
change. Note that the same file is a phase-11 `PERF-001` adjacency: `cleanup_old_logs` filters
on `finished_at`, which is why the composite leads with `status`.

### MIG-008 — `users_email_length_check` is chain-only, model-silent, and cannot fire

| Item | Anchored value |
|---|---|
| Verdict | **substantiated in all three parts** (LOW; band unchanged) |
| Created in | `alembic/versions/000000000000_initial_migration.py` — a `DO $$ … END $$` block whose guard filters `pg_constraint` on **`conname` alone, with no `conrelid` filter** |
| Live constraint (measured `pg_constraint`) | `users_email_length_check`, `contype = 'c'`, `CHECK ((length((email)::text) <= 255))` |
| Column type | `users.email` is `VARCHAR(255)` in the chain; `String(255)` in `src/mkobi/db/models/user.py` — **the type constraint fires first**, so the `CHECK` has no reachable input |
| Model-side | `CheckConstraint` appears **zero times** across `src/mkobi/**`; `__table_args__` appears 10 times across the ten model modules — the model genuinely cannot see this constraint |
| Drift-gate blindness | `alembic check` compares the **live database** against the **model layer**, never the chain against either; Alembic's autogenerate does not compare `CHECK` constraints. The project's gates are `ruff check src/ tests/` and `mypy src/`, and `pyproject.toml` excludes `alembic/` from mypy — so nothing in the repository would notice. |

**Seams.** One new revision on top of `82739c97fde1` dropping the constraint, with
`downgrade()` re-adding it (and re-adding it **with** a `conrelid` filter in the guard, so the
restored object is correct). Independently, a **comment/guard fix inside `000000000000`** to
add the `conrelid` filter — note this edits an already-applied revision, which changes its
checksum; the report treats it as a text edit to the guard block, which does not re-run
`upgrade` on any existing database. The model layer needs **no** change: the constraint is
model-silent by design, and adding it to `__table_args__` would make it *reappear* in
`alembic check` output. No test asserts the constraint's presence (confirmed: no test file
matches `migrat|alembic|index`).

---

## 3. `VAL-14-*` — validation-level defects, and which change a target

| ID | Severity | Defect | Changes a target? |
|---|---|---|---|
| `VAL-14-001` | LOW | MIG-001's surviving-`Sort` argument proves only that the *chosen* construction needed a sort; `enable_seqscan=off` is a cost penalty, not a prohibition (the report's own Q3 took a `Seq Scan … Disabled: true`). The absence of an ordering index is proven by the four-index `pg_indexes` inventory, not by the plan. The cost sentence overstates: with `LIMIT 100` PostgreSQL top-N sorts. | **No.** MIG-001's target and band are unchanged. The *justification* and one consequence sentence must be restated. |
| `VAL-14-002` | LOW | The report's verification of TOPO-007 misreports its own `ruff` result ("4 errors, all `UP007`"). **Re-run here:** `ruff check alembic/ --output-format concise` returns 4 errors — `UP035` at `82739c97fde1…py:8:1`, `UP007` at `:16:16`/`:17:16`/`:18:13`. | **No.** The conclusion (`alembic/` outside both gates) and the remedy (`ruff check --fix alembic/`) are unaffected. |
| `VAL-14-003` | MEDIUM | MIG-003's fact 2 is refuted by the docstring it quotes: "the same column set as the PK" denotes `(dashboard_id, filter_id)`, which is exactly what the reverse creates. **Verified against the code.** Branch one of the recommendation would install the defect the finding alleges. | **Yes, decisively.** MIG-003's recommendation reduces to "retire, or keep-and-reconcile". The Planner must not reintroduce branch one. |
| `VAL-14-004` | MEDIUM | MIG-004's evidence records a measured absence that is not there: the dump carries **two** `ALTER DEFAULT PRIVILEGES`, not zero, and 22 `OWNER TO`, not 24. The rule **does** survive a restore; the role does not. | **Yes, narrowly.** The second consequence is struck and narrowed. The recommendation is **unchanged** — it concerns the role. |
| `VAL-14-005` | LOW | Five mechanical citations are off: `Makefile.ps1:221→222`, `:229→230`, `config.py:219→221`, `:222→224`, `alembic/env.py:114-127` → acquisition at `:115-117`, `try` at `:113`. | **No.** **Re-measured here:** all five land where `VAL-14-005` says. |

---

## 4. Coverage ledger

| Finding | Verdict | Primary evidence anchor(s) |
|---|---|---|
| MIG-001 | substantiated | `ProcessingLogRepository.get_filtered` unconditional `order_by(started_at.desc())` · live `pg_indexes` on `processing_logs` = 4, none leading with `started_at` · `ProcessingLog.__table_args__` declares 3 non-PK indexes · head `82739c97fde1` |
| MIG-002 | substantiated | `->>` emitted at two `aggregated_data_repo.py` sites · grep for `@>` over `db/repositories/` = 0 hits · live GIN `USING gin (dims)` → `jsonb_ops` · `AggregatedData.__table_args__` names no opclass · `aggregated_data` = 0 rows |
| MIG-003 | substantiated (2 of 3 facts) | forward `DROP INDEX IF EXISTS` · reverse `CREATE INDEX … (dashboard_id, filter_id)` · 5 repo hits all in `f47ac18b5b9e` · `000000000000` PK `(dashboard_id, filter_id)` · live `dashboard_filters_pkey` only |
| MIG-004 | substantiated (load-bearing half) | grep of `alembic/` for `GRANT\|REVOKE\|CREATE ROLE\|ALTER DEFAULT PRIVILEGES` = 0 files · `01-create-app-role.sh` and `db/starter.py` grant sets · `USAGE` vs `USAGE, CREATE` divergence confirmed · `Makefile.ps1:304` `pg_restore` without `--exit-on-error` |
| MIG-005 | substantiated, **premise half-fixed** | `recreate_test_database` now has an env gate + `TEST_DATABASE_NAME_PATTERN` name gate, from commit `8178610` (ancestor of HEAD) · five tests in `test_starter.py` pin them · lock still only in `alembic/env.py`, after the drop · `tests/conftest.py:433` calls it unconditionally |
| MIG-006 | substantiated | `000000000001` `upgrade`/`downgrade` both `pass` · `000000000000` creates every index the name refers to · live index set matches the chain exactly |
| MIG-007 | substantiated (artefact count corrected to 2) | filename says `status` · docstring title says `status` · `upgrade()` docstring says composite (correct) · body creates `(status, finished_at)` · no `(status)` index live or in the model |
| MIG-008 | substantiated | `000000000000` `DO $$` guard filters `conname` without `conrelid` · live `users_email_length_check` = `CHECK ((length((email)::text) <= 255))` · `users.email` `VARCHAR(255)` · `CheckConstraint` = 0 hits in `src/mkobi/**` · `alembic/` excluded from both gates |
| VAL-14-001 | confirmed (no target change) | live index inventory is the proof; `LIMIT` top-N |
| VAL-14-002 | confirmed; re-measured | `ruff check alembic/` → `UP035` at `:8:1`, `UP007` at `:16:16`/`:17:16`/`:18:13` |
| VAL-14-003 | confirmed | PK `(dashboard_id, filter_id)`; reverse creates the same two columns |
| VAL-14-004 | accepted as stated | report's own `pg_dump` counts (2 default-privilege rules, 22 `OWNER TO`) not re-run here |
| VAL-14-005 | confirmed; re-measured | `Makefile.ps1:222`/`:230`; `config.py:221`/`:224`; `alembic/env.py:115-117` |

---

## 5. Cross-cutting architecture and constraints

### 5.1 Model layer versus applied revisions

| Dimension | State |
|---|---|
| Model modules | 10 + `__init__.py` in `src/mkobi/db/models/`: `access`, `aggregated_data`, `dashboard`, `dashboard_filter_values`, `filters`, `graphs`, `layout`, `processing_configs`, `processing_logs`, `registration_request`, `user` |
| `__table_args__` occurrences | **10** — every model declares its indexes in the ORM |
| `CheckConstraint` occurrences in `src/mkobi/**` | **0** — the one `CHECK` in the database is model-invisible (MIG-008) |
| Autogenerate target | `alembic/env.py` imports all 11 model classes, sets `target_metadata = Base.metadata`, and sets `compare_type=True` in both offline and online `context.configure` |
| Chain-vs-model agreement | **12 tables, 13 foreign keys with identical `ON DELETE` actions, 6 native enum types agree in both directions** (the FK and enum halves re-measured here — §5.5). The only divergence of record is the chain-only `users_email_length_check`. |
| The chain's shape | **authored as statements, not derived from the model.** `000000000000` writes raw `op.execute("CREATE TABLE …")` rather than `op.create_table`. This single structural fact produces four of the eight findings (MIG-003, MIG-004, MIG-006, MIG-008) and is not filed separately. |
| Gate coverage of `alembic/` | **none.** `Makefile.ps1:222` is `ruff check src/ tests/`, `:230` is `mypy src/`; `pyproject.toml` excludes `alembic/` from mypy. Re-measured: `uv run ruff check alembic/` returns 4 errors, all in `82739c97fde1…py` (1 `UP035`, 3 `UP007`) — a clean result does not exist, and the gates do not look. |

### 5.2 Naming conventions and the head

Linear, single head, 8 revisions, no branch, no `depends_on`, no `branch_labels` anywhere
(full chain table in §1.3). Naming is mixed and load-bearing: **three zero-padded sequential
placeholders** (`000000000000/1/2`) and **five Alembic-generated 12-hex identifiers**
(`4479eb53fd4e`, `b749bc53b1ee`, `f47ac18b5b9e`, `c5d6e7f8a9b0`, `82739c97fde1`).

**A new phase-14 revision must set `down_revision = "82739c97fde1"`.** Renaming or squashing an
existing identifier orphans its row in `alembic_version` on every deployed database.

### 5.3 `aggregated_data` and JSONB usage

| Property | Value |
|---|---|
| Table | `aggregated_data`, `id BIGSERIAL PRIMARY KEY` |
| Payload | `dims JSONB NOT NULL`, `metrics JSONB NOT NULL` — the "single table, any dashboard, no migrations" design decision at `docs/SPEC.md:114` |
| Model | `AggregatedData` with a `JSONBType(TypeDecorator)` that degrades to `JSON` off PostgreSQL |
| FKs | `dashboard_id` → `dashboards(id) ON DELETE CASCADE`; `graph_id` → `graphs(id) ON DELETE CASCADE` |
| Indexes (live, all 6) | `aggregated_data_pkey` btree(id) · `idx_aggregated_data_dashboard_id` · `idx_aggregated_data_graph_id` · `idx_aggregated_data_dashboard_graph` btree(dashboard_id, graph_id) · `idx_aggregated_data_dims_gin` **GIN (dims) → `jsonb_ops`** · `uq_aggregated_data_dashboard_graph_dims` **UNIQUE btree (dashboard_id, graph_id, ((dims)::text))** |
| The two access paths, and the operators they can serve | GIN/`jsonb_ops`: `? ?& ?| @> @? @@` — **not `->>`**. `uq_…dims::text`: an expression index on the document's whole text rendering — **not `->> 'k'`, not `@>` either** as a prefix match on the column. Neither can serve the operator the repository issues. |
| Write-amplification ranking (phase 11 `M11-9`) | `uq_…dims::text` **83,480 kB at 375,000 rows ≈ 8× the GIN** (9,872 kB), larger than the table's own data; `idx_aggregated_data_graph_id` 2,408 kB. GIN per-row write cost: three published figures disagree by 3× (49.2 / 26.3 / 80.7 B/row) — **no constant exists**. |
| `ON CONFLICT` coupling | the UPSERT conflict target **must** remain `text("((dims)::text)")`; a plain column reference raises `InvalidColumnReferenceError`. Dropping or narrowing the index **silently breaks conflict detection**. |
| Rows in the live dev database | **0** |

### 5.4 Enum types and the retired `success` value

| Type | Live labels (measured) | Source |
|---|---|---|
| `user_role` | `admin, editor, viewer` | `UserRole` |
| `dashboard_permission_level` | `view, edit, admin` | `DashboardPermission` |
| `graph_type` | `bar, line, pie, table` | `GraphType` |
| `filter_type` | `select, multiselect, range, date` | `FilterType` |
| `processing_status` | **`started, uploaded, processing, completed, failed`** — 5 values | `ProcessingStatus` |
| `registration_status` | `pending, approved, rejected` | `RegistrationStatus` |

`src/mkobi/models/enums.py::ProcessingStatus` holds five members: `STARTED`, `UPLOADED`,
`PROCESSING`, `COMPLETED`, `FAILED`. **`SUCCESS` no longer exists in code.** It was created by
`000000000000` and dropped by `4479eb53fd4e` (rename → recreate → retype the column → drop the
old type). Three documents still list it:

| Document | Where |
|---|---|
| `docs/09-database/enums.md` | reference-table row 7, the `ProcessingStatus` code block, the value table, **and** the "PostgreSQL ENUM Types" table at the bottom — four places in one file |
| `docs/09-database/schema-processing.md` | the `processing_status` value list and the status-lifecycle diagram |
| (outside `docs/09-database/`, **not phase 14's**) | `docs/03-processing/processing-api.md` · `docs/04-admin/admin-api.md` · `docs/07-frontend/upload-ui.md` · `docs/00-overview/data-flow.md` · `docs/11-guides/create-dashboard.md` · `docs/03-processing/task-queue.md` · `docs/11-guides/task-queue-migration.md` |

**The last group is not phase 14's.** Phase 05 `C05-6` assigns only `docs/09-database/` here
(`enums.md` + `schema-processing.md`); `docs/03-processing/`, `docs/04-admin/` and
`docs/07-frontend/` fall under phase 05's own narrative and phase 13's client tier.

**A second, unnamed asymmetry in the same revision:** `4479eb53fd4e`'s `upgrade()` creates
`('started','uploaded','processing','completed','failed')` while its `downgrade()` creates
`('started','uploaded','processing','success','failed','completed')` — the value order differs
between the two directions, so a downgrade/re-upgrade cycle does not restore the original
`enumsortorder`. No report names this. It is a `MIG-003`-class fact in a different file.

**The tripwire:** `tests/test_enum_db_consistency.py::TestProcessingStatusEnumConsistency::test_processing_status_values_match`
asserts **both** directions — `missing_in_db` and `extra_in_db` must be empty. It is currently
green because the code and the database both hold five values. **Re-adding `SUCCESS` to
`models/enums.py` without a migration would fail it**, which is exactly the sequencing
constraint phase 05 records: a new `ProcessingStatus` member is phase 14's migration.

### 5.5 Index inventory, foreign keys, cascade behaviour

**13 foreign keys, all `ON DELETE` actions measured (live) and matching the model layer:**

| Table | FK | Action |
|---|---|---|
| `dashboards` | `created_by` → `users(id)`, `layout_id` → `layouts(id)` | `SET NULL` ×2 |
| `graphs` | `dashboard_id` → `dashboards(id)` | `CASCADE` |
| `dashboard_access` | `user_id`, `dashboard_id` | `CASCADE` ×2 |
| `dashboard_filters` | `dashboard_id`, `filter_id` | `CASCADE` ×2 |
| `dashboard_filter_values` | `dashboard_id` | `CASCADE` |
| `processing_configs` | `dashboard_id` | `CASCADE` |
| `aggregated_data` | `dashboard_id`, `graph_id` | `CASCADE` ×2 |
| `processing_logs` | `dashboard_id` | `SET NULL` |
| `registration_requests` | `reviewed_by` | `SET NULL` |

Deleting a dashboard cascades to `graphs`, `dashboard_access`, `dashboard_filters`,
`dashboard_filter_values`, `processing_configs` and `aggregated_data` — **the aggregate payload
is destroyed with the dashboard.** No phase-14 finding touches retention, but any `ordinal`
column (phase 05 `C05-5`) lives inside that cascade.

`pg_constraint` for `contype IN ('c','u')` across the whole schema returns exactly **two** rows:
`registration_requests_email_key` (UNIQUE on `email`) and `users_email_length_check` (MIG-008).
There is no other `CHECK` anywhere.

### 5.6 Bootstrap paths, the seeder, and how a schema is recreated

| Path | Mechanism |
|---|---|
| Dev / production compose | a one-shot `migrate` service runs `alembic upgrade head`; `app` depends on it with `condition: service_completed_successfully`; `AUTO_MIGRATE` is off everywhere in the shipped compose |
| Application start-up | `DatabaseStarter.startup()` → verify revision → `ensure_admin_user()` → dev seeders → stale temp-file cleanup → `cleanup_old_logs()` → `recreate_test_database()` if the tier is test |
| **Dev seeder** | `run_dev_seeders()` in `src/mkobi/db/dev_seeders.py` calls `ensure_test_media_dash()`; runs **only** on the `DEVELOPMENT` tier and swallows its own errors. Writes `dashboards`/`graphs`/`layout`/`processing_configs` rows on every dev boot |
| **Test bootstrap** | `tests/conftest.py::setup_test_database` (`scope="session"`) builds a **worker-isolated** `f"bidb_test{worker_suffix}"` under xdist, sets `recreate_test_db=True`, and calls `DatabaseStarter(...).recreate_test_database()` **directly** — a door independent of the ASGI lifespan. The chain is then replayed by `_apply_migrations` |
| Per-test isolation | `async_db_session` uses the SAVEPOINT pattern (`begin_nested()` before yield, `rollback()` in `finally`) |
| `test-fresh` | `Makefile.ps1::Invoke-TestFresh` = `Invoke-TestReset` + `Invoke-Test`; wipes the test **volumes** and rebuilds |
| **`.\Makefile.ps1 test`** | **recreates the schema itself, every session**, through the conftest fixture |

**The mechanism that matters for this phase:** a phase-14 revision lands in the test tier with
no separate migration step, because the chain is replayed from scratch every session. Cheap
rollout, cheap blast radius — but the suite then exercises only `upgrade`, from `base` upward,
never incrementally from the current head and never `downgrade`.

### 5.7 Seam ownership — which sibling phase owns what

| Seam | Owner phase | Hand-over evidence |
|---|---|---|
| `uq_aggregated_data_dashboard_graph_dims` DDL (83 MB, ~8× GIN) | **phase 05** (defect `DP-003`/`PB-5`/`PB-15`) + **phase 14** (the DDL) | plan-11 `C11-9`, `R-11-8`, `DP-11-J`; plan-05 `C05-5` |
| `aggregated_data.ordinal` column DDL + its `schema-core.md` reference | **phase 14** | plan-05 `C05-5`, `PB-15`, `DP-017` |
| Dropping `idx_aggregated_data_dims_gin` | **phase 14** (migration), ruled by **phase 11** `DP-11-E` | plan-11 `R-11-5`, `PRF-1` option (b) |
| `docs/09-database/` (retired `success`, index inventory, phantom-file attribution) | **phase 14** | plan-05 `C05-6`, `C05-13`; plan-04 handover table; plan-08 `CQLT-9` |
| A new `ProcessingStatus` member's enum migration | **phase 14** | plan-05 `PB-16` / `C05-6` |
| `ProcessingLog.artifact_filename` / `.cleanup_error` DDL | **phase 14** | plan-06 `R-06-7`, `C06-3` |
| The Alembic model-vs-chain drift **question** (vs phase 08's gate) | **phase 14** | plan-08 `C08-4`, `D-10`, `CQLT-6` |
| Whether `alembic/` sits under `ruff`/`mypy` | **phase 08** | report's TOPO-007 adjudication |
| The privilege DDL for the app role | **contested**: plan-03 `C-6` names phase 14 as the alternative home; MIG-004 names phase 14 | plan-03 `C-6` |
| `db/starter.py` itself | **phase 01** (config/starter) + **phase 03/04 series** | plan-08 `C08-5`; brief |
| `TXN-001` transaction ownership | **closed** — landed `2174895` | brief |
| `test-fresh` sequencing if a migration lands mid-phase | execution is phase 14's; the note is phase 05/06's | plan-05 §routing |
| `docs/14-schema-migrations/*` (plan-08's named SSOT for migration workflow) | **phase 14** owns the subject; the directory **does not exist** | plan-08 verification row |
| `docs/SPEC.md` §16.2 "7 core indexes" | cited by `indexes.md`; **no such section exists** — phase 14's doc debt | §7.2 |

---

## 6. In-flight and already-landed work intersecting this phase

| Commit / state | Touches | Relation to phase 14 |
|---|---|---|
| `863b81b` (HEAD) | `db/advisory_lock.py`, `workers/data_worker.py`, `docs/06-backend/configuration.md`, `tests/test_advisory_lock.py`, `tests/test_config.py` | **None.** Introduces a *second*, unrelated advisory-lock subsystem. It does **not** touch `alembic/env.py`'s `MIGRATION_ADVISORY_LOCK_KEY = 42` and does not touch `db/starter.py`. The two lock namespaces are unrelated and must not be merged. |
| `ab76989` (parent) | `db/advisory_lock.py` (new, 169 lines), `workers/data_worker.py` | **None** directly — the declared lock is for the **aggregate rebuild**, not migrations. Phase 11 `PRF-10` must not introduce a second wait ceiling against it. |
| `2174895` | `api/deps.py`, `api/routes/admin.py`, `db/session.py`, `services/user_service.py` | **None** schema-side. It is the set-based-write region peers reported as dirty — now committed, tree clean. |
| `cea2d06`, `b646ef1`, `9a77625`, `a92b546`, `c4c0b14` | process topology, worker, lease, docs | **None.** `c4c0b14` records TOPO-001…008 in documentation — the phase-01 record the phase-14 report's TOPO-004 adjudication says must be corrected. |
| **`8178610`** | `db/starter.py`, `tests/test_starter.py` | **Directly intersects MIG-005** — delivers the target-identity half (env gate + `TEST_DATABASE_NAME_PATTERN` + 5 guard tests). Confirmed an ancestor of HEAD. |
| `4a4f9d1` | model + `c5d6e7f8a9b0` | Origin of `idx_processing_logs_status_started_at`, one of `processing_logs`' four indexes. |
| `2ea304e` | `cleanup_old_logs` switched `started_at` → `finished_at` | **Explains why** `b749bc53b1ee` and `c5d6e7f8a9b0` have the shapes they do. |
| `53f62d4`, `96459cb` | `f47ac18b5b9e` docstring | **Directly intersects MIG-003** — "created externally (e.g., manually or via a non-versioned migration)" *is* the finding. Two commits wrote the same prose. |
| Working tree | 41 deletions + 14 untracked, **all under `.ai/` and `frontend/coverage/`** | **No production file was dirty at audit start.** The `frontend/coverage/**` deletions are a known side-effect of `npm run test` (plan-13 front matter), phase 13's. |
| **Newly appeared mid-audit** | `M src/mkobi/workers/data_worker.py` (+69/-21) | A peer's uncommitted edit, **not** the set-based write region the brief described. Read via `git diff`: it moves the terminal `COMPLETED` transition into the same transaction as the aggregate write, and re-orders the `ab76989` advisory lock relative to the failure handler. **No schema, index, model, column, or migration change.** It touches the transaction boundary that phase 03 `B2`/`B3` and phase 05 `PB-14` also name. **Phase-14 impact: none** — but the same file was clean at the start of this run, so the tree is *moving*. |

---

## 7. Discrepancies and risks

### 7.1 Stale anchors and refuted claims

| Claim | Status | Correct value |
|---|---|---|
| "HEAD is `ab76989`" (brief) | **stale** | HEAD is `863b81b`; `ab76989` is the parent |
| "uncommitted production edits in a set-based write region" | **stale** | Scoped `git status` was **empty** at audit start; those edits landed in `ab76989` / `2174895`. A **different** edit (`data_worker.py`, transaction + lock) appeared mid-run — no schema symbol. |
| MIG-005: "nothing checks that its target is a test database" | **drifted → half-fixed** | `recreate_test_database` has an environment gate **and** `TEST_DATABASE_NAME_PATTERN = ^bidb_test(_[A-Za-z0-9]+)?$`, both before any statement, from `8178610`, pinned by 5 tests. The **mutual-exclusion** half is untouched. |
| MIG-005's `starter.py` anchors (`:193-296`, `:208-209`, `:244-251`, `:254-259`, `:261-283`, `:294`) | **stale** | the function now spans `:207-350`; env gate `:230-236`; name gate `:250-256`; injection-shape check `:259-260`; `pg_terminate_backend` `:297-304`; `DROP`/`CREATE` `:307-312`; grants `:315-337`; `_apply_migrations` `:348`. Every **symbol** exists; every **number** moved. |
| MIG-001's `processing_log_repo.py:163-228` anchors | **hold** | `get_filtered` at `:163-228`; predicates `:183/:189/:194/:199`, `order_by` `:206`, `offset`/`limit` `:208-212` — all as cited |
| MIG-002's `aggregated_data_repo.py:161`, `:268` | **hold** | both `->>` sites resolve; repo-wide grep for `@>` = 0 hits |
| `VAL-14-002`'s correction | **confirmed by re-measurement** | `ruff check alembic/ --output-format concise` → `UP035` at `:8:1`, `UP007` at `:16:16`/`:17:16`/`:18:13` |
| `VAL-14-005`'s five corrections | **confirmed by re-measurement** | `Makefile.ps1:222`/`:230`; `config.py:221`/`:224`; `pg_advisory_lock` at `alembic/env.py:115-117` |
| MIG-007: "three artefacts disagree" | **refuted by the report itself** | **two** — filename and docstring title. The `upgrade()` docstring is the one artefact that is correct. |
| MIG-003 fact 2 | **refuted** (`VAL-14-003`) | the reverse creates `(dashboard_id, filter_id)`, matching the PK and the docstring's own words |
| MIG-004: "zero `ALTER DEFAULT PRIVILEGES`" | **refuted** (`VAL-14-004`) | 2 in the dump; the rule survives a restore; the *role* does not |
| Phase 01's `VAL-002` citing `alembic/versions/20250915_0004_*.py` | **file does not exist** | confirmed here too. Phase 01 owns that repair. |
| MIG-001's "3 rows in `bidb`" | cosmetic | now **5** |

### 7.2 Symbols the report names that do not exist today

| Symbol named by a report or doc | Reality |
|---|---|
| `idx_dashboard_filters_dashboard_filter` (named in `docs/09-database/indexes.md:142`, not by a finding) | **Does not exist** in code or database; the real object is `dashboard_filters_pkey` |
| `alembic/versions/7130ecb0388c_true_initial_migration.py` (`indexes.md:22` says it creates every index) | **Does not exist** in this working tree — only in the unrelated worktree `.kilo/worktrees/lowly-principal/` and in old history. The real file is `000000000000_initial_migration.py` |
| `docs/SPEC.md` "section 16.2" (cited twice by `indexes.md`) | **No such section.** `SPEC.md` has 8 `##` headings: Purpose, Technology Stack, Architecture, Main Data Flow, Roles & Permissions, Documentation Index, Key Design Decisions, Version History. The "7 core indexes" claim has no source. |
| `docs/14-schema-migrations/*` (plan-08's named SSOT for the manual migration workflow) | **Directory does not exist** |

### 7.3 Contested ownership

| Contested item | Positions | State |
|---|---|---|
| The privilege DDL for the app role | plan-03 `C-6` names **phase 14** the alternative home; plan-03 `B8` also carries it | **Unresolved.** MIG-004's recommendation (a single referenced SQL artefact + a deployment-doc note) fits both, and is explicitly **not a migration** — a revision cannot create a role without a superuser the chain does not assume. |
| Whether `alembic/` enters the lint/typecheck gates | report's TOPO-007 adjudication: **phase 08** | Settled. Phase 14 does not re-file. |
| `db/starter.py` | **phase 01** (brief) / **phase 03 `B10`** + the 03/04 series (plan-08 `C08-5`) | **The most contended file in the phase** — MIG-004's second grant site and MIG-005's remaining work both live in it. Re-read immediately before any edit. |
| The model-vs-chain drift question | plan-08 gives it a gate (`CQLT-6`), hands the question here (`C08-4`) | Settled. Phase 08 must not answer it. |
| `uq_…dims::text` write cost | plan-11 `DP-11-J`: **Coordinator**, with phase 05 and phase 14 | **Open.** Plan-11's own reading is (a) phase 05 prices it, phase 14 owns any DDL. Unruled. |

### 7.4 Tests that will break

| Test | Breaks when | Why |
|---|---|---|
| `test_enum_db_consistency.py::TestProcessingStatusEnumConsistency::test_processing_status_values_match` | a `ProcessingStatus` member is added **without** a matching `processing_status` migration | asserts **both** directions; `extra_in_db` and `missing_in_db` must both be empty |
| `test_enum_db_consistency.py::TestAllMappedEnumsConsistency::ENUM_MAPPINGS` | same, for the three mapped types | the cross-tier home for a new code |
| `test_starter.py::TestRecreateTestDatabaseGuards` (5 tests) | MIG-005's mutual-exclusion half adds a lock **before** `pg_terminate_backend` | `test_recreates_guarded_test_database` asserts the positive path executes; `test_refuses_production_tier` and `test_refuses_non_test_database_name` assert **`factory.calls == []` and `factory.statements == []`** — a lock taken *before* the gate checks breaks the refusal tests; one taken *after* the gates but *before* `pg_terminate_backend` preserves them. `test_accepts_convention_names` pins `bidb_test`, `bidb_test_gw0`, `bidb_test_w1` — the exact xdist forms the report warns about. |
| `test_starter.py::TestRecreateTestDatabaseCliGuard::test_cli_refuses_production_tier` | the same | same shape |
| `test_advisory_lock.py` | a migration lock were routed into `db/advisory_lock.py` | `863b81b` just made its leak guard non-vacuous; not this phase's to disturb |
| `test_data_worker.py` | phase 11 `PRF-10` lands a set-based write | carries `ab76989`'s lock and bounded-wait assertions; must stay green |

**Nothing pins an index definition, a plan shape, a migration identifier, or a `CHECK`
constraint.** A test file matching `migrat|alembic|index` does not exist. This cuts both ways:
a phase-14 revision breaks nothing, and equally **nothing verifies it landed correctly** except
the next `.\Makefile.ps1 test`, which replays the chain from scratch.

### 7.5 Migration hazards specific to this phase

| Hazard | Concrete instance in this phase | Severity |
|---|---|---|
| **Irreversibility** | `4479eb53fd4e` renames the enum type and drops the old one. A failure between `CREATE TYPE processing_status` and `DROP TYPE processing_status_old` leaves **two** types; a failure after the retype but before the drop leaves a live `processing_status_old`. PostgreSQL wraps the migration in one transaction, so a hard failure rolls back — but the sequence is four unguarded statements with no `IF EXISTS` on the `ALTER TYPE … RENAME`. | **HIGH** |
| **Lock duration on a live table** | `CREATE INDEX` without `CONCURRENTLY` takes a `SHARE` lock that **blocks writes** for the whole build. On `processing_logs` (5 rows) that is instantaneous. On `aggregated_data` — 375,000 rows and 83 MB of index per phase 11 — it blocks every UPSERT for the duration, and `CONCURRENTLY` **cannot run inside an Alembic transaction**, which is this project's whole model (`env.py` opens one). **Unresolved tension; a real decision point.** | **HIGH** |
| **Back-fill volume** | The only back-fill in the current chain is the zero-row enum retype. Phase 05's `C05-5` (`aggregated_data.ordinal` back-filled from the current `id` order) would be the phase's **first** real back-fill, over a table measured at 375,000 rows. Not this phase's work, but the phase that writes the revision. | **MEDIUM** |
| **Downgrade absence** | `000000000001` is a no-op both ways (MIG-006). `f47ac18b5b9e`'s reverse cannot restore a prior state (MIG-003). `4479eb53fd4e`'s reverse restores a **different value order**. **No test anywhere exercises any `downgrade()`.** A new revision with a hand-written `downgrade()` is unverifiable by the suite. | **MEDIUM** |
| **The suite recreates the schema itself** | `.\Makefile.ps1 test` drops and rebuilds `bidb_test*` every session via `conftest.py:433`. A migration is therefore exercised on **every run** — but only `upgrade`, only from `base` upward, never incrementally from head. **An `upgrade` that works from `base` but not from the current head will pass the suite and fail in production.** | **HIGH** |
| **Model/chain half-migration** | A revision that adds an index without adding it to `__table_args__` leaves `alembic check` reporting drift forever. The project's own comment at `000000000000:104` treats the two as a pair. | **MEDIUM** |
| **Identifier immutability** | Three revisions are zero-padded placeholders, five are generated hex. Renaming any orphans its `alembic_version` row. MIG-006 and MIG-007 both correctly refuse renumbering. | **MEDIUM** |
| **Restore is not atomic** | `Makefile.ps1:304` runs `pg_restore --clean --if-exists` **without `--exit-on-error`**, so MIG-004's failed-`GRANT` case is reported and the restore continues: schema and data land, the role does not, the application cannot connect, and only a non-zero exit would signal it. | **MEDIUM** |

---

## 8. Decision points for the Planner

Genuine technical uncertainty. **This context picks none of them.**

| # | Question | Alternatives | Chooser | Blocked while unruled |
|---|---|---|---|---|
| **D-14-A** | **MIG-005's remaining work: what mutual exclusion, and where is it acquired?** | (a) a `pg_advisory_lock` keyed on the target database, taken on the `postgres` admin connection **after** both guards and **before** `pg_terminate_backend` — preserves `test_refuses_*`'s `factory.calls == []`; (b) a lock keyed on the derived `db_name` so `bidb_test_gw0` and `gw1` do not serialise against each other; (c) an idempotency marker — refuse to recreate a database already at head | **Tech Lead** (file is phase 03/04 territory, plan-08 `C08-5`) | MIG-005's second half. The first half is already delivered by `8178610`. |
| **D-14-B** | **MIG-002 / phase 11 `DP-11-E`: drop `idx_aggregated_data_dims_gin`, or keep it?** | (a) documentation only (phase 11 `PRF-1`'s default); (b) drop it — a migration **here**; (c) change the repository to emit `@>` — **explicitly rejected by phase 11's measurement** (`@>` is 2.5–8.1× *slower* in both shapes) | **Tech Lead**, with phase 05 and phase 11 | The migration. Phase 11's `PRF-1` documentation fix is required under every option. |
| **D-14-C** | **`uq_aggregated_data_dashboard_graph_dims` (83 MB, ~8× the GIN) — narrow, hash, drop, or leave?** | (a) leave, let phase 05's `DP-003` canonicalisation absorb it; (b) narrow the expression; (c) hash it instead of indexing `dims::text`; (d) drop — **silently breaks UPSERT conflict detection**, phase 11 `PRF-10`'s conflict target | **Coordinator**, with phase 05 and phase 14 (= plan-11 `DP-11-J`, unruled) | Anything touching the write path. `R-11-8` currently forbids phase 11 doing it. |
| **D-14-D** | **MIG-003: retire `f47ac18b5b9e`, or keep it and reconcile the docstring?** | (a) retire — fold the rationale into `000000000000`'s docstring; (b) keep the revision, correct the docstring to match the reverse; (c) change the reverse to single-column — **barred by `VAL-14-003`**, it would install the defect the finding alleges | **Tech Lead** | Nothing; executable either way once ruled. |
| **D-14-E** | **MIG-008: is the `conrelid` guard fix an edit to `000000000000`, or a new revision?** | (a) edit `000000000000`'s guard text in place — the block does not re-run `upgrade` on existing databases, so it is a no-op there; (b) leave `000000000000` frozen and document the defect instead | **Tech Lead** | The revision that drops the constraint lands either way; only the guard fix turns on this. |
| **D-14-F** | **Does a phase-14 revision need `CREATE INDEX CONCURRENTLY`, and how does that survive `env.py`'s transaction?** | (a) plain `CREATE INDEX`, accept the write lock, rely on the table being small **today**; (b) `CONCURRENTLY` with `autocommit_block()` — supported by Alembic but fragile in an async `env.py`; (c) plain `CREATE INDEX` plus an operator runbook window | **Tech Lead**, with a Researcher on Alembic 1.x async `CONCURRENTLY` support | Any index change on `aggregated_data`. **Cheap for MIG-001 (5 rows); expensive for `aggregated_data`.** |
| **D-14-G** | **The `docs/09-database/` debt exceeds `C05-6` — does this phase absorb it all?** Unowned by any report: the phantom `7130ecb0388c` file, the non-existent SPEC §16.2, the non-existent `idx_dashboard_filters_dashboard_filter`, and the GIN containment claim. | (a) absorb all — the directory is phase 14's and the claims are false today; (b) absorb only `C05-6`'s two files and file the rest; (c) treat the containment claim as phase 11 `PRF-1`'s, since that plan requires it fixed under every option | **Tech Lead** | The documentation half of MIG-002 and of MIG-006's index attribution. |
| **D-14-H** | **Does the phase write a drift answer, or only take phase 08's gate?** plan-08 `C08-4` hands the question here and forbids itself from answering it. | (a) run `alembic check` once, record it, answer only "does the chain match the model today"; (b) add a gate as well — **duplicating `CQLT-6`**; (c) decline and say so | **Tech Lead**, with phase 08 | The `QLT-004` / `C08-4` hand-over closes only on (a) or (c). |

