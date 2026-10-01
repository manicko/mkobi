---
phase: 14-schema-migrations
executed: 2026-09-30
executor: auditor
problems-only: true
baseline: 05f2779323c1746c8945f63882b187bcb2d7b608
baseline-dirty: "true — M src/mkobi/workers/data_worker.py, M tests/test_file_cleanup.py, D .ai/builders/**, D .ai/structure/**, D .ai/models/**, D .ai/plans/audit-fix-plan.md, D .ai/templates/**, D frontend/coverage/**, ?? .ai/audit/**"
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 3
  LOW: 3
---

# Phase 14 — Findings

## Summary

The declared schema state and its evolution were examined: the eight-revision Alembic chain read as a
graph, each revision against its own reverse, the eleven SQLAlchemy models against the chain as two
declarations of one schema, the chain-owned objects the model layer cannot express, the six
native enum types against `models/enums.py`, the index inventory against the predicates the
repositories actually issue, thirteen foreign keys against their declared `ON DELETE` actions, the
schema source of each of the four environments the deployment offers, and the chain's residue. Eight
findings; the most consequential is that **two of the schema's declared access paths are structurally
incapable of serving the operators the code issues against them** — proven on a live PostgreSQL 18
instance with `enable_seqscan=off` and `enable_bitmapscan=off`, not inferred from a cost model. The
chain itself is structurally sound: one head, no branch, every declared predecessor resolves, and
every column, key, foreign key and `ON DELETE` action agrees between the model layer and the chain on
all twelve tables and thirteen relationships. What the chain does not carry is the application's
role and privileges, and the only code path that creates a database — both established outside the
chain, both recorded nowhere. Four prior findings (TOPO-004, TOPO-007, QLT-008, TST-012) are
adjudicated in the Cross-Finding Analysis rather than re-filed; two of them rest on a premise this
phase's evidence corrects.

## Findings

### MIG-001 — The admin processing-log list's date filter and default sort have no access path that can produce that order

**Severity** — HIGH

**Zone** — "The Index Inventory against the Predicates the Code Actually Issues"

**Observation** — `GET /api/v1/admin/logs/` builds its query in
`db/repositories/processing_log_repo.py:163-236` (`get_filtered`). Every predicate it can issue is
optional. The route at `api/routes/processing_logs.py:36-93` defaults `dashboard_id`, `status_filter`
and both date bounds to `None`, and defaults to `ORDER BY started_at DESC` (repo line 206) with
`OFFSET`/`LIMIT` (lines 208-212). The only two indexes in the schema that contain `started_at` are
`idx_processing_logs_status_finished_at (status, finished_at)` and
`idx_processing_logs_status_started_at (status, started_at)` — both created by the chain
(`alembic/versions/b749bc53b1ee_...py:22-25`, `c5d6e7f8a9b0_...py:22-25`) and both declared in the
model layer (`db/models/processing_logs.py:74-81`). `started_at` is the **non-leading** column in
both, so neither can supply an ordering over `started_at` when `status` is unconstrained. There is
no index on `started_at` alone.

Against the live development database I forced the planner to reject every alternative it has:

```
SET enable_seqscan=off; SET enable_bitmapscan=off;
EXPLAIN (COSTS OFF) SELECT * FROM processing_logs
  WHERE started_at >= '2026-01-01' ORDER BY started_at DESC LIMIT 100;
```
```
 Limit
   ->  Sort
         Sort Key: started_at DESC
         ->  Index Scan using idx_processing_logs_status_started_at on processing_logs
               Index Cond: (started_at >= '2026-01-01 00:00:00+00'::timestamp with time zone)
```

The `Sort` node survives both settings off. The only plan the planner can construct is a full
traversal of the composite index followed by a sort of everything it read — the index is used as a
heap-visitor, not as an ordering source. Adding `status = 'failed'` to the same query eliminates the
`Sort` entirely (`Index Scan Backward using idx_processing_logs_status_started_at`, both scan types
still disabled), which isolates the cause to the missing leading `status` equality and nothing else.
With no filters at all — the endpoint's default call — the plan is `Seq Scan` + `Sort` with both scan
types disabled.

**Evidence** — the three `EXPLAIN` outputs above, reproduced read-only against `mkobi-db-1` /
`bidb` at revision `82739c97fde1`; the index inventory read from `pg_indexes`; the optionality of
every predicate at `processing_logs.py:36-58`; the query construction at
`processing_log_repo.py:194-212`.
**Consequence** — today the table holds 3 rows in the development database and 5 in the test
database (`SELECT count(*) FROM processing_logs`), so the sort is free and nothing is observably
slow. The
endpoint's cost is not the row count but that it is **structurally** a sort-everything query: it
re-reads and re-sorts the whole `processing_logs` table on every page, and `OFFSET` pagination
repeats that work per page. `processing_logs` is the one table in this schema that grows without a
size bound of its own — `db/starter.py:395-418` prunes only rows in terminal states older than
`LOGS_RETENTION_DAYS` (default 30), and rows in `started`/`uploaded`/`processing` are never pruned by
that statement. The exposure scales with ingest rate and retention window, and the endpoint is
admin-only, which is the sole reason this is not worse.

**Recommendation** — add one index that leads with the sorted column, via a new revision on top of
`82739c97fde1`: `CREATE INDEX idx_processing_logs_started_at ON processing_logs (started_at DESC)`.
That single index serves the default call, the date-range call and the `ORDER BY` in all three of
them; with a `status` equality the planner will combine it by bitmap-AND with the existing composite.
The direction matters more than the exact form: the defect is that no access path in the schema
begins with the column the query is ordered by, so any future filter combination on this endpoint
inherits the same sort. No shipped test asserts the current plan shape, so nothing is a remediation
blocker.

### MIG-002 — The declared GIN index on `aggregated_data.dims` cannot serve the only JSONB operator the application issues

**Severity** — HIGH

**Zone** — "The Index Inventory against the Predicates the Code Actually Issues"

**Observation** — the only JSONB predicate the application issues against a structured document
column is extraction, not containment. `db/repositories/aggregated_data_repo.py:161` builds
`AggregatedData.dims[key].astext == str(value)` inside the filter loop of `get_by_graph_id`, and
line 268 builds `select(distinct(dims[dim_name].astext))` in `get_dims_values`. Both render as
`dims ->> 'k' = 'v'`. The schema declares one access path over that column:
`CREATE INDEX idx_aggregated_data_dims_gin ON aggregated_data USING GIN (dims)`
(`alembic/versions/000000000000_initial_migration.py:209-211`), declared identically in
`db/models/aggregated_data.py:53` as `Index("idx_aggregated_data_dims_gin", "dims",
postgresql_using="gin")`. Because no `jsonb_path_ops` and no operator class is named, PostgreSQL
binds the default GIN opclass for the type, `jsonb_ops`, whose members are the containment and
existence operators only.

I proved the mismatch on a live PostgreSQL 18 instance using a temporary table, which is
session-local and leaves nothing behind:

