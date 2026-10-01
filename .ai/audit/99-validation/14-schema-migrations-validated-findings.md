---
phase: 14-schema-migrations
executed: 2026-09-30
executor: validator
problems-only: true
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 3
  LOW: 3
audited-findings: 8
audited-namespace: MIG-
validation-namespace: VAL-14-
baseline: 0717b65f541d6378984fbf21a84b2067ba3e1294
baseline-dirty: "true — D .ai/builders/**, D .ai/structure/**, D .ai/models/**, D .ai/templates/**, D .ai/plans/audit-fix-plan.md, D .ai/audit/templates/audit-final-report.md, D frontend/coverage/**, ?? .ai/audit/**, ?? .ai/plans/*"
written-at: 0717b65f541d6378984fbf21a84b2067ba3e1294
---

# Phase 14 — Validated Findings

## Summary

The schema-and-migration report was re-derived from the executing path at `0717b65`, against the
rubric of record at `.kilo/commands/audit/phases/14-audit-schema-migrations.md:122-137`. All eight
`MIG-` identifiers re-anchor cleanly, all eight zone quotations are verbatim block titles, and the
chain's own head moved nowhere. Both HIGH findings reproduce on live PostgreSQL 18.6 with the exact
`EXPLAIN` shapes the input recorded, and MIG-002's operator-class claim is exact — the live index
uses GIN `jsonb_ops`, whose members are `@> ? ?| ?& @? @@` and which contains no `->>`. The material
adjudication holds: `tests/conftest.py:433` does call `DatabaseStarter(...).recreate_test_database()`
directly on every session, so phase 01's premise for TOPO-004 is wrong and phase 14's correction
**raises** the exposure rather than lowering it. No audited band is changed. Five defects in the input
report itself are filed as `VAL-14-001` through `VAL-14-005` (2 MEDIUM, 3 LOW), the two MEDIUM being a
measured absence in MIG-004 that is not there and a quoted docstring in MIG-003 that refutes the
inference drawn from it.

## Disposition Tally

| ID | Band carried | Disposition | Basis |
|---|---|---|---|
| MIG-001 | HIGH | confirmed | all three `EXPLAIN`s reproduced byte-for-byte; asserted *reasoning* imprecise (`VAL-14-001`); band unchanged |
| MIG-002 | HIGH | confirmed | `pg_opclass`/`pg_amop` reproduce the claim exactly; emitted predicate re-derived from the ORM; band unchanged |
| MIG-003 | MEDIUM | confirmed on 2 of 3 numbered facts | fact 2 refuted by its own quoted docstring (`VAL-14-003`); band unchanged |
| MIG-004 | MEDIUM | confirmed; one mechanism refuted | no grant/role in any of the eight revisions; `ALTER DEFAULT PRIVILEGES` **is** in the dump (`VAL-14-004`) |
| MIG-005 | MEDIUM | confirmed | executing path re-read; drop observed executing from outside the audit; concurrency ruling stated |
| MIG-006 | LOW | confirmed | both directions are `pass`; ancestor index statements present |
| MIG-007 | LOW | confirmed; artefact count corrected | `alembic history` reproduces the wrong description; **two** artefacts disagree, not three |
| MIG-008 | LOW | confirmed | constraint chain-only, model-silent, type fires first — reproduced |
| TOPO-004 (phase 01) | HIGH | **premise correction upheld**; the drop executes on every session | `conftest.py:433` read in full |
| TOPO-007 (phase 01) | LOW | ownership ruling upheld (phase 08) | gate exclusion re-derived; the input's own ruff verification misreported (`VAL-14-002`) |
| QLT-008 (phase 08) | — | ruling upheld; schema correct, divergence at the Pydantic boundary | re-derived |
| TST-012 / DP-003 / PERF-001 | — | deferrals upheld | MIG-002 checked against the refuted figures |

Tally: 8 confirmed, 0 re-typed, 0 re-graded, 0 merged, 0 not substantiated, 0 unsettled among the
audited findings. 7 prior-finding rulings returned, 1 of them a material correction to an
already-validated phase-01 finding. 5 validation-level findings filed (`VAL-14-001` … `VAL-14-005`):
2 MEDIUM, 3 LOW, 0 CRITICAL, 0 HIGH.

## Findings — audited namespace `MIG-` (validated)

### MIG-001 — The admin processing-log list's date filter and default sort have no access path that can produce that order

**Verdict** — confirmed. Band carried unchanged at HIGH; the rubric assigns HIGH to "a live
predicate has no access path that can serve it". No re-grade.

**Severity** — HIGH

**Zone** — "The Index Inventory against the Predicates the Code Actually Issues"

**Observation** — Re-anchored and confirmed. `ProcessingLogRepository.get_filtered`
(`src/mkobi/db/repositories/processing_log_repo.py:163-228`) builds every predicate conditionally:
`:183` dashboard, `:189` status, `:194` date-from, `:199` date-to. `:206` is
`order_by(processing_log_model.ProcessingLog.started_at.desc())` — unconditional — and `:208-212`
applies `offset`/`limit`. The live inventory of `processing_logs` in `bidb` at `82739c97fde1` is four
indexes, none of which leads with `started_at`:

```
idx_processing_logs_dashboard_id         btree (dashboard_id)
idx_processing_logs_status_finished_at   btree (status, finished_at)
idx_processing_logs_status_started_at    btree (status, started_at)
processing_logs_pkey                     btree (id)
```

**Evidence** — All three `EXPLAIN (COSTS OFF)` outputs reproduce byte-for-byte against
`mkobi-db-1` / `bidb` / PostgreSQL 18.6, `SET enable_seqscan=off; SET enable_bitmapscan=off`:

```
-- Q1, date filter, no status
 Limit -> Sort (Sort Key: started_at DESC)
       -> Index Scan using idx_processing_logs_status_started_at
            Index Cond: (started_at >= '2026-01-01 00:00:00+00')

-- Q2, date filter + status = 'failed'
 Limit -> Index Scan Backward using idx_processing_logs_status_started_at
            Index Cond: ((status = 'failed') AND (started_at >= '2026-01-01'))

-- Q3, the endpoint's default call, no filters at all
 Limit -> Sort (Sort Key: started_at DESC)
       -> Seq Scan on processing_logs  Disabled: true
```

The isolation test holds: adding the leading-column equality removes the `Sort` outright. I also ran
the counterfactual the input did not — a **temporary** table (`mig14_pl`, 50 000 rows, the same two
composite indexes, both scan types disabled) to establish what the planner would actually choose and
whether an index would be used at all. It reproduces the same three shapes, and adding
`CREATE INDEX i_lead ON mig14_pl (started_at DESC)` removes the `Sort` in favour of
`Index Scan using i_lead`. The recommendation therefore works, and the direction is confirmed: a
btree whose leading column is the sorted column is what the plan needs.

**Consequence** — As filed. The read is admin-only and the table holds 3 rows in `bidb` today, so the
present cost is small; the exposure is structural, and the recommendation lands as a pure addition
with a reversible `downgrade`.

**Recommendation** — Executable as written. The target (`82739c97fde1`) is the live head, no shipped
test asserts the plan shape, and the index is additive. Two refinements the input did not record:
`DESC` in the index definition is redundant (a btree is scanned backwards on demand, as Q2's
`Index Scan Backward` demonstrates), and the input's statement that the endpoint "re-reads and
re-sorts the whole table on every page" overstates the sort: with `LIMIT 100` present PostgreSQL uses a
top-N heapsort, so it *reads* every qualifying row but does not fully sort it. The traversal, not the
sort, is the cost. See `VAL-14-001` for the reasoning defect this sits inside.