```
CREATE TEMP TABLE mig14_probe (id bigserial primary key, dims jsonb NOT NULL);
CREATE INDEX mig14_probe_gin ON mig14_probe USING gin (dims);
SET enable_seqscan = off;
```
| operator issued | plan under `enable_seqscan=off` |
|---|---|
| `dims ->> 'k' = 'v'` (what the code emits) | `Seq Scan on mig14_probe` / *Disabled: true* / `Filter: ((dims ->> 'k') = 'v')` |
| `dims @> jsonb_build_object('k','v')` (what the GIN index can serve) | `Bitmap Heap Scan` → `Bitmap Index Scan on mig14_probe_gin` |

With sequential scanning disabled the planner has nothing to offer for the operator the code emits
and falls back to a disabled sequential scan with the predicate as a residual filter. The same
index serves `@>` immediately. The declared access path is not merely unused on this path; it cannot
be used on it.

**Evidence** — the two `EXPLAIN` outputs above against `mkobi-test-test-db-1` / `bidb_test`; the
operator class identity confirmed in `pg_opclass` (`gin` / `jsonb_ops`); the emitted SQL at
`aggregated_data_repo.py:161` and `:268`; the index definition at
`000000000000_initial_migration.py:209-211` and its model-layer twin at
`db/models/aggregated_data.py:53`.

**Consequence** — `idx_aggregated_data_dims_gin` is paid for on every insert, update and delete of
`aggregated_data` — `jsonb_ops` indexes every key and every value in the document, so write cost
scales with document size — and returns nothing on the only predicate the application issues against
that column. `get_by_graph_id` is the hot dashboard read path and it applies the extraction
predicate once per caller-supplied filter key (`for key, value in filters.items()`), so the
degradation is per-filter-key, not per-request. `aggregated_data` is empty in both live databases at
this baseline (0 rows in `bidb`, 0 in `bidb_test`), so the present measurable cost is the write
side only; the read side becomes visible on the first real upload. I am not claiming a btree
expression index is warranted — phase 11 measured the project's own documented recommendation and
refuted it, and that measurement is not re-litigated here. The finding is the structural one: what
the schema declares and what the code issues do not match, and the declared half is inert.

**Recommendation** — decide which operator the read path is meant to use and make the schema state
it. If extraction is the intended operator, `jsonb_path_ops` is still not the answer (it serves
`@>`, not `->>`); either the repository emits `@>` / `?|` so the existing index becomes usable, or
the GIN index is dropped as residue it never was. Both directions are correct; what is not correct
is leaving a write-amplifying index declared for an operator no code emits. The repository change
is the smaller of the two edits and lands in phase 05's territory, so this should be scheduled with
that phase rather than as a standalone schema fix.

### MIG-003 — `f47ac18b5b9e` drops an object no revision creates, and its reverse recreates a different object

**Severity** — MEDIUM

**Zone** — "Each Revision's Reverse against Its Forward"

**Observation** — the chain is linear, so this revision's forward and reverse are directly
comparable. Forward (`alembic/versions/f47ac18b5b9e_remove_redundant_dashboard_filters_index.py:36`)
performs one statement: `DROP INDEX IF EXISTS idx_dashboard_filters_dashboard_id`. Reverse (lines
50-52) performs one statement: `CREATE INDEX IF NOT EXISTS idx_dashboard_filters_dashboard_id ON
dashboard_filters (dashboard_id, filter_id)`. Three facts make the pair asymmetric:

1. **No revision creates the forward's target.** `000000000000` creates
   `dashboard_filters` with `PRIMARY KEY (dashboard_id, filter_id)` (lines 167-175) and creates no
   further index on the table. `000000000001`, the only other revision touching FK indexes, is a
   no-op. The model layer declares no index on `dashboard_filters` at all — the association `Table`
   at `db/models/filters.py:84-87` carries only its primary key. So on every database this chain can
   build, the forward is a statement against an object that was never there.
2. **The reverse creates a different object than the forward removed.** The module docstring
   (lines 5-6) describes the dropped index as "The non-unique idx_dashboard_filters_dashboard_id
   index ... covers the same column set as the PK", i.e. single-column `(dashboard_id)`. The reverse
   creates a **two-column** `(dashboard_id, filter_id)` index. A `downgrade` therefore does not
   restore the prior state; it installs a wider index that no forward in the chain can remove and no
   declaration in the project specifies.
3. **The object's entire lifecycle exists as prose.** The docstring (lines 5-6, 40-48) states the
   index "was created externally (e.g., manually or via a non-versioned migration)". That is the only
   record of the object's origin; no revision, no model attribute and no script creates it.

**Evidence** — `alembic history` shows the chain is linear and that no revision other than
`f47ac18b5b9e` mentions this index name; `000000000000_initial_migration.py:164-175` is the only
`dashboard_filters` DDL; `db/models/filters.py:84-87` declares no index; the live index inventory
from `pg_indexes` shows `dashboard_filters` carrying only `dashboard_filters_pkey` at revision
`82739c97fde1`.

**Consequence** — the chain's record of `dashboard_filters` is a single statement that cannot be
reversed and a comment asserting a database the project cannot reproduce. Anyone restoring an
environment from a `pg_dump` taken before this revision ran now receives an index that no
declaration anywhere in the repository accounts for, and the only way to remove it is to hand-write
SQL — the exact condition AGENTS.md rule 13 forbids. The live blast radius today is nil: the index
does not exist in either running database, so the forward has never had an effect. The cost is
entirely in the chain's trustworthiness, which is the property this phase exists to measure.

**Recommendation** — square the reverse with the forward: either give the reverse the index
definition the docstring describes (single-column `(dashboard_id)`) so a downgrade restores the
documented prior state, or, if the object is genuinely not the chain's to manage, delete the
revision and fold its rationale into the `000000000000` docstring where the `dashboard_filters`
table is actually created. The second is the smaller end state; the first is the smaller diff. No
shipped test asserts this revision's behaviour.

### MIG-004 — The application role and every privilege the application needs are established outside the chain, and no restore path re-establishes them

**Severity** — MEDIUM

**Zone** — "Which Environments Obtain Their Schema from the Chain, and Which Obtain It Otherwise"

**Observation** — the chain declares only schema objects: tables, indexes, enum types, a
`CHECK` constraint, a trigger function and four triggers. It declares **no role and no grant** —
there is no `CREATE ROLE`, no `GRANT` and no `ALTER DEFAULT PRIVILEGES` statement in any of the eight
revisions. The runtime role is established instead, in two places that are both outside the chain
and both environment-specific:

- dev and production: `docker/init-scripts/01-create-app-role.sh`, mounted at
  `docker/docker-compose.yml:33` as `/docker-entrypoint-initdb.d`. It issues `CREATE ROLE mkobi_app
  WITH LOGIN PASSWORD ...`, `GRANT CONNECT`, `GRANT USAGE ON SCHEMA public`, `GRANT ... ON ALL
  TABLES IN SCHEMA public`, `GRANT USAGE ON ALL SEQUENCES`, and two `ALTER DEFAULT PRIVILEGES IN
  SCHEMA public` statements. The script's own header says it runs "on PostgreSQL container
  initialization (first volume start)".
- the test tier: `db/starter.py:261-263` (`GRANT CONNECT`), `:277` (`GRANT USAGE, CREATE ON SCHEMA
  public`), `:279-280` (table and sequence grants), `:282-283` (the two `ALTER DEFAULT PRIVILEGES`).
  These are needed because `recreate_test_database` drops the database the init script had already
  granted on, and nothing re-runs the init script afterwards.

Neither source is reversible, and the backup/restore path does not carry them. `Makefile.ps1:285`
takes dumps with `pg_dump -U postgres -d bidb -F c` and `:304` restores with `pg_restore -U postgres
-d bidb --clean --if-exists`. I read what that round trip actually emits: `pg_dump --schema-only`
contains `GRANT USAGE ON SCHEMA public TO mkobi_app;` and
`GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.aggregated_data TO mkobi_app;` and further
`GRANT` lines for every remaining table and both sequences in the schema, but **no `CREATE ROLE` and
no `ALTER DEFAULT PRIVILEGES`**. The per-table grants survive a restore; the role and the
forward-looking default-privilege rule do not.

**Evidence** — the absence of any grant statement in `alembic/versions/*.py` (read of all eight);
`docker/init-scripts/01-create-app-role.sh` in full; `db/starter.py:261-283`;
`docker exec mkobi-db-1 pg_dump -U postgres -d bidb --schema-only` filtered for
`GRANT|REVOKE|ALTER DEFAULT|CREATE ROLE` — 24 `OWNER TO` lines and `GRANT` lines to `mkobi_app`, zero
`CREATE ROLE` and zero `ALTER DEFAULT PRIVILEGES`; the live grant set read from
`information_schema.role_table_grants` (5 DML privileges × 13 tables including `alembic_version`).

**Consequence** — two consequences, both live. First, a restore onto a server whose volume was never
initialised — the documented disaster-recovery path — reproduces the data and the per-table grants
but leaves no `mkobi_app` role, so `pg_restore` fails on the first `GRANT ... TO mkobi_app` and the
application then cannot connect at all. Nothing in the chain fails; there is no revision that would
notice. Second, the forward-looking half of the grant model exists only in two shell/Python
fragments: a revision that creates a new table today relies on `ALTER DEFAULT PRIVILEGES` having been
established at volume init, and that is an environment fact, not a schema fact. The chain, which is
the project's stated mechanism for making the schema reproducible, reproduces none of it.

**Recommendation** — declare the role's existence in the chain's own record. The minimal correct step
is not to add `CREATE ROLE` to a migration (roles are cluster-scoped, not database-scoped, and the
chain runs per-database), but to make the grant set a first-class, reviewable artefact that the
chain's execution path applies and that a restore path reapplies — one SQL file, referenced from
both `01-create-app-role.sh` and `db/starter.py:261-283`, plus a `pg_dump`-side note that the role
itself is not part of a dump. Failing that, at minimum document in `docs/10-deployment/deployment.md`
that the role must be created by the init script on any fresh server before `restore` is run.
Whichever direction is taken, the duplication between the two grant sites should go away: today they
are two independent transcriptions of one privilege set, and they already differ (the shell script
grants `USAGE` on the schema; `starter.py:277` grants `USAGE, CREATE`).

### MIG-005 — The only path that creates a database is not in the chain, records nothing, and nothing checks that its target is a test database

**Severity** — MEDIUM

**Zone** — "Which Environments Obtain Their Schema from the Chain, and Which Obtain It Otherwise"

**Observation** — `DatabaseStarter.recreate_test_database` (`db/starter.py:193-296`) is the only
routine in the system that establishes a database. It terminates every backend on the target
(`:244-251`), issues `DROP DATABASE IF EXISTS` and `CREATE DATABASE` (`:254-259`), grants the
privileges above (`:261-283`) and replays the chain with `_apply_migrations` (`:294`). It is reached
from two doors:

- `tests/conftest.py:433` — the session-scoped `setup_test_database` fixture calls
  `DatabaseStarter(starter_config).recreate_test_database()` directly, on every pytest session. This
  is a direct call, not a lifespan effect.
- `db/starter.py:430-433` — the `python -m mkobi.db.starter --recreate-test-db` CLI, whose own
  `else` branch at `:434-435` prints the invocation as the supported usage.

Three properties of this path are true now. The drop records nothing: it is not a revision, and
`alembic_version` is not consulted, so the operation leaves no trace in the chain's own ledger of
what happened to the schema. It has no reverse — the previous contents of the dropped database are
unrecoverable, which is the intended semantics for a scratch database and the reason it is dangerous
for any other. And its only guard is an identifier-shape check: `re.match(r"^[a-zA-Z0-9_]+$",
db_name)` at `:208-209`, whose own comment describes it as SQL-injection defence, "defense-in-depth"
against injection. Nothing checks what the name denotes. The target name comes from
`config.DATABASE_URL` / `TEST_DATABASE_URL`, and `config.py:219` and `:222` declare `dbname: str =
"bidb"` and `test_dbname: str = "bidb_test"` as independent fields with no validator relating them.

**Evidence** — `db/starter.py:193-296` in full, in particular `:208-209`, `:244-259`, `:294`;
`tests/conftest.py:400-436`; the absence of a `test_dbname`/`dbname` cross-validator anywhere in
`config.py` (read of `DatabaseSettings` at `:214-290` and the property accessors at `:922-965`); the
live schema of `bidb_test` showing the chain at `82739c97fde1` with 0 `aggregated_data` rows, i.e. a
database that was dropped and rebuilt by this path as recently as the last session. **First-hand
observation of the effect:** at the start of this audit `SELECT count(*) FROM aggregated_data`
against `bidb_test` returned 4; roughly twenty minutes later, with no action by this audit, the same
query returned 0. A concurrent session's `setup_test_database` fixture had terminated the backends,
dropped the database and replayed the chain. The `alembic_version` row read `82739c97fde1` in both
live databases before and after, which is the ledger's blind spot: a drop and a full rebuild leave
exactly the trace a clean migration run would leave.

**Consequence** — the destructive operation is executed on a **shared** database. `bidb_test` is
published on host port 5434 by `docker-compose.test.yml:45` and the test database is a single
resource that every parallel pytest run and every concurrent audit or remediation agent uses. Each
session's fixture calls `pg_terminate_backend` on every backend attached to it, then drops and
recreates it, with no mutual exclusion: the project's only advisory lock,
`pg_advisory_lock(42)` at `alembic/env.py:114-127`, is only reached afterwards, inside
`_apply_migrations`. A concurrent session's in-flight test therefore has its connections terminated
and its database replaced underneath it, and neither party is told. That is the present, observable
consequence. The unguarded-target half is a latent one: all three compose files set
`DATABASE__TEST_DBNAME` to `bidb_test`, so nothing today points this at a real database, and I am
not filing the misconfiguration as the finding.