### MIG-002 — The declared GIN index on `aggregated_data.dims` cannot serve the only JSONB operator the application issues

**Verdict** — confirmed. Band carried unchanged at HIGH; the rubric assigns HIGH verbatim to "a
declared access path cannot serve the operator the code actually issues against a structured
column". No re-grade.

**Severity** — HIGH

**Zone** — "The Index Inventory against the Predicates the Code Actually Issues"

**Observation** — Re-derived from the ORM rather than from the rendered SQL string. Both call sites
emit extraction. `aggregated_data_repo.py:161` is
`AggregatedData.dims[key].astext == str(value)` inside `for key, value in filters.items()`, which
SQLAlchemy renders as `(dims ->> 'k') = 'v'`; `:268` is
`select(distinct(AggregatedData.dims[dim_name].astext))` in `get_dims_values`. Neither is a
containment operator, and no `@>`, `?` or `@@` is emitted anywhere against this column.

The live index is `CREATE INDEX idx_aggregated_data_dims_gin ON public.aggregated_data USING gin (dims)`
— no operator class named — and the catalog resolves what that binds to:

```
idx_aggregated_data_dims_gin | gin | jsonb_ops | jsonb
```

**Evidence** — The operator membership of `jsonb_ops` read from `pg_opclass` → `pg_amop` for the GIN
method is exactly six operators:

```
gin | jsonb_ops | ?   | jsonb  | text
gin | jsonb_ops | ?&  | jsonb  | text[]
gin | jsonb_ops | ?|  | jsonb  | text[]
gin | jsonb_ops | @>  | jsonb  | jsonb
gin | jsonb_ops | @?  | jsonb  | jsonpath
gin | jsonb_ops | @@  | jsonb  | jsonpath
```

`->>` is absent, and there is no `jsonb`-GIN opclass in the catalog that contains it — `jsonb_path_ops`
carries only `@>`, `@?`, `@@`. This is the well-known behaviour the input names, and it is exactly
correct. The sibling access path over the same column,
`uq_aggregated_data_dashboard_graph_dims btree (dashboard_id, graph_id, ((dims)::text))`, is an
expression index on the whole document's text rendering and cannot serve `->> 'k'` either, so no
declared access path on `aggregated_data` can serve the issued operator. The only remaining index,
`idx_aggregated_data_graph_id`, is a single-column btree on `graph_id`.

**Consequence** — As filed. The GIN index is write-amplified on every insert and serves nothing the
code issues. `aggregated_data` holds 0 rows in `bidb` and 0 in `bidb_test` at this baseline, so the
read-side effect is not yet measurable — correctly stated as a limit by the input and correctly *not*
quantified.

**Recommendation** — Executable as a decision, and the input is right to route it to phase 05: the
smaller edit is in the repository, not the schema. The input also correctly refuses to re-litigate
phase 11's measurement. Verified against the refutation: MIG-002 asserts **no** index-size figure and
**no** "containment is 2.6x slower" claim anywhere in its body, consequence or recommendation. The
only quantitative statement it makes is that the index is "paid for on every insert, update and
delete", which is a write-cost statement, not the refuted 9 872 kB / 1.87x figure and not the
refuted 5 265 kB-per-200k figure either. The two documents do not conflict.

### MIG-003 — `f47ac18b5b9e` drops an object no revision creates, and its reverse recreates a different object

**Verdict** — confirmed, on two of its three numbered facts. Band carried unchanged at MEDIUM (the
rubric assigns MEDIUM to "a revision whose reverse cannot restore what its forward removed", and
Block 4/9 assign it to an object whose lifecycle lives only in a comment). One numbered fact is
**refuted by its own cited evidence** and one of the two recommended fixes would introduce the
asymmetry the finding claims to remove — recorded as `VAL-14-003`. No re-grade.

**Severity** — MEDIUM

**Zone** — "Each Revision's Reverse against Its Forward"