**Recommendation** — two independent changes, both small. Give the operation the mutual exclusion it
lacks, at the point where it is destructive rather than where the chain is replayed — the lock has
to be taken on the target database before `pg_terminate_backend`, which means the drop cannot
delegate to `alembic/env.py` and needs its own acquisition. And add a check that the target name is
the configured test database, alongside the existing identifier-shape check: refuse unless
`db_name == config.database.test_dbname` and `db_name != config.database.dbname`. `config.py` is the
right home for the second so that the rule holds for every caller rather than for this one. Neither
change is urgent on its own; together they are the difference between a shared fixture that cannot
destroy a peer's work and one that can.

### MIG-006 — `000000000001` performs nothing in either direction and exists only to occupy a position

**Severity** — LOW

**Zone** — "The Chain's Own Residue: Revisions and Statements That Assert Nothing"

**Observation** — `alembic/versions/000000000001_add_missing_fk_indexes.py` has
`def upgrade() -> None: pass` at line 23 and `def downgrade() -> None: pass` at line 28. Neither
direction touches the schema. The module docstring (lines 1-10) states the reason and asserts a
standing obligation: "Kept for backward compatibility - existing databases may have already applied
the indexes via this migration." No such database can exist inside this chain: its predecessor
`000000000000` already creates every index the name refers to, at lines 105-110
(`idx_dashboards_layout_id`, `idx_dashboards_created_by`), line 249
(`idx_registration_requests_reviewed_by`) and the four `aggregated_data` indexes at lines 200-214.
`000000000000`'s own comments confirm it — "FK indexes (matching ORM `__table_args__`)" and "FK
index (matching ORM `__table_args__`)". The obligation can only have been discharged by a build of
`000000000000` that preceded its current form, and that build is not reachable from the base
revision.

**Evidence** — `alembic/versions/000000000001_add_missing_fk_indexes.py:21-28`; the index
statements in `000000000000_initial_migration.py:105-110`, `:200-214`, `:247-250`; `uv run alembic
history` placing `000000000001` between `000000000000` and `000000000002` in a linear chain.

**Consequence** — a reader auditing the schema by revision name encounters a revision named
"add_missing_fk_indexes" that adds no index, and must then establish from `000000000000`'s body that
the indexes it names are already there. The chain's own history misdescribes its own shape, and the
docstring is the only record of a decision — a decision to keep a migration whose stated purpose
cannot be performed.

**Recommendation** — the smallest change is to correct the docstring to say plainly that the
revision is a retained position whose objects were folded into `000000000000`, and why folding them
in was safe. Deleting the revision and renumbering is the cleaner end state but is a history rewrite
with no benefit proportionate to a two-line comment; the comment is the right call.

### MIG-007 — `b749bc53b1ee` names, documents and performs three different index shapes

**Severity** — LOW

**Zone** — "The Chain's Own Residue: Revisions and Statements That Assert Nothing"

**Observation** — three artefacts in this revision disagree about what it creates. The filename is
`b749bc53b1ee_add_processing_logs_status_index.py` — "status index", singular column. The module
docstring title at line 1 is "Add index on processing_logs.status for cleanup query performance",
and the OpenAPI-facing summary at line 1 of the `upgrade` docstring at line 21 repeats it. The body
at lines 22-25 executes `CREATE INDEX IF NOT EXISTS idx_processing_logs_status_finished_at ON
processing_logs (status, finished_at)` — a **two-column composite**. The index name it creates also
disagrees with all three. There is no single-column `processing_logs(status)` index in the schema and
none in the model layer either; `db/models/processing_logs.py:74-81` declares
`("idx_processing_logs_status_finished_at", "status", "finished_at")` and
`("idx_processing_logs_status_started_at", "status", "started_at")`, both composite.

The consequence is not cosmetic here, because this revision is the one that created the access path
`idx_aggregated_data...` no — the one that created the access path MIG-001 turns on. Anyone
reconstructing the index set from the revision names and summaries — which is the only record a
reader of `alembic history` has — concludes that a `(status)` index exists. It does not, and its
absence as a standalone object is part of why the date-range query in MIG-001 has no access path
that can order by `started_at`.

**Evidence** — `alembic/versions/b749bc53b1ee_add_processing_logs_status_index.py:1` (docstring title)
and `:21-25` (`upgrade` summary and body) against `db/models/processing_logs.py:74-81`; the live
index inventory from `pg_indexes`, which
lists `idx_processing_logs_status_finished_at` and `idx_processing_logs_status_started_at` and no
other index on the table beyond the primary key and `idx_processing_logs_dashboard_id`;
`uv run alembic history`, which prints the docstring title, not the body.

**Consequence** — the chain's self-description is wrong in a way that a schema reader cannot detect
without reading every body. `uv run alembic history` — the command the project provides for exactly
this purpose (`Makefile.ps1` `migration-status` is `alembic current`, which prints one revision) —
reports "Add index on processing_logs.status" for a revision that created a composite.

**Recommendation** — correct the docstring title and the `upgrade` summary to name the composite,
and leave the revision identifier and filename alone: renaming the file breaks nothing but gains
nothing, since the identifier is the stable name. This is a comment-only change with no schema
effect.

### MIG-008 — `users_email_length_check` is chain-only, model-silent, and cannot fire

**Severity** — LOW

**Zone** — "Schema Objects with No Counterpart in the Model Layer"

**Observation** — `alembic/versions/000000000000_initial_migration.py:252-265` creates
`CONSTRAINT users_email_length_check CHECK (length(email) <= 255)` on `users`, guarded by a
`pg_constraint conname` lookup that filters on the name only and not on the table. No model in
`src/mkobi/db/models/` declares a `CheckConstraint` — a search of the ten model modules for
`CheckConstraint` returns zero hits, and `User.email` at `db/models/user.py:41-45` is a plain
`String(255), nullable=False` with nothing else attached. The constraint therefore exists in exactly
one of the two declarations of this schema, and the second declaration cannot see it.

It also cannot fire. `users.email` is declared `VARCHAR(255)` in both the chain (line 59) and the
model. PostgreSQL rejects an over-length value on assignment to a `varchar(n)` column before any
`CHECK` is evaluated. I reproduced both halves on a live PostgreSQL 18 instance with a temporary
table carrying the same column type and the same constraint definition:

| statement | result |
|---|---|
| `INSERT ... VALUES (repeat('x',256))` into `varchar(255)` | `ERROR: value too long for type character varying(255)` |
| `INSERT ... VALUES (repeat('x',255))` | `INSERT 0 1` |

The type constraint fires first in every case. The `CHECK` has no reachable input.

**Evidence** — the constraint definition at `000000000000_initial_migration.py:252-265`; zero
`CheckConstraint` declarations across `db/models/*.py`; the column type at
`000000000000:59` and `db/models/user.py:41-45`; the live constraint read from `pg_constraint`
(`users | users_email_length_check | c | CHECK ((length((email)::text) <= 255))`) and
`information_schema.columns.character_maximum_length = 255` for the same column; the two-statement
probe above. Composed with the discharged result that `alembic check` reports no drift
(phase 10, OPS) while this constraint is present and the model layer is silent: the drift gate
compares the live database against the model layer, and Alembic's autogenerate does not compare
`CHECK` constraints, so this divergence is structurally invisible to the only gate the project owns.

**Consequence** — the chain asserts a length guard on `users.email` that the schema does not
perform, on a column whose type already performs a stricter one. No data can be lost and no write
can be wrongly refused, so there is no live effect; the cost is that the chain's record of the
schema is inaccurate in a way no automated check in the project can report, and the guard's name
(`users_email_length_check`) is a plausible-looking protection to a future maintainer who will not
find that the type is doing the work. No revision drops it.

**Recommendation** — delete the constraint in a new revision on top of `82739c97fde1`:
`ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_length_check;`. The column type is the
guard, and it is the stronger one. If the intent was to bound the *value* rather than the storage,
that intent needs a different expression and a stated rule about what an over-long address should do,
which is an application decision rather than a schema one. The `pg_constraint` guard at
`000000000000:255-262` should also gain a `conrelid` filter while it is in view, so a future
constraint of the same name on another table does not satisfy it.

## Distribution

The findings fall in three places, and the chain itself is not among them: no finding contradicts
the model layer, and none of the eight touches a data-loss or corruption path.

- **Access paths versus issued predicates (2 findings, both HIGH)** — `aggregated_data` and
  `processing_logs`, the two tables the read path depends on. `aggregated_data` carries the more
  findings-adjacent one (MIG-002).
- **The chain's own record (3 findings)** — MIG-003, MIG-006 and MIG-007 are all defects in what
  the revisions say they do rather than in what they do to the schema. None of them changes a
  column, a key or a constraint.
- **Schema source and authority outside the chain (2 findings)** — `db/starter.py` and
  `docker/init-scripts/01-create-app-role.sh`, the two places that create things the chain does not
  describe.

`db/starter.py` carries the most: MIG-005, and the second half of MIG-004. It is the only module
that both establishes a database and grants privileges, and neither act is in the chain.

## Cross-Finding Analysis

Six of the eight findings share one cause. The chain is **authored as statements, not derived from
the model layer**, and nothing in the project can diff the two.

Every one of the eight revisions except the last writes raw SQL through `op.execute()`;
`000000000000` is a 392-line transcription of `CREATE TABLE` / `CREATE INDEX` / `DO $$` blocks, and
only `82739c97fde1` is genuine Alembic autogenerate output, still carrying its
`# ### commands auto generated by Alembic - please adjust! ###` banner at lines 23-25. That is what
MIG-003 (a revision whose subject exists only in prose), MIG-006 and MIG-007 (revisions whose
descriptions do not match their bodies) and MIG-008 (a constraint the model cannot see) are all
made of. And the one gate the project owns cannot compensate: `alembic check` compares the **live
database** against the **model layer**, never the chain against either, and it does not compare
`CHECK` constraints at all — which is precisely why MIG-008 is invisible to it, and why phase 10's
"no drift today" is a true and insufficient result. Adding `alembic/` to the ruff and mypy targets
(the TOPO-007 gap, adjudicated below) would catch the four `UP007` violations in
`82739c97fde1` and would not catch any of the six above: they are all semantic, and a linter is not
the instrument for them.

MIG-001 and MIG-002 are independent of that cause and of each other. Both are cases of a declared
access path that does not serve the declared query, but in different places for different reasons —
one because the index's leading column is not the one the query orders by, the other because the
operator class does not contain the operator — and they are fixed by changes in different files.
MIG-004 and MIG-005 are related but not shared-cause: both concern authority that lives outside the
chain, one over grants and one over the database itself, and they are independently fixable.

### Adjudications of prior findings

**TOPO-004 (phase 01, HIGH) — the drop precedes the advisory lock.** The lock's *placement* is a
phase-01 topology defect and stays there. It is not a phase-14 defect, for a specific reason: the
lock is acquired in `alembic/env.py:114-127`, which is the chain's own execution harness, and a guard
placed inside the chain cannot protect a path that is not in the chain. The schema-side consequence
— that the only routine which establishes a database is not a revision, records nothing in
`alembic_version` and has no reverse — is what MIG-005 files, as a distinct claim about the schema
source rather than about lock ordering.

**Phase 01's premise that the destructive path "is never executed because the harness bypasses the
lifespan" is incorrect, and the correction raises the exposure rather than lowering it.**
`tests/conftest.py:433` calls `DatabaseStarter(starter_config).recreate_test_database()` directly —
not through the lifespan — on every session. The ASGITransport bypass at `conftest.py:559` is real
and does prevent `starter.startup()` from running, but it is irrelevant to this path, which conftest
invokes itself. The path is not merely armed; it executes on every test run, against a database
published on host port 5434 and shared with every other session. TOPO-004's severity judgement
stands and its supporting premise should be corrected upstream.

**TOPO-007 (phase 01, LOW) — `alembic/` sits outside both quality gates.** This is a
gate-coverage defect over my files, and its owner is **phase 08**, not 01 and not 14. Neither
process topology (01) nor schema evolution (14) owns lint coverage; the phase-14 scope boundary
assigns "whether a drift gate exists, is loaded and would notice" to 08, and gate coverage is the
same question one level up. I verified the ruff half rather than taking it on report:
`uv run ruff check alembic/` returns `Found 4 errors`, all `UP007` at
`alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py:17` and `:18`, both
auto-fixable. I am not re-filing it and I am not fixing it here; the one-line fix is to add
`alembic/` to the `lint` and `typecheck` targets at `Makefile.ps1:221,229` and to the mypy exclude
list at `pyproject.toml:169`.

**QLT-008 (phase 08) — the bare-`str` permission homes versus the native enum.** The divergence is
real and the **schema is the party doing its job**. `dashboard_permission_level` holds exactly
`view,edit,admin`; `DashboardPermission` in `models/enums.py:17-22` holds exactly the same three; and
`db/models/access.py` declares the column as `Enum(DashboardPermission, name="dashboard_permission_level",
values_callable=...)`, so the ORM layer is fully typed. The bare-`str` homes phase 08 counted
are the Pydantic boundary (`models/access.py:11` and `:30`, both `permission: str = "view"`) and the
service signatures. I traced the one path that reaches the store: `grant_access` calls
`self._validate_permission(permission)` at `services/dashboard_service.py:374` and then writes
**`permission`**, not the normalised value, at `:389`. `_validate_permission` (`:482-501`) maps
`read`→`view` and `write`→`edit` and discards `normalized`; `core/permissions.py:209-210` maps the
same two aliases on the read side. So `{"permission": "read"}` passes validation, is written verbatim,
and PostgreSQL refuses it. The 500 phase 08's validator reproduced is the enum doing exactly what a
storage-enforced enumeration is for. **Not a phase-14 finding and not re-filed**: the type-versus-
enum divergence lives between the Pydantic boundary and the service, both in phase 08's territory, and
the fix is to return `normalized` from `_validate_permission` and type the parameter
`DashboardPermission`, not to widen the enum. Had the column been `VARCHAR`, phase 08's finding
would have been a data-corruption CRITICAL instead.