**Observation** — Facts 1 and 3 reproduce exactly. The forward
(`alembic/versions/f47ac18b5b9e_remove_redundant_dashboard_filters_index.py:36`) is the single
statement `DROP INDEX IF EXISTS idx_dashboard_filters_dashboard_id`; the reverse (`:50-52`) is a
single `CREATE INDEX IF NOT EXISTS … ON dashboard_filters (dashboard_id, filter_id)`. A
repository-wide search for `idx_dashboard_filters_dashboard_id` returns five hits, all inside this one
revision (`:5`, `:33`, `:36`, `:42`, `:51`) — no other revision and no model declares it.
`000000000000:169-173` creates `dashboard_filters` with `PRIMARY KEY (dashboard_id, filter_id)` and no
further index, and its own comment at `:166` reads "No additional index needed - PK index already
covers all queries". The live table in `bidb` carries exactly one index, `dashboard_filters_pkey
btree (dashboard_id, filter_id)`. Fact 3 holds: the object's origin is asserted only in prose at `:5`
("created externally (e.g., manually or via a non-versioned migration)") and `:42`.

Fact 2 does not survive. The input reads the docstring at `:5-7` — "The non-unique
idx_dashboard_filters_dashboard_id index … is redundant — it covers the same column set as the PK" —
as describing a single-column `(dashboard_id)` index. The quoted words do not say that. The PK is
`(dashboard_id, filter_id)`, so "the same column set as the PK" denotes `{dashboard_id, filter_id}` —
precisely the two-column shape the reverse creates. Taken at face value the docstring and the reverse
**agree**, and the finding's asymmetry does not exist.

**Evidence** — `alembic history` shows the chain linear with a single head; the five-hit search for
the index name; `000000000000:164-175`; `pg_indexes` for `dashboard_filters`; `pg_constraint` for
`dashboard_filters` (one PK, two FKs, two NOT NULL — no other index).

**Consequence** — As filed and narrowed. A downgrade still does not restore a prior state, because
the forward never removed anything on any database this chain can build — which is the surviving
defect, and it is the one Block 4 and Block 9 actually enumerate. The live blast radius is nil, as
the input correctly states.

**Recommendation** — Executable, but only its second branch. The second branch (retire the revision,
fold the rationale into `000000000000`'s docstring) is correct and is the smaller end state. The
**first** branch must not be taken as written: changing the reverse to a single-column
`(dashboard_id)` would make the reverse contradict the docstring that currently describes it, and
would install a narrower index than the one the prose claims existed. If the intent is to keep the
revision, the correct action is the opposite — reconcile the docstring and the reverse, not
restrain the reverse.

### MIG-004 — The application role and every privilege the application needs are established outside the chain, and no restore path re-establishes them

**Verdict** — confirmed on the load-bearing half, **one stated mechanism refuted by direct
measurement**. Band carried unchanged at MEDIUM (rubric: "a grant established where no revision
declares it"). See `VAL-14-004`. No re-grade.

**Severity** — MEDIUM

**Zone** — "Which Environments Obtain Their Schema from the Chain, and Which Obtain It Otherwise"

**Observation** — The core structural claim reproduces. A search of `alembic/` for
`GRANT|REVOKE|CREATE ROLE|ALTER DEFAULT PRIVILEGES` returns **no files found** — no revision creates a
role or states a grant. Both outside-chain sites reproduce: `docker/init-scripts/01-create-app-role.sh`
issues `CREATE ROLE mkobi_app WITH LOGIN PASSWORD` (`:24`), `GRANT CONNECT ON DATABASE` (`:29`),
`GRANT USAGE ON SCHEMA public` (`:32`), table and sequence grants (`:35`, `:38`) and two
`ALTER DEFAULT PRIVILEGES` (`:41-42`); `db/starter.py:263`, `:277`, `:279-280`, `:282-283` carry the
same set. The duplication the input names is real and I confirm the divergence it reports: the shell
script grants `USAGE` on the schema while `starter.py:277` grants `USAGE, CREATE`.

**Evidence** — `pg_dump -U postgres -d bidb --schema-only` executed inside the container and filtered
in place (no host file was written, per the project's `pg_dump` rule). The measurement contradicts the
input's evidence sentence in two of four counts:

| statement in the input | measured |
|---|---|
| "zero `CREATE ROLE`" | **0** — correct |
| "zero `ALTER DEFAULT PRIVILEGES`" | **2** — refuted |
| "24 `OWNER TO` lines" | **22** |
| `GRANT` lines to `mkobi_app` | 16 `GRANT` + the 2 `ALTER DEFAULT PRIVILEGES` |

Both emitted lines are exactly the two default-privilege rules:

```
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO mkobi_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT USAGE ON SEQUENCES TO mkobi_app;
```

**Consequence** — The first consequence is confirmed and is the serious half: the dump carries
`GRANT USAGE ON SCHEMA public TO mkobi_app;` and sixteen per-object grants but **no `CREATE ROLE`**, so
a restore onto a server whose volume was never initialised fails on the first `mkobi_app` grant, the
role never comes into existence, and the application cannot connect at all — with nothing in the chain
that would notice. The second consequence, as written, is **wrong**: the input concludes that "the
role and the forward-looking default-privilege rule do not [survive a restore]". The role does not
survive; the forward-looking rule does, because `pg_dump` carries it and `pg_restore` replays it under
the same `FOR ROLE postgres` grantor.

**Recommendation** — Executable as written for the surviving half; the role half is correctly stated
and the recommendation (a single referenced SQL artefact plus a deployment-document note that the role
is not part of a dump) is unaffected by the refuted half. No change needed to the recommendation.

### MIG-005 — The only path that creates a database is not in the chain, records nothing, and nothing checks that its target is a test database

**Verdict** — confirmed. Band carried unchanged at MEDIUM (rubric: "an environment whose schema the
chain does not describe"). The first-hand observation is re-classified — see `VAL-14-002`. No
re-grade.

**Severity** — MEDIUM

**Zone** — "Which Environments Obtain Their Schema from the Chain, and Which Obtain It Otherwise"

**Observation** — Re-derived from the executing path and confirmed in full.
`DatabaseStarter.recreate_test_database` (`src/mkobi/db/starter.py:193-296`) is the only routine in
the repository that establishes a database. The order is: validate the identifier shape at
`:208-209` (`re.match(r"^[a-zA-Z0-9_]+$", db_name)` — SQL-injection defence, nothing about what the
name denotes); `pg_terminate_backend` at `:244-251`; `DROP DATABASE IF EXISTS` and `CREATE DATABASE`
at `:254-259`; grants at `:261-283`; and only then `_apply_migrations(test_url)` at `:294`. Nothing
consults `alembic_version`, nothing is reversible, and the project's only advisory lock is reached
inside that final step.

The advisory lock placement is confirmed exactly as the input and phase 01 both state:
`alembic/env.py:112-127` acquires `pg_advisory_lock(MIGRATION_ADVISORY_LOCK_KEY)` inside
`do_run_migrations`'s connection, i.e. inside the chain replay — strictly after the drop at
`starter.py:254-259`. The input cites `alembic/env.py:114-127`; the acquisition is at `:115-117`
inside a `try` that opens at `:113`. Both anchors resolve.

**Evidence** — `tests/conftest.py:400-436` read in full (see the TOPO-004 adjudication below);
`starter.py:193-296`; `alembic/env.py:105-138`; the two doors at `starter.py:188-189` (`startup()`
also calls `recreate_test_database()` when `env == TEST or recreate_test_db`) and `starter.py:430-435`
(the CLI).

**Consequence** — As filed, and understated nowhere. The rollout caveat the input attaches is correct
and is the one thing a reviewer must not skip: `tests/conftest.py:417-418` builds
`f"bidb_test{worker_suffix}"` under xdist, so the target name is *derived*, not equal to
`config.database.test_dbname`. A guard written as the input recommends
(`db_name == config.database.test_dbname`) would refuse every parallel run. The input already flags
this in its Rollout Safety section; it is correct and must survive into remediation.

**Recommendation** — Executable, with the ordering the input gives. Two changes, both small; the
input is right that the lock must be taken on the target before `pg_terminate_backend` and therefore
cannot delegate to `alembic/env.py`.

### MIG-006 — `000000000001` performs nothing in either direction and exists only to occupy a position

**Verdict** — confirmed. Band carried unchanged at LOW; the rubric assigns LOW verbatim to "a revision
that asserts nothing … a comment that is the only record of a decision". No re-grade.

**Severity** — LOW

**Zone** — "The Chain's Own Residue: Revisions and Statements That Assert Nothing"

**Observation** — Re-anchored and exact. `alembic/versions/000000000001_add_missing_fk_indexes.py:23`
is `pass` and `:28` is `pass`. The docstring at `:7-9` states the standing obligation — "Kept for
backward compatibility - existing databases may have already applied the indexes via this migration"
— and no database inside this chain can satisfy it, because its predecessor already creates every
index the name refers to: `000000000000:105-110` (`idx_dashboards_layout_id`,
`idx_dashboards_created_by`), `:200-214` (the five `aggregated_data` indexes) and `:247-250`
(`idx_registration_requests_reviewed_by`). The comments at `:104` and `:247` say so outright
("FK indexes (matching ORM `__table_args__)").

**Evidence** — File read in full (28 lines); `000000000000:103-110`; `alembic history` places
`000000000000 -> 000000000001 -> 000000000002` in a linear chain.

**Consequence** — As filed. No data or schema effect; the cost is that the chain misdescribes its own
shape and the docstring is the only record of a decision to keep a migration whose stated purpose
cannot be performed.

**Recommendation** — Executable and correctly chosen: the docstring correction is the right call and
the input's refusal to renumber is right, since the identifier is the stable name in an already-deployed
chain.

### MIG-007 — `b749bc53b1ee` names, documents and performs three different index shapes

**Verdict** — confirmed, with the artefact count corrected. Band carried unchanged at LOW. No re-grade.

**Severity** — LOW

**Zone** — "The Chain's Own Residue: Revisions and Statements That Assert Nothing"

**Observation** — The substance reproduces and the load-bearing part is reproduced independently. The
filename is `b749bc53b1ee_add_processing_logs_status_index.py`; the module docstring title at `:1` is
"Add index on processing_logs.status for cleanup query performance"; the body at `:22-25` executes
`CREATE INDEX IF NOT EXISTS idx_processing_logs_status_finished_at ON processing_logs (status,
finished_at)`. `src/mkobi/db/models/processing_logs.py:74-78` declares exactly three indexes —
`dashboard_id`, `(status, finished_at)` and `(status, started_at)` — and **no** single-column
`(status)` index, matching the live inventory exactly.

One correction to the finding's own arithmetic: the input counts **three** artefacts disagreeing and
states that "the OpenAPI-facing summary at line 1 of the `upgrade` docstring at line 21 repeats it".
It does not repeat it. The `upgrade` docstring at `:21` reads "Add composite index on
processing_logs (status, finished_at) for cleanup queries" — it correctly names the composite and is
the one artefact in the file that is right. **Two** artefacts disagree (the filename and the module
docstring title), not three. This changes nothing about the finding, its band or its recommendation,
and is recorded here rather than as a separate identifier.

**Evidence** — File read in full (30 lines); `processing_logs.py:74-78`; `pg_indexes` for
`processing_logs` (four indexes, none on `status` alone); and decisively, `uv run alembic history`,
which prints for this revision:

```
b749bc53b1ee -> f47ac18b5b9e, Add index on processing_logs.status for cleanup query performance.
```