**TST-012 (phase 09) — rows surviving in the test database.** This is phase 09's, and the schema
fixture is not the cause. `tests/conftest.py:469-497` implements per-test isolation correctly: a
SAVEPOINT (`begin_nested`) opened before each test and rolled back in a `finally`. Rows survive only
where work bypasses that session — a code path that opens its own session via
`get_async_sessionlocal()`, which is the same class of defect as TXN-001 (phase 03, CRITICAL: the
session dependency yields a session and never commits or rolls back). The fixture is doing what a
schema fixture should; the leak is downstream of it in code that phase 03 already owns. No
phase-14 finding, and I note the two overlap so a remediation does not fix the fixture and call it
done.

**DP-003 (phase 05) — type-sensitive aggregate identity.** Not re-filed. The unique index
`uq_aggregated_data_dashboard_graph_dims (dashboard_id, graph_id, ((dims)::text))` is declared
identically in the chain (`000000000000:212-214`) and the model layer
(`db/models/aggregated_data.py:56-61`), and `jsonb`'s canonical text rendering means it is a
faithful identity on `dims` for values the storage engine already considers equal. It cannot
prevent `'1'` from storing separately from `1`, because the two are not equal `jsonb` values and no
index over `dims` could make them so. The correctness claim is phase 05's and a distinct schema
claim does not exist here.

**PERF-001 (phase 11) — the unbounded dashboard read.** Not re-filed and not re-derived as an index
finding beyond MIG-002, which is a structural opclass match and not a cost measurement. Phase 11's
refutation of the project's own JSONB-containment recommendation is not repeated: MIG-002 does not
assert that any replacement index is warranted, only that the declared one cannot serve the issued
operator.

## Roadmap

Grouped by cause. Steps 1-2 are the access-path pair and are independent of everything else; step 1
should land before step 2's decision, because MIG-002's fix direction depends on whether the
read-path change in step 2 changes what the schema needs to declare.

1. **MIG-001** — add one revision on top of `82739c97fde1` creating an index that leads with
   `started_at`. Prerequisite for step 4's verification: none; it is a pure addition and no step
   depends on it.
2. **MIG-002** — decide the operator, then act. Settle with phase 05 whether
   `get_by_graph_id` keeps emitting `->>` or moves to a containment form; if it keeps emitting
   `->>`, the GIN index is residue and a second revision drops it. Prerequisite for step 3: the
   decision, not the edit.
3. **MIG-003, MIG-006, MIG-007** — the comment-and-reverse pass over the chain. Three independent
   edits, one review: correct `b749bc53b1ee`'s docstring, correct `000000000001`'s docstring, and
   square `f47ac18b5b9e`'s reverse with its forward (or retire the revision). Prerequisite for step
   4: none, but doing this first means the chain reads correctly for anyone who works on step 4.
4. **MIG-004** — collapse the two transcriptions of the grant set into one referenced artefact, and
   state in the deployment document that the role itself is outside the dump. Prerequisite for
   step 5: the single artefact must exist before the restore path can be pointed at it.
5. **MIG-005** — add the target-identity check in `config.py` and move the mutual exclusion to the
   destructive call site. Prerequisite: nothing; do this before the next full-suite run on a shared
   `bidb_test`, because it is the one change that stops the fixture from interfering with other
   work.
6. **MIG-008** — one revision dropping `users_email_length_check`, with the `conrelid` filter added
   to the guard in `000000000000` while the constraint is in view. Independent of everything above.

MIG-001, MIG-003, MIG-006, MIG-007 and MIG-008 are all comment-or-addition changes that no deployed
environment's data depends on. Only MIG-002's second branch (dropping the GIN index) changes
observable behaviour.

## Rollout Safety

Five of the six steps are additive or comment-only and carry no rollout risk: a new index
(`MIG-001`), three documentation corrections, and a constraint drop that removes an object with no
reachable input. The two that change observable behaviour are MIG-002's index drop and MIG-005's
new guard.

Dropping `idx_aggregated_data_dims_gin` is the one step that could surprise. Nothing in the current
code can use it (MIG-002), but a future query written against `@>` would lose its only access path
until an index is added, and the drop is a write-amplification win that only shows on tables that are
currently empty — so there is no pressure to notice a regression. The safe sequence is: land the
repository change that fixes the operator first, confirm by `EXPLAIN` that the plan is what you
expect on a table with representative data, and only then drop the index. Reversal is a single
`CREATE INDEX` back; the revision's `downgrade` should carry it.

MIG-005's guard can break a working setup: if any environment relies on the test database being
named something other than `DATABASE__TEST_DBNAME` — the xdist suffix in
`tests/conftest.py:417-425` builds `bidb_test{suffix}` names, which are derived rather than
configured — the check must be written against the configured value, not a hard-coded literal, or
parallel runs will start refusing to start. Verify by running the suite with and without `-n`
before and after. The mutual-exclusion change is the safer half: it can only make a destructive
operation wait, and it can be reverted by removing the acquisition. Roll both out separately.

## Appendices

### Baseline

`git rev-parse HEAD` = `05f2779323c1746c8945f63882b187bcb2d7b608`
`git status --porcelain` — dirty, as recorded in the frontmatter. No file was edited, staged,
committed, reverted or stashed by this audit; no migration was run; every database access was a
read-only `SELECT`, `EXPLAIN` (never `EXPLAIN ANALYZE`) or catalog query.

**HEAD moved during the audit.** By the time this report was finalised `HEAD` was
`0717b65f541d6378984fbf21a84b2067ba3e1294`, one commit ahead of the recorded baseline:
`fix(worker): report CSV processing failures on their own session`. That commit touches exactly two
files, `src/mkobi/workers/data_worker.py` and `tests/test_file_cleanup.py` — the same two the
baseline showed as modified. Neither is a migration, a model, a compose file, a Makefile target or a
document this report cites, so no anchor in this report moved and none needed re-verification. The
`baseline:` frontmatter records the commit this audit actually read.

### Commits since `8505a62` touching a migration or `alembic/env.py`

None. Every commit landed between `8505a62` and `0717b65` is in the phase-02 configuration/secrets
remediation stream — configuration validation, credential hardening, compose environment wiring,
documentation alignment and gate restoration. `git diff --stat 8505a62..HEAD -- alembic/` is empty:
`alembic/versions/`, `alembic/env.py` and `alembic.ini` are unchanged since before the audit window,
so the whole chain read here is the chain as it stood at `8505a62`. `Makefile.ps1` is likewise
unchanged across that range. The remediation did touch two files this phase reads:
`docker/docker-compose.yml` and `docker/docker-compose.override.yml` (CFG-004/CFG-009 environment and
credential wiring, including the new `UPLOAD__TEMP_DIR` on the `migrate` service) and
`src/mkobi/db/starter.py`. The starter change is confined to `ensure_admin_user` (the weak-password
predicate, moved from a local set to the shared `is_weak_admin_password` /
`is_weak_admin_username` helpers) plus its import block; every line this report cites in that file
(`:193-296`, `:208-209`, `:244-259`, `:261-283`, `:294`, `:395-418`, `:430-435`) lies outside the
changed hunk and was read at the current HEAD. One boundary-adjacent note for phase 08:
`8953bf7 fix(gates): restore green ruff and mypy baselines` altered the gate definitions and the
current targets still exclude `alembic/` — see the TOPO-007 adjudication above.

### Derived revision graph (Block 1)

Single head, linear, no branch, no unresolvable predecessor, nothing orphaned.

```
(base) -> 000000000000 -> 000000000001 -> 000000000002 -> 4479eb53fd4e
       -> b749bc53b1ee -> f47ac18b5b9e -> c5d6e7f8a9b0 -> 82739c97fde1 (head)
```

Source: `uv run alembic heads` (`82739c97fde1 (head)`, one line) and `uv run alembic history`. The
live `alembic_version.version_num` is `82739c97fde1` in both `bidb` and `bidb_test`.

### Per-revision forward/reverse verdicts (Block 2)

| revision | forward | reverse | verdict |
|---|---|---|---|
| `000000000000` | 12 tables, 6 enum types, 24 indexes, 1 CHECK, 1 plpgsql function, 4 triggers | drops triggers, function, 12 tables, 6 enum types | symmetric; base reverse takes indexes/CHECK with their tables |
| `000000000001` | `pass` | `pass` | **MIG-006** |
| `000000000002` | `CREATE TABLE dashboard_filter_values` + 2 indexes | `DROP TABLE` | symmetric |
| `4479eb53fd4e` | rename/recreate/retype/drop the enum, dropping `success` | same sequence restoring the original 6 values **in the original order** | symmetric; verified the reverse restores `started,uploaded,processing,success,failed,completed` |
| `b749bc53b1ee` | create `(status, finished_at)` | drop it | **MIG-007** (shape only) |
| `f47ac18b5b9e` | `DROP INDEX IF EXISTS idx_dashboard_filters_dashboard_id` | `CREATE INDEX` on `(dashboard_id, filter_id)` | **MIG-003** — asymmetric |
| `c5d6e7f8a9b0` | create `(status, started_at)` | drop it | symmetric; see the access-path note below |
| `82739c97fde1` | `op.add_column('processing_logs', 'error_code', String(50))` | `op.drop_column` | symmetric; the only genuine autogenerate output in the chain |

`4479eb53fd4e`'s forward also reorders `failed` and `completed` in the enum, and its reverse restores
the original order, so a downgrade/re-upgrade cycle is order-faithful. No index in the chain is
built on `processing_status` before the reorder (`b749bc53b1ee` runs after it), so no index is left
stale across the type rewrite.

### Access-path note for phase 11 (not a finding, by this block's own rule)

`idx_processing_logs_status_started_at` is declared for "stale log cleanup queries"
(`c5d6e7f8a9b0:1`), but the stale-cleanup `DELETE` does not use it. Verified against the live
database with `enable_seqscan=off`:

```
DELETE FROM processing_logs WHERE status='processing' AND started_at < now() - interval '1 hour';
->  Index Scan using idx_processing_logs_status_finished_at on processing_logs
      Index Cond: (status = 'processing'::processing_status)
      Filter: (started_at < (now() - '01:00:00'::interval))
```

The planner prefers the `finished_at` index and demotes `started_at` to a residual filter, even with
sequential scanning disabled. This block's rule is that the measurable cost of a redundant access
path belongs to phase 11, so no finding is filed; the write-amplification measurement is left there.

### Chain-owned objects with no model-layer counterpart (Block 4)

| object | created by | altered by | dropped by | verdict |
|---|---|---|---|---|
| `users_email_length_check` | `000000000000:252-265` | — | no revision; only the base reverse, via `users` | **MIG-008** |
| `update_updated_at_column()` | `000000000000:267-278` | — | `000000000000` reverse:355 | lifecycle complete |
| `update_{users,layouts,dashboards,processing_configs}_updated_at` | `000000000000:280-341` | — | `000000000000` reverse:347-352 | lifecycle complete |
| `idx_aggregated_data_dims_gin` | `000000000000:209-211` | — | no revision; base reverse via the table | **MIG-002** |
| `uq_aggregated_data_dashboard_graph_dims` | `000000000000:212-214` | — | no revision; base reverse via the table | declared identically in the model layer |
| 6 native enum types | `000000000000:24-52` | `4479eb53fd4e` (recreates `processing_status`) | `000000000000` reverse:375-392 | declared identically in the model layer |

The trigger function is the **only** mechanism keeping `updated_at` current: a search of the ten
model modules for `onupdate` returns zero hits, so no model sets the column on the ORM side. That is
a coherent design, not a gap, and the function and its four triggers have complete lifecycles in the
chain — recorded here because Block 4 asks what outside the chain can change them, and the answer
is only `DROP DATABASE` and a `pg_restore --clean`.

### Enumerated-type parity (Block 5)

Both directions agree for all six types, verified against `pg_enum` in the live database. No
symmetric difference.

| type | stored values | application enum | agrees |
|---|---|---|---|
| `user_role` | `admin,editor,viewer` | `UserRole` (`enums.py:9-14`) | yes |
| `dashboard_permission_level` | `view,edit,admin` | `DashboardPermission` (`enums.py:17-22`) | yes |
| `graph_type` | `bar,line,pie,table` | `GraphType` (`enums.py:25-31`) | yes |
| `filter_type` | `select,multiselect,range,date` | `FilterType` (`enums.py:34-40`) | yes |
| `processing_status` | `started,uploaded,processing,completed,failed` | `ProcessingStatus` (`enums.py:58-65`) | yes |
| `registration_status` | `pending,approved,rejected` | `RegistrationStatus` (`enums.py:43-48`) | yes |

The application carries one extra vocabulary that the store does not: the `read` and `write` aliases
at `core/permissions.py:209-210` and `services/dashboard_service.py:485-488`. Adjudicated above
under QLT-008 — the divergence is in the Pydantic boundary, not in the schema, and the enum is
correctly refusing it. Note also that `api/routes/processing_logs.py:47-48` advertises
`SUCCESS` in the `status_filter` parameter description; `ProcessingStatus` has no `SUCCESS` member
(removed by `4479eb53fd4e`), so the published API documentation names a value the store and the
application both reject. That is a documentation defect in phase 08's territory, recorded here
because the enum is the authority for it.

### Referential-action agreement (Block 7)

All thirteen foreign keys exist in both declarations with identical `ON DELETE` actions; the live
`pg_constraint` inventory matches the model layer one for one. No relationship is constrained on one
side only, and no delete path can leave a row naming a missing parent.