The claim that the chain's own reader-facing output misdescribes the object is therefore reproduced
end to end.

**Consequence** — As filed. A reader reconstructing the index set from `alembic history` concludes a
`(status)` index exists. It does not, and its absence as a standalone object is part of why MIG-001's
default query has no ordering access path.

**Recommendation** — Executable as written: correct the docstring title only, leave the identifier and
filename alone. Note that correcting the *title* is what changes `alembic history`'s output; correcting
the `upgrade` docstring is optional, since it is already correct.

### MIG-008 — `users_email_length_check` is chain-only, model-silent, and cannot fire

**Verdict** — confirmed in all three parts. Band carried unchanged at LOW. No re-grade.

**Severity** — LOW

**Zone** — "Schema Objects with No Counterpart in the Model Layer"

**Observation** — Reproduced in full. `alembic/versions/000000000000_initial_migration.py:252-265`
creates the constraint inside a `DO $$` block whose guard filters `pg_constraint` on `conname` alone,
with no `conrelid` filter, exactly as the input reports. A search for `CheckConstraint` across
`src/mkobi` returns **zero hits** across the ten model modules, while `__table_args__` returns ten —
the second declaration genuinely cannot see this constraint. `users.email` is `VARCHAR(255)` in the
chain at `:59` and `String(255)` in the model.

**Evidence** — The live constraint and column type, and the reachability probe, all reproduce on
PostgreSQL 18.6:

```
SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint
 WHERE conrelid='users'::regclass AND contype='c';
 users_email_length_check | c | CHECK ((length((email)::text) <= 255))

information_schema.columns -> character varying, character_maximum_length = 255

-- on a TEMP table carrying the same type and constraint:
INSERT ... VALUES (repeat('x',256))  ->  ERROR: value too long for type character varying(255)
```

The type constraint fires first and the `CHECK` has no reachable input.

**Consequence** — As filed, and the composed observation about the drift gate is correct and worth
keeping: `alembic check` compares the **live database** against the **model layer**, never the chain
against either, and Alembic's autogenerate does not compare `CHECK` constraints. This divergence is
therefore structurally invisible to the only gate the project owns, which is why phase 10's "no drift
today" is a true and insufficient result rather than a contradiction of it.

**Recommendation** — Executable as written and correctly scoped: drop the constraint in a new revision,
and add the `conrelid` filter to the guard at `000000000000:255-262`. The temporary probe table used
to establish reachability was session-local and left nothing behind.

## Adjudications of prior findings

### TOPO-004 (phase 01, HIGH) — the premise correction is **upheld**, and it escalates the finding

The most consequential thing in the input is this adjudication, and it is correct. Phase 01's
validated report rests the safety of TOPO-004 on a premise about the test harness; the input says that
premise is wrong, and I verified it from the executing path rather than from either report's account
of it.

**What phase 01 actually validated.** `.ai/audit/99-validation/01-process-architecture-validated-findings.md:207-208`
states that "a copy of this path is never executed by the harness: `conftest.py:559-560` builds the
client with `httpx.ASGITransport(app=app)`, which does not emit ASGI lifespan events, so
`DatabaseStarter.startup()` never [runs]", and its Recommendation at `:706` proposes to re-word
TOPO-004 as "armed in the test tier today; the only thing preventing the drop is that …".

**What the executing path does.** `tests/conftest.py:400-436` is the `setup_test_database` fixture. It
is `@pytest.fixture(scope="session")` (`:400`); it builds `DatabaseStarterConfig(…,
recreate_test_db=True)` (`:427-432`); and it then executes, at `:433`:

```python
await DatabaseStarter(starter_config).recreate_test_database()
```

That is a **direct, unconditional call**. It is not a lifespan effect, and the `ASGITransport`
bypass at `:559` — which is real, and which does prevent `starter.startup()` from running — is
irrelevant to it, because conftest invokes the same function by a different door. `recreate_test_database`
executes `pg_terminate_backend` at `db/starter.py:244-251` and `DROP DATABASE IF EXISTS` /
`CREATE DATABASE` at `:254-259` **before** it reaches `_apply_migrations` at `:294`, and the project's
only advisory lock is acquired inside that last call, at `alembic/env.py:115-117`.

**Ruling — upheld, with one precision the input overstates.** The drop executes; phase 01's premise is
wrong; and the correction raises TOPO-004's exposure rather than lowering it. The precision: the
fixture runs once per session **that requests it**, and it is requested by `async_test_engine`
(`conftest.py:440`) and `baseline_data` (`conftest.py:501`) — so "on every pytest session" is exact for
the suite's database-touching tests, which is the suite in practice, but a session running only
`mock_db` unit tests would not trigger it. That refinement does not rescue phase 01's premise: nothing
in the harness prevents the drop, and phase 01's Recommendation, taken as written, would record a
false safety claim in a validated report.

**Independent runtime confirmation.** I did not run the suite, and I did not invoke
`recreate_test_database`. But at 19:57 UTC `bidb_test` contained **zero tables** — no `users`, no
`processing_logs`, and no `alembic_version` at all — and `pg_stat_file` on its `PG_VERSION` reports a
modification time of **2026-09-30 19:46:10+00**, eleven minutes before my session began and with zero
active backends attached. The drop executed; the migration replay that should have followed it did
not complete. This is the third-party confirmation of the same mechanism the input observed
first-hand, and it is also the sharpest available illustration of MIG-005's ledger blind spot: a
dropped-and-rebuilt database leaves exactly the trace a clean migration run leaves, and a database
caught mid-rebuild leaves a schema that does not exist. **I did not restore it** — it was in this
state when I first read it, restoring it would write to a database peers are actively using, and
`recreate_test_database` is the only supported way to rebuild it.

### TOPO-007 (phase 01, LOW) — ownership ruling upheld; the input's own verification of it is partly wrong

The ownership ruling is correct and I uphold it. Lint coverage is not process topology and not schema
evolution; `14-audit-schema-migrations.md:26-27` assigns "whether a drift gate exists, is loaded and
would notice" to phase 08, and gate coverage is the same question one level up. Phase 08 owns it.
Not re-filed here, correctly.

The structural facts reproduce: `Makefile.ps1:222` is `ruff check src/ tests/` and `:230` is
`mypy src/`, neither of which reaches `alembic/`; `pyproject.toml:169` is
`[tool.mypy] exclude = ["alembic/"]`, exactly as cited. But the input's *verification* of the ruff half
is wrong in two of three particulars — see `VAL-14-002`.

### QLT-008 (phase 08) — ruling upheld; the schema is doing its job

Upheld, and re-derived from the store rather than from either report. The live
`dashboard_permission_level` holds exactly `view, edit, admin` at enum sort orders 1, 2, 3, and
`dashboard_access.permission`'s `udt_name` is `dashboard_permission_level` — a native enum, not
`varchar`. `DashboardPermission` in `src/mkobi/models/enums.py` is a `StrEnum` holding exactly `VIEW`,
`EDIT`, `ADMIN`. The enum and the store agree exactly, in both directions, which is precisely the
opposite of what phase 08's validator found at the application boundary.

The 500 is the enum working. `services/dashboard_service.py:374` calls
`self._validate_permission(permission)`, whose body at `:482-491` maps `read`→`view` and `write`→`edit`
into `normalized` and calls `DashboardPermission(normalized)` to validate — then discards
`normalized`. Line `:389` writes `permission=permission`, the **un-normalised** value. So
`{"permission": "read"}` passes validation and is written verbatim, and PostgreSQL refuses it.
The input's ruling is right: the type-versus-enum divergence lives between the Pydantic boundary and
the service, both phase 08's territory; the fix is to return `normalized` and type the parameter, not
to widen the enum; and had the column been `VARCHAR` this would indeed have been a
data-corruption finding rather than a rejection. One citation slip: the input describes
`models/access.py:11` as `permission: str = "view"`; line `:11` is `required_permission: str = "view"`
and line `:30` is `permission: str = "view"`. Both are bare-`str` boundaries, so the ruling is
unaffected.