| relationship | declared in model | declared in chain | live constraint | action |
|---|---|---|---|---|
| `dashboard_access.user_id` | `access.py:31` | `000000000000:150` | `dashboard_access_user_id_fkey` | CASCADE |
| `dashboard_access.dashboard_id` | `access.py:37` | `000000000000:151` | `dashboard_access_dashboard_id_fkey` | CASCADE |
| `dashboards.layout_id` | `dashboard.py:62` | `000000000000:94` | `dashboards_layout_id_fkey` | SET NULL |
| `dashboards.created_by` | `dashboard.py:68` | `000000000000:95` | `dashboards_created_by_fkey` | SET NULL |
| `graphs.dashboard_id` | `graphs.py:44` | `000000000000:117` | `graphs_dashboard_id_fkey` | CASCADE |
| `dashboard_filters.dashboard_id` | `filters.py:85` | `000000000000:170` | `dashboard_filters_dashboard_id_fkey` | CASCADE |
| `dashboard_filters.filter_id` | `filters.py:86` | `000000000000:171` | `dashboard_filters_filter_id_fkey` | CASCADE |
| `processing_configs.dashboard_id` | `processing_configs.py:27` | `000000000000:181` | `processing_configs_dashboard_id_fkey` | CASCADE |
| `aggregated_data.dashboard_id` | `aggregated_data.py:71` | `000000000000:193` | `aggregated_data_dashboard_id_fkey` | CASCADE |
| `aggregated_data.graph_id` | `aggregated_data.py:77` | `000000000000:194` | `aggregated_data_graph_id_fkey` | CASCADE |
| `processing_logs.dashboard_id` | `processing_logs.py:37` | `000000000000:221` | `processing_logs_dashboard_id_fkey` | SET NULL |
| `registration_requests.reviewed_by` | `registration_request.py:67` | `000000000000:241` | `registration_requests_reviewed_by_fkey` | SET NULL |
| `dashboard_filter_values.dashboard_id` | `dashboard_filter_values.py:57` | `000000000002:27` | `dashboard_filter_values_dashboard_id_fkey` | CASCADE |

Business keys are declared in both: `users.email` (unique index), `layouts.name`, `dashboards.name`,
`filters.name`, `graphs(dashboard_id, name)` (all unique indexes), `registration_requests.email`
(unique constraint), `dashboard_access(user_id, dashboard_id)` (PK), `dashboard_filters(dashboard_id,
filter_id)` (PK), `processing_configs.dashboard_id` (PK), `dashboard_filter_values(dashboard_id,
filter_name, filter_value)` (unique index), `uq_aggregated_data_dashboard_graph_dims` (unique
expression index).

One structural observation, not filed: `aggregated_data` carries two independent foreign keys,
`dashboard_id` and `graph_id`, with no constraint tying the graph to that dashboard. I checked
whether any live path can produce a mismatched pair and found none — `aggregation_service.py:118`
takes `graph.id` from a dashboard-scoped list, and `data_service.py:378` takes
`graphs[0].id` from `graph_repo.get_by_dashboard_id(dashboard_id, db)` at line 231. The gap is
reachable only by construction error, and this block does not populate a band with hypotheticals.

### Environment x schema-source matrix (Block 8)

| environment | schema source | reached? | notes |
|---|---|---|---|
| production | `migrate` service, `alembic upgrade head` as `postgres` (`docker-compose.yml:54-92`) | reached, every deploy | role and grants from `init-scripts/01-create-app-role.sh` at volume init; `AUTO_MIGRATE` removed from `app` so the app never replays the chain |
| development | same `migrate` service, `ENV: development` (`docker-compose.override.yml:14-38`) | reached | same role source; `DATABASE__USER: postgres` inherited from the base file's `migrate` block, which environment merging preserves |
| test | `test-migrate` service (`docker-compose.test.yml:86-113`) plus `recreate_test_database` from `conftest.py:433` | reached, **twice per session** | `ENV: test` and `RECREATE_TEST_DB: "true"` at `:93` and `:147` sit on `test-app`, whose command is `tail -f /dev/null` (`:167`), so the lifespan never runs and those two settings are inert under Compose; the pytest harness reaches the same function by a different door. Grants come from `db/starter.py:277-283`, not from the init script, because the drop wiped them. See MIG-005. |
| restore | `pg_restore --clean --if-exists` (`Makefile.ps1:304`) | reached, on demand | overwrites the chain's output with a dump; `GRANT`s round-trip, `CREATE ROLE` and `ALTER DEFAULT PRIVILEGES` do not. See MIG-004. |

### Method and limits

Read-only throughout. Catalog and plan evidence was taken from `mkobi-db-1` / `bidb` (revision
`82739c97fde1`) and `mkobi-test-test-db-1` / `bidb_test` (revision `82739c97fde1`) via `docker exec
psql`. The GIN-opclass and CHECK-reachability proofs used `CREATE TEMP TABLE`, which is session-local
and left nothing behind; no permanent object was created in either database. `EXPLAIN` was used
without `ANALYZE` throughout, so no query was executed. Static proofs: `uv run ruff check alembic/`
(4 `UP007`, all at `82739c97fde1:17-18`), `uv run alembic heads`, `uv run alembic history`.

**Limits on this report.** Three properties could not be settled at this baseline and are recorded
here rather than as findings.

1. *Plan shapes on the real read path.* `aggregated_data` holds 0 rows in `bidb` and 0 in
   `bidb_test` at this baseline — re-verified at the end of the audit, after the drop described in
   MIG-005 — so MIG-002's proof is the opclass capability match on a temporary table rather than a
   plan measured against production-shaped data. Phase 11's 375,000-row measurement is no longer
   reproducible in either live database. The structural claim does not depend on row count, but its
   *magnitude* does, and this report does not quantify it. `processing_logs` holds 3 rows in `bidb`
   and 5 in `bidb_test`.
2. *Downgrade reproduction.* No revision was downgraded and re-upgraded on a store, because that
   requires a schema-writing operation on databases other agents are using. The forward/reverse
   verdicts above are read from the bodies; MIG-003's asymmetry is a static proof that needs no
   store, but a downgrade/re-upgrade cycle on `f47ac18b5b9e` would be the empirical confirmation.
3. *Whether a clean chain can be built on a non-superuser.* Every compose file runs the chain as
   `postgres`. Whether the eight revisions are replayable by a least-privilege migration role — the
   mitigation the compose file's own comment at `docker-compose.yml:52` proposes — was not tested,
   and `mkobi_app` has no DDL privilege to attempt it with.

Artefacts consulted: the eight files in `alembic/versions/`, `alembic/env.py`, `alembic.ini`,
`src/mkobi/db/models/*.py` (11 modules), `src/mkobi/db/starter.py`, `src/mkobi/config.py`,
`src/mkobi/app.py`, `src/mkobi/db/repositories/{aggregated_data_repo,processing_log_repo,filter_repo,dashboard_filter_values_repo,dashboard_repo,registration_request_repo}.py`,
`src/mkobi/services/{dashboard_service,data_service,aggregation_service}.py`,
`src/mkobi/core/permissions.py`, `src/mkobi/models/{access,dashboard,enums}.py`,
`src/mkobi/api/routes/{processing_logs,data,dashboards_access}.py`, `tests/conftest.py`,
`Makefile.ps1`, `docker/docker-compose.yml`, `docker/docker-compose.override.yml`,
`docker/docker-compose.test.yml`, `docker/init-scripts/01-create-app-role.sh`.