### TST-012 (phase 09), DP-003 (phase 05), PERF-001 (phase 11) — all three deferrals upheld

**TST-012.** Upheld. `tests/conftest.py:468-497` implements the SAVEPOINT pattern — `begin_nested()`
before the yield at `:491`, `rollback()` in the `finally` at `:495` — so the fixture is doing what a
schema fixture should, and any surviving rows come from a code path that opens its own session. Phase
03 owns that class of defect; no phase-14 finding arises. The input's warning that a remediation must
not stop at the fixture is correct and worth carrying forward.

**DP-003.** Upheld. `uq_aggregated_data_dashboard_graph_dims` is declared identically in the chain
(`000000000000:212-214`) and the model layer, and the live definition matches both:
`btree (dashboard_id, graph_id, ((dims)::text))`. Whether `jsonb`'s canonical text rendering is a
faithful identity, and whether `'1'` can be prevented from storing separately from `1`, is phase 05's
correctness claim. No distinct schema claim exists, and the input correctly declines to manufacture
one.

**PERF-001.** Upheld, and specifically checked against the refutation as instructed. Phase 11's
validator refuted the project's own JSONB-containment recommendation: the GIN index is in neither
plan, `idx_scan=2` rather than 0, and the 9 872 kB figure was the whole 375 000-row table rather than
a per-200 000-row cost — a 1.87x overstatement against the true 5 265 kB per 200 000 rows. **MIG-002
repeats none of it.** A search of MIG-002's observation, evidence, consequence and recommendation for
either figure returns nothing; it carries no size number and no speed ratio of any kind. Its only
quantitative statement is that `jsonb_ops` is "paid for on every insert, update and delete of
`aggregated_data`", which is a write-cost structural claim about opclass membership, not a
measurement. MIG-001 is likewise free of any size or ratio figure, and it says so itself rather than
quantifying. The two reports do not conflict, and the phase-11 refutation stands undisturbed.

## Adjudication of MIG-005's first-hand observation — product defect, not an audit artefact

The input closes MIG-005's evidence with a first-hand observation: `aggregated_data` in `bidb_test`
returned 4 rows, and roughly twenty minutes later returned 0, with no action by the audit. It
attributes this to a concurrent session's `setup_test_database` fixture. That attribution is correct,
and the ruling is unambiguous: **this is a finding about the product, not about this audit's
environment.**

The distinction is worth stating precisely. What the audit environment supplied was *concurrency* —
several agents sharing one `bidb_test` on host port 5434. What fired is *shipped code* at
`src/mkobi/db/starter.py:193-296`, reachable from two documented doors, with no mutual exclusion
(the only advisory lock is taken afterwards, inside the chain replay) and no target-identity guard.
The identical effect is reachable with no audit in the picture: two developers running the suite on a
shared host, or two overlapping CI jobs against one `bidb_test`. The code does not know or care
whether a peer is a colleague or an agent.

What concurrency changes is the **rate**, not the defect — and the input is careful about this. It
reports the observation as evidence that the path executes, not as a frequency claim, and its
Consequence says "the present, observable consequence" rather than projecting one. No defect is filed
against the input for this. I add what it could not know: at 19:57 UTC `bidb_test` held **zero
tables**, its `PG_VERSION` mtime was 19:46:10 — before my session began, with zero active backends —
and no `alembic_version` row existed at all. The drop executed; the replay that should have followed
did not. That is MIG-005's ledger blind spot observed from the outside, and it is why the ruling is
the product's rather than the environment's.

## Findings — validation namespace `VAL-14-`

Validation-level findings live in their own section and never share the `Severity` column with the
audited `MIG-` findings, because the two are graded on different scales.

### VAL-14-001 — MIG-001's surviving-`Sort` argument does not prove what it is offered as proving, and its cost sentence overstates the sort

**Severity** — LOW

**Observation** — MIG-001 rests its proof on this sentence: "The `Sort` node survives both settings
off. The only plan the planner can construct is a full traversal of the composite index followed by a
sort of everything it read." Both halves are wrong as stated, and the input's own third `EXPLAIN`
contradicts the first.

`enable_seqscan=off` and `enable_bitmapscan=off` are **cost penalties, not prohibitions**. The input's
third query demonstrates it directly — the planner chose `Seq Scan on processing_logs / Disabled:
true`, i.e. it took a path it had been "forced" out of. So the planner had at least three
constructions available (index scan + sort, penalised sequential scan + sort, and — had such an index
existed — an ordering index scan with no sort), and the survival of one `Sort` shows only that the
chosen construction needed one. It cannot show that no construction was available without one. The
isolation the input draws is valid for the variable it varies — adding the leading equality does
remove the sort — but the absence of an ordering-capable index is proven by the `pg_indexes` inventory
(four indexes, none leading with `started_at`), not by the plan.

The Consequence sentence overstates the second half: "it re-reads and re-sorts the whole
`processing_logs` table on every page". With `LIMIT 100` present, PostgreSQL uses a top-N heapsort, so
it *reads* every qualifying row and keeps the top 100; it does not fully sort them. The traversal is
the cost. The `OFFSET` repetition point stands either way.

**Evidence** — The three reproduced `EXPLAIN` outputs, of which the third contains
`Seq Scan on processing_logs / Disabled: true`; `pg_indexes` for `processing_logs`; and the
counterfactual the input did not run: on a **temporary** 50 000-row table carrying the same two
composite indexes and both scan types disabled, the same three plan shapes reproduce, and adding
`CREATE INDEX i_lead ON mig14_pl (started_at DESC)` removes the `Sort` entirely and yields
`Index Scan using i_lead`. The temporary table was session-local and left nothing behind.

**Consequence** — No remediation consequence. MIG-001's conclusion is correct, its band is right, and
its recommendation is verified to work by the counterfactual. A reader who acts on the finding without
repairing the argument reaches the same correct action. Drift in the evidence, not a defect in the
finding.

**Recommendation** — Restate the proof as the static inventory plus the counterfactual; drop the "only
plan the planner can construct" claim; replace "re-sorts the whole table" with "reads every qualifying
row and top-N sorts it".

### VAL-14-002 — The input's verification of TOPO-007 misreports the ruff result it claims to have run

**Severity** — LOW

**Observation** — The input offers this as its own verification rather than on report: "`uv run ruff
check alembic/` returns `Found 4 errors`, all `UP007` at
`alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py:17` and `:18`, both
auto-fixable."

I ran it. The count of 4 is right; the rule composition and the line set are both wrong. The actual
result is **one `UP035` and three `UP007`**, at lines **8, 16, 17 and 18**:

- `:8` `from typing import Sequence, Union` → `UP035` (import from `collections.abc` instead) — **not** `UP007`
- `:16` `down_revision: Union[str, Sequence[str], None]` → `UP007` — **not listed by the input**
- `:17` `branch_labels: Union[str, Sequence[str], None]` → `UP007`
- `:18` `depends_on: Union[str, Sequence[str], None]` → `UP007`

So the input attributes all four to one rule and names two of the three `UP007` sites. The
conclusion it draws — that `alembic/` sits outside both gates — is unaffected, and so is the
remediation it sketches: `ruff check --fix alembic/` clears all four regardless of rule code.

**Evidence** — `uv run ruff check alembic/` at `0717b65` returns `Found 4 errors. [*] 4 fixable with
the --fix option.`, with `UP035` at `:8:1` and `UP007` at `:16:16`, `:17:16`, `:18:13`. The file read
at `:1-30`.

**Consequence** — Drift only. TOPO-007 is a real gate-coverage gap owned by phase 08, its band is
right, and a maintainer applying the fix gets the same result either way. No wrong approval.

**Recommendation** — Correct the parenthetical to "1 × `UP035` at `:8`, 3 × `UP007` at `:16-18`".

**Cross-phase conflict, recorded and not resolved here.** Phase 01's own validation report already
filed a finding about this same command, `VAL-002` in
`.ai/audit/99-validation/01-process-architecture-validated-findings.md`, and the two reports disagree
about it in opposite directions. Phase 01's `VAL-002` states: "`ruff check alembic/` returns **4
errors**, all in one revision file: `alembic/versions/20250915_0004_*.py:1,3,10,12` (`UP035`
deprecated `typing` import, `UP007` `Optional`/`Union`)." Its rule composition is **right** and the
input's is wrong; its file is wrong and the input's is right. I re-ran the command and searched the
repository and the full git history: **no file matching `20250915_0004_*` exists now or ever has** in
this repository — `Get-ChildItem -Recurse -Filter "*20250915*"` and `git log --all -- "*20250915*"`
both return nothing. The chain's revisions are the eight identifiers this report read
(`000000000000` … `82739c97fde1`). The two reports therefore reach opposite conclusions about the same
subject, and one of them cites a path that does not resolve. **Phase 01 owns the repair of its own
report**; I do not renumber or re-file `VAL-002`, and phase 14's adjudication of TOPO-007 stands on
the measurement reproduced here.

### VAL-14-003 — MIG-003's second numbered fact is refuted by the docstring it quotes, and its first recommended fix would create the asymmetry it alleges

**Severity** — MEDIUM

**Observation** — MIG-003 files three numbered facts. Fact 2 states: "**The reverse creates a
different object than the forward removed.** The module docstring (lines 5-6) describes the dropped
index as 'The non-unique idx_dashboard_filters_dashboard_id index … covers the same column set as the
PK', i.e. single-column `(dashboard_id)`."

The quoted words do not support the gloss. The primary key is `(dashboard_id, filter_id)` — read at
`000000000000:172` and in the live `pg_constraint` as `PRIMARY KEY (dashboard_id, filter_id)`. "The
same column set as the PK" therefore denotes `{dashboard_id, filter_id}`, which is exactly the shape
the reverse creates at `f47ac18b5b9e:50-52`. Read at face value the docstring and the reverse
**agree**. The only evidence for the single-column reading is the index *name*, and the name is not
what the finding cites.

This matters because it is not inert. The Recommendation offers two branches, and the first — "give
the reverse the index definition the docstring describes (single-column `(dashboard_id)`) so a
downgrade restores the documented prior state" — would make the reverse contradict the very docstring
the finding relies on, installing a narrower index than the prose claims existed. A reader who follows
branch one would introduce the defect the finding is about. Branch two (retire the revision) is
unaffected and remains correct.

The finding survives on facts 1 and 3, which reproduce exactly: no revision or model declares the
index (five repository-wide hits, all inside this one revision), and its origin exists only in prose.
Its MEDIUM band is right and no re-grade is applied.

**Evidence** — `f47ac18b5b9e:1-16` (docstring), `:36` (forward), `:50-52` (reverse);
`000000000000:169-173`; live `pg_constraint` for `dashboard_filters`; a repository-wide search for
`idx_dashboard_filters_dashboard_id` returning five hits, all in this file.

**Consequence** — A reader must repair the report before acting on branch one of the recommendation.
Taking branch two, or taking no action, produces no harm.

**Recommendation** — Strike fact 2 and its supporting sentence. If the revision is kept, the correct
action is to reconcile the docstring with the reverse (the docstring is the sloppier of the two); if
single-column really was the intent, that intent has to be stated deliberately and the reverse changed
on purpose — not inferred from the quoted prose.

### VAL-14-004 — MIG-004's evidence records a measured absence that is not there, and one of its two consequences is refuted

**Severity** — MEDIUM

**Observation** — MIG-004's Observation states: "`pg_dump --schema-only` contains … but **no `CREATE
ROLE` and no `ALTER DEFAULT PRIVILEGES`**. The per-table grants survive a restore; the role and the
forward-looking default-privilege rule do not." Its Evidence states it filtered the dump for
`GRANT|REVOKE|ALTER DEFAULT|CREATE ROLE` and found "zero `CREATE ROLE` and zero `ALTER DEFAULT
PRIVILEGES`".

I ran the same filter. The `CREATE ROLE` half is right. The `ALTER DEFAULT PRIVILEGES` half is not: the
dump carries **two** such statements, and they are precisely the two the outside-chain sites
establish.

```
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO mkobi_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT USAGE ON SEQUENCES TO mkobi_app;
```

`pg_dump` emits `pg_default_acl` entries and `pg_restore` replays them under the same `FOR ROLE
postgres` grantor the chain runs as, so the forward-looking rule **does** survive the round trip.
MIG-004's second Consequence — that the forward-looking half of the grant model "exists only in two
shell/Python fragments" and that "the chain … reproduces none of it" — is wrong in its restore half.
The same Evidence sentence also reports "24 `OWNER TO` lines" against a measured 22, and the same
Observation says "further `GRANT` lines for every remaining table and both sequences", which is 16
`GRANT` lines plus these 2.

The finding survives on the half that matters and the half that is dangerous: `CREATE ROLE` is absent
(measured 0), so a restore onto a server whose volume was never initialised fails on the first `GRANT
… TO mkobi_app`, the role never comes into existence, and the application cannot connect at all, with
nothing in the chain that would notice. That is a real MEDIUM under the rubric ("a grant established
where no revision declares it"). Only the default-privilege half falls.

**Evidence** — `pg_dump -U postgres -d bidb --schema-only` executed inside `mkobi-db-1`, filtered in
place (no host file written, per the project's `pg_dump` rule). Counts: `CREATE ROLE` = **0**,
`ALTER DEFAULT PRIVILEGES` = **2**, `OWNER TO` = **22**, `GRANT … mkobi_app` = **16**. The two emitted
lines quoted above. `Makefile.ps1:285` and `:304` confirmed; note `pg_restore` runs without
`--exit-on-error`, so it reports the failed grants and continues rather than aborting the restore.

**Consequence** — The reader must repair the report before acting on its second consequence. Acting on
the recommendation is unaffected: it concerns the role, which is correctly identified.

**Recommendation** — Correct the Evidence sentence to "zero `CREATE ROLE`, **two** `ALTER DEFAULT
PRIVILEGES`, 22 `OWNER TO`"; delete the sentence claiming the default-privilege rule does not survive a
restore; and narrow the second consequence to what is true — the rule round-trips through `pg_dump`,
but it is still established only outside the chain, so a database built any other way does not have
it.

### VAL-14-005 — Five of the input's mechanical line citations are off against the working tree

**Severity** — LOW

**Observation** — Anchors were resolved mechanically rather than accepted, and five citations do not
land on the content they are offered for. The lines exist in every case, so none is a reference into
non-existent lines, but each points elsewhere:

| cited | actual | what is at the actual line |
|---|---|---|
| `Makefile.ps1:221` (`lint` target) | `Makefile.ps1:222` | `ruff check src/ tests/` |
| `Makefile.ps1:229` (`typecheck` target) | `Makefile.ps1:230` | `mypy src/` |
| `config.py:219` (`dbname`) | `config.py:221` | `dbname: str = "bidb"` |
| `config.py:222` (`test_dbname`) | `config.py:224` | `test_dbname: str = "bidb_test"` |
| `alembic/env.py:114-127` (lock) | acquisition at `alembic/env.py:115-117`, `try` opens at `:113` | `pg_advisory_lock` |

By contrast `pyproject.toml:169` (`[tool.mypy] exclude = ["alembic/"]`), `Makefile.ps1:285`/`:304`,
`starter.py:193-296`, `:208-209`, `:244-259`, `:261-283`, `:294`, `:395-418`, `:430-435`,
`conftest.py:417-425`, `:433`, `:559`, and all eight `MIG-00x` zone quotations resolve exactly as
cited.

**Evidence** — Line-number resolution on `Makefile.ps1`, `src/mkobi/config.py` and `pyproject.toml`;
`alembic/env.py:105-138` read in full.

**Consequence** — Drift with no remediation consequence. No finding, recommendation or adjudication in
the report turns on any of these anchors; each names the right artefact.

**Recommendation** — Correct the five offsets before the report is used as a remediation worklist.

## Distribution

The eight audited findings fall where the input places them, and that distribution survives
adjudication. Two HIGH findings, both in Block 6, both on the two tables the read path depends on. Three
LOW findings in the chain's own residue and unowned-object space, none of which touches a column, a
key or a constraint. Three MEDIUM findings on authority that lives outside the chain. No audited
finding contradicts the model layer, and none touches a data-loss or corruption path — which I
re-derived rather than accepted: the live schema agrees with the model layer on all twelve tables,
all thirteen foreign keys with identical `ON DELETE` actions, and all six native enum types in both
directions.

`src/mkobi/db/starter.py` carries the most, as the input says: MIG-005 in full and the second half of
MIG-004, and it is the only module in the repository that both establishes a database and grants
privileges while remaining outside the chain.

The five validation-level findings fall differently. They are defects in the *report*, not the system:
three in the evidence of adjudications (VAL-14-001, VAL-14-002, VAL-14-005) and two in the reasoning
of filed findings (VAL-14-003, VAL-14-004). No validation-level finding describes a product defect,
and none of the eight `MIG-` findings was found to be a false alarm, stale, or mis-graded.

## Cross-Finding Analysis

**One cross-phase conflict, unresolved here and owned elsewhere.** Phase 14's TOPO-007 verification
and phase 01's `VAL-002` disagree about the same `ruff check alembic/` result in opposite directions —
rule composition on one side, file path on the other — and phase 01's cited file does not resolve
against the working tree or against git history. Recorded in full under `VAL-14-002`. **Phase 01 owns
the repair of its own report.** Neither identifier is renumbered and no finding is duplicated.

**One material correction that must propagate upstream.** Phase 14's adjudication of TOPO-004 is
upheld and it contradicts an already-validated phase-01 finding on the load-bearing premise. Phase 01
validated TOPO-004 partly on the statement that the destructive path "is never executed by the
harness" because the harness bypasses the lifespan, and its Recommendation at `:706` proposes to
re-word TOPO-004 as "armed in the test tier today; the only thing preventing the drop is that …". That
premise is false — `tests/conftest.py:433` calls `recreate_test_database()` directly on every session
that requests the fixture — so the proposed re-word would institutionalise a false safety claim in a
validated report. **Phase 01 owns the correction to its own record; the finding identifier TOPO-004
is not renumbered and the band is not re-graded by this phase.** The correction raises TOPO-004's
exposure rather than lowering it, and the roadmap below sequences accordingly.

**Two merges this phase declines to make.** MIG-004 and MIG-005 both concern authority outside the
chain, and the input is right that they are related but not shared-cause — one is over grants, one is
over the database itself, and they are independently fixable. MIG-001 and MIG-002 are both "a declared
access path that cannot serve the declared query", but they fail for different reasons, live in
different files, and are fixed by changes in different layers. Merging either pair would destroy the
separation the roadmap depends on. The input's decision not to merge is upheld.

**One seam check.** Every one of the eight `MIG-` findings falls inside a zone the phase's own
command file assigns to it: Block 6 for MIG-001 and MIG-002, Block 2 for MIG-003, Block 8 for MIG-004
and MIG-005, Block 9 for MIG-006 and MIG-007, Block 4 for MIG-008. All eight zone strings are verbatim
block titles, checked against
`.kilo/commands/audit/phases/14-audit-schema-migrations.md:44-120`. One partial-overlap note rather
than a seam violation: MIG-001's Consequence reasons about table growth and retention window, which
phase 14's scope boundary assigns to phase 11 (`:26-27`). That is blast-radius context inside a
phase-14 finding, not a separate finding, and the input's own access-path note for phase 11 shows the
boundary being respected. No finding is filed outside the input's declared scope.

## Roadmap

The audited roadmap stands as written, with one substitution. Steps are grouped by cause and ordered
by dependency, not by severity.

1. **MIG-005** first, ahead of the input's own ordering, and for the reason the correction to phase 01
   establishes rather than a new dependency. This is the one change that stops a session from
   destroying a peer's work, and it is the one path that executes on every test run against a database
   published on host port 5434. Two edits: a target-identity check in `config.py`, and mutual exclusion
   acquired at the destructive call site rather than inside the chain replay. Prerequisite: nothing.
2. **Correct the phase-01 record** for TOPO-004's premise before the roadmap it feeds is executed. This
   is not a code step and closes nothing in this phase, but the input's correction only protects anyone
   if it reaches the report phase 01's readers hold. Owner: phase 01.
3. **MIG-001** — one revision on top of `82739c97fde1` leading with `started_at`. Additive, reversible,
   verified by counterfactual. Prerequisite: none.
4. **MIG-002** — settle the operator with phase 05 before editing either side. The decision is the
   prerequisite, not the edit.
5. **MIG-003, MIG-006, MIG-007** — the comment-and-reverse pass, one review. MIG-003's first branch
   must be struck per `VAL-14-003`; only the retire-or-reconcile branch is safe.
6. **MIG-004** — collapse the two transcriptions of the grant set into one referenced artefact and state
   in the deployment document that the role is not part of a dump. The default-privilege half of the
   input's justification is refuted (`VAL-14-004`); the role half stands, and the recommendation is
   unchanged. The single artefact must exist before the restore path can be pointed at it.
7. **MIG-008** — one revision dropping `users_email_length_check`, with the `conrelid` filter added to
   the guard at `000000000000:255-262`. Independent of everything above.
8. **Report repairs** — `VAL-14-001` through `VAL-14-005` in `.ai/audit/14-schema-migrations/findings.md`.
   No code; blocks no step.

MIG-001, MIG-003, MIG-006, MIG-007 and MIG-008 are additive or comment-only and no deployed
environment's data depends on them. Only MIG-002's second branch changes observable behaviour, as the
input says.

## Rollout Safety

MIG-001 is a plain `CREATE INDEX` on a live table and takes a write lock for the duration of the build.
On `processing_logs` today — 3 rows in `bidb` — that is instantaneous. The index is unused by the
default query until it lands and is removable with a single `DROP INDEX`; its `downgrade` should carry
the drop, which the input's recommendation implies but does not state.

MIG-002's index drop remains the one step that could surprise, and the input's safe sequence is right:
land the repository change that fixes the operator first, confirm the plan with `EXPLAIN` on
production-shaped data, then drop. Reversal is a single `CREATE INDEX` back. I add one constraint the
input does not: `aggregated_data` is **empty in both live databases** at this baseline, so no `EXPLAIN`
on either can confirm anything about the post-fix plan. The confirmation step is not executable until
there is representative data, and the roadmap should say so rather than treating step 4 as verified by
inspection.

MIG-005's guard is the step most likely to break a working setup, and the input flags the right trap.
`tests/conftest.py:417-418` builds `f"bidb_test{worker_suffix}"` under xdist, so the target name is
derived; a check written as `db_name == config.database.test_dbname` refuses every parallel run. Write
it against the derived value, and run the suite with and without `-n` before and after. The
mutual-exclusion half is the safer of the two: it can only make a destructive operation wait, and
reverting it is removing the acquisition. Roll the two out separately, as the input says.

MIG-004's change is additive but has one ordering constraint the input states correctly: the single
referenced grant artefact must exist before the restore path is pointed at it. Note also that
`pg_restore` at `Makefile.ps1:304` runs without `--exit-on-error`, so a restore onto a server with no
`mkobi_app` role reports each failed grant and continues — the schema and data land, the role does
not, and the application then cannot connect. Whatever monitoring is attached to `restore` should treat
a non-zero exit as the signal, not the absence of visible errors.

## Appendices

### Namespace ruling

Validation-level findings in this report use **`VAL-14-`**, not the flat `VAL-` the validate command
specifies. The deviation is recorded here as instructed and is a collision report, not a second
namespace. The flat prefix is occupied: phases 01 and 02 minted `VAL-001` … `VAL-008` with no phase
qualifier, and phases 06 through 12 adopted the phase-qualified form (`VAL-12-` is declared in
`12-authorization-validated-findings.md`). The audited prefix `MIG-` is declared at
`14-audit-schema-migrations.md:143` and was re-derived from that declaration before minting anything;
a search of the working tree for in-source `MIG-` markers returns none, so no provenance migration is
owed. Phases 13, 15 and 16 run later and will declare their own.

### Baseline

`git rev-parse HEAD` = `0717b65f541d6378984fbf21a84b2067ba3e1294`.
`git status --porcelain` — dirty, exactly as recorded in the front matter: deletions under `.ai/` and
`frontend/coverage/`, and untracked `.ai/audit/**` and `.ai/plans/*`. Nothing was edited, staged,
committed, reverted or stashed. `migration-new` was not run and no migration was applied or reverted.

**Drift from the input's baseline.** The input recorded `05f2779`; HEAD is `0717b65`, one commit
ahead. I did not re-derive the intervening commit from the input's account — I resolved every anchor
mechanically at `0717b65`, and `git diff --stat 05f2779..HEAD` touches only
`src/mkobi/workers/data_worker.py` and `tests/test_file_cleanup.py`, neither of which any anchor,
finding, or adjudication in this report depends on. All anchors in this report were read at the
current tree.

**Working tree moved during this run.** `git status --porcelain` gained `M src/mkobi/config.py` and
`M tests/test_config.py` after my first reading of it. Those are a concurrent peer's remediation
edits, not mine — I edited no code file, and the only file I wrote is this report. Because `config.py`
is the sole code file this report cites a line number from, I re-resolved both anchors after the
change and they are unmoved: `:221` `dbname: str = "bidb"` and `:224` `test_dbname: str = "bidb_test"`,
which is what `VAL-14-005` records. Nothing else in this report depends on a peer's edits.

**Database hygiene.** Read-only throughout. `SELECT`, catalog queries and `EXPLAIN` (never `EXPLAIN
ANALYZE`, so no query was executed) against `mkobi-db-1` / `bidb` and `mkobi-test-test-db-1` /
`postgres`. `pg_dump --schema-only` was run inside the container and filtered in place; no `pg_dump`
output was ever redirected to a host file. **Objects created: two `CREATE TEMP TABLE` probes**
(`mig14_pl`, `mig14_ck`), both session-local and destroyed when their `psql` session exited; **counted
back: 2 of 2, 0 permanent objects created in either database.** No DDL, no `INSERT`, no `UPDATE`, no
`DELETE` and no `DROP` was issued against either database. `bidb_test` was found in a torn-down state
(0 tables, mtime 19:46:10, before this session began) and was **deliberately left as found** —
rebuilding it would write to a database peers are actively using, and `recreate_test_database` is the
only supported way to do it. Neither the dev nor the frontend stack was started, stopped or
reconfigured; no frontend gate was run, so `frontend/coverage/` was not further disturbed.

### Coverage ledger

| block | item count reached | disposition |
|---|---|---|
| 1 — claim re-derived from the executing path | 8 of 8 findings, 7 prior-finding rulings | all anchors resolved mechanically; 2 asserted causes found wanting (`VAL-14-001`, `VAL-14-003`) |
| 2 — vacuous-control angle | 4 gates applied (`ruff`, `mypy`, `alembic check`, xdist worker isolation) | `ruff` and `mypy` confirmed to exclude `alembic/`; each ran and decided something — zero vacuous controls found in this input's support |
| 3 — grade against the audited rubric | 8 of 8 | 0 re-grades; every band matches `14-audit-schema-migrations.md:122-137` |
| 4 — which side moves | 8 of 8 | 3 comment-only (MIG-006, MIG-007, MIG-008), 5 with code consequences; 0 re-typed, 0 merged |
| 5 — recommendation executable | 8 of 8 | 7 executable as written; MIG-003's first branch is not (`VAL-14-003`) |
| 6 — cross-phase conflict, ownership, merge | 2 rival claims examined (TOPO-004 premise; TOPO-007 ruff result) | 1 conflict owned by phase 01; 1 correction owned by phase 01; 2 merges declined |
| 7 — finding-ID namespace integrity | `MIG-` declared, minted and in-source markers searched | declared at `:143`; 8 minted; 0 in-source markers; `VAL-14-` recorded as a deviation |
| 8 — shared template as controlled artefact | 6 front-matter fields, 5 per-finding fields, 8 zone quotations, 1 empty-state rule | all 8 findings carry all five fields; all 8 zones are verbatim block titles; front matter `phase:` is honest |
| 9 — input resting on its own declared blocks | 8 of 8 | MIG-001 and MIG-002's evidence (live `EXPLAIN`) is an independent observation, not a named block; MIG-004 and MIG-005 rest on Block 8, which does name them |
| 10 — validated report as an artefact | 8 audited + 5 validation-level | tally agrees with per-finding verdicts; no identifier renumbered; audited and validation namespaces never share a table |
| 11 — shared angles | vacuous-control and cross-resource side-effect | neither is bound by phase 14 in its own words; no angle is cited by this input without a definition |

**Claims left unsettled, with reasons.**

1. *Downgrade/re-upgrade reproduction on a store.* Not attempted. It requires schema-writing operations
   on `bidb` and `bidb_test`, which peers are actively using, and the task forbids writing outside a
   transaction I control. MIG-003's asymmetry is a static proof that needs no store, so the finding does
   not depend on it; the empirical cycle would only confirm.
2. *Plan shapes against production-shaped `aggregated_data` data.* `aggregated_data` holds 0 rows in
   `bidb` and 0 in `bidb_test`, and `bidb_test` currently holds no tables at all. MIG-002's proof is
   therefore the opclass capability match — read from `pg_amop` for the GIN method — rather than a plan
   measured against real data. The structural claim does not depend on row count; its magnitude does,
   and this report does not quantify it. The input states this limit correctly and I concur.
3. *Whether a least-privilege migration role can replay the chain.* Not tested. Every compose file runs
   the chain as `postgres`, and `mkobi_app` holds no DDL privilege to attempt it with. Unchanged from
   the input's own limit.
4. *Whether MIG-005's `pg_terminate_backend` actually severed a live peer's in-flight session.* I
   observed the drop and the empty database; I did not observe the peer's failure, and I did not run
   the suite. The inference that the teardown at 19:46:10 came from a `recreate_test_database` call
   rests on the code path and the mtime together, not on a captured backend list.