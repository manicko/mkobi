# R5 / `CHTB-6` (`CHT-009`) — Research

**Block:** make a filter value something the repository can actually evaluate; retire `range` per `D-16-2`.
**Scope:** `multiselect` mechanism + `range` removal. No production code, no tests, no git state touched.
**Evidence base:** repository source read directly; PostgreSQL **18.6** probes executed on the live
`mkobi-test` container (`localhost:5434`, database `r5_probe`, created and dropped); `AggregatedFiltersRequest`
and candidate Pydantic shapes executed in-process; backend baseline
(`test_filter_payload_bounds.py` + `test_data_endpoint.py` = **11 passed**) run through
`.\Makefile.ps1 test-select`.

**Confidence legend** used throughout: HIGH = executed or read directly · MEDIUM = read, inference sound ·
LOW = not verified here.

---

## 1. Recommendation

### 1.1 `multiselect` — **path (A), with the membership test in the repository and a widened boundary union.**

Widen `AggregatedFiltersRequest.filters` to admit `list[str]`, and branch
`AggregatedDataRepository._graph_filter_conditions` on the value shape: a list produces a
text-anchored membership predicate, a scalar keeps today's comparison **byte-identical**.

The expression is **`(dims ->> :key) IN (:v1, :v2, …)`** — SQLAlchemy `.astext.in_(values)`.

**Reason, by evidence:**

| Candidate | Verdict | Evidence |
|---|---|---|
| `(dims ->> k) IN (…)` / `= ANY(text[])` | **RECOMMENDED** | Compiles to `(aggregated_data.dims ->> %(dims_1)s) IN (%(p1)s, %(p2)s)` — the *same* `->>` operator as the existing scalar branch, so a `select` and a `multiselect` over one dimension can never disagree. Empty list renders `IN (NULL) AND (1 != 1)` (verified, SQLAlchemy 2.0.50) — an explicit always-false predicate, no syntax error. PG probe returned rows 1,2 for `ARRAY['North','South']`. Wrong key returned 0. |
| `@>` containment | **REJECT** | Structurally cannot express OR over one key. Probe: `dims @> jsonb_build_object('category','North') AND dims @> jsonb_build_object('category','South')` → **0 rows** — a JSONB object cannot hold the same key twice. `jsonb_build_object(ARRAY['category'], ARRAY['North','South'])` is a hard error on PG18: `key value must be scalar, not array, composite, or json`. Single-value `@>` would need one `OR` chain per element, which is N predicates — exactly the plan-time growth `PRF-5` (`models/data.py:483-491`) was written to bound. |
| `jsonb_exists_any` | **REJECT** | Wrong direction. Probe: `jsonb_exists_any(jsonb_build_object('category', NULL), ARRAY['North','South'])` → **0 rows**. It asks "does the candidate hold any of these **key names**", not "does the value equal any of these". For value membership it degenerates to one `exists_any` per value AND-ed — the same AND problem as `@>`. Also not indexable (see §1.2). |
| `@@` jsonpath | **REJECT** | Requires string-interpolating the filter values into a jsonpath literal ⇒ **no parameter binding** ⇒ injection surface, against `AGENTS.md` ("raw SQL via f-strings" forbidden). Indexable, but irrelevant if it cannot be bound safely. |

### 1.2 Index usage — and a correction to `docs/09-database/indexes.md`

`docs/09-database/indexes.md:87-89` records that the GIN index `idx_aggregated_data_dims_gin` is
**not reached by the application**, and asserts that *"`@>` does not reach a GIN index of this shape"* and
*"unreachable from either predicate form."*

Measured on PG 18.6 with `enable_seqscan = off`:

| Predicate | Plan |
|---|---|
| `dims @> '{"category":"North"}'::jsonb` | `Bitmap Index Scan on idx_agg_dims_gin` — **reachable** |
| `dims @@ '$.category ? (@ == "North")'` | `Bitmap Index Scan on idx_agg_dims_gin` — reachable |
| `dims->>'category' = ANY('{North}')` | `Seq Scan` — **not reachable** |
| `jsonb_exists_any(...)` | `Result / One-Time Filter` over `Seq Scan` — not reachable |

The index's default opclass is `jsonb_ops` (gin), confirmed via `pg_opclass`; `jsonb_ops` supports `@>`
and `@@` but never `->>`. **So the doc's factual claim about `@>` is wrong**; the claim about `->>` is
right. `pg_stat_user_indexes.idx_scan = 0` is a true measurement of *today* because nothing emits `@>`.

**Consequence for this block:** the recommended form is `->>`, which **keeps the GIN index unreached**,
so `docs/09-database/indexes.md` needs **no change for the shipped predicate** — but the
"unreachable from either predicate form" sentence is a false claim about the schema and should be
corrected to name `->>` only. That doc edit belongs to `CHTB-8` (documentation), not here.

`idx_aggregated_data_dashboard_graph` (`indexes.md:63-74`) remains the index that actually serves the
read; the list branch does not change that.

### 1.3 The mechanism that keeps `range`'s rejection off the dashboard-scope 422

**The decisive finding, executed:**

```python
class M(BaseModel):
    filters: dict[str, str | int | float | bool | list[str]]
    model_config = ConfigDict(extra="forbid")

M(filters={'cat': ['A','B']})    # OK    -> multiselect
M(filters={'cat': [0, 100]})     # FAIL  -> string_type  (a range, refused — but incoherently)
M(filters={'cat': ['0','100']})  # OK    -> accepted as a multiselect  *** THE HOLE ***
M(filters={'cat': []})           # OK
```

`['0','100']` is **simultaneously** a legitimate `multiselect` over two string dimension values **and** a
`range` whose bounds came back as strings — the exact `loadPersistedFilters` scenario
(`DashboardView.tsx:56-73`, which casts `sessionStorage` into `FilterState` with only an
"is an object, is not an array" check). **They are indistinguishable on the wire.** Therefore:

> **The value union CANNOT be the discriminator.** No amount of union typing can tell a
> `multiselect` over `{'0','100'}` from a degraded `range`. Any mechanism that tries will silently
> match nothing on a membership test — reintroducing `CHT-009` in the very block that closes it.

The discriminator must be the filter's **declared type**, which the system already stores and which is
*not* on the wire in the value. Two declarations exist; only one is reachable and typed:

| Source | Typed? | Reachable? | Evidence |
|---|---|---|---|
| `filters.type` (PG `filter_type` enum) | yes (`Enum(FilterType, …)`, `db/models/filters.py:46-53`) | **NO** | `api/routes/filters.py` is a 6-line placeholder: *"global filter CRUD endpoints … have been removed"*. `FilterService._validate_filter_type` (`services/filter_service.py:260-280`) is **unreachable over HTTP**. The only writer is `db/seeders/test_media_dash.py`. `GET /dashboards/{id}/filters` returns only `{"filter_id": …}` — it does not expose `type`. |
| `dashboards.config.filters[].type` | **no** — `DashboardConfig.filters: list[dict[str, Any]] \| None` (`models/dashboard.py:16`) | **YES** — `POST`/`PUT /dashboards` | Executed: `DashboardConfig(graph_types=['bar'], filters=[{'field':'price','type':'range','min':0,'max':100}])` is **accepted today, silently**. This is the hole `D-16-2` names. |

**Recommended mechanism — two layers, in this order:**

**Primary (per-filter, cannot blank a dashboard): refuse `range` at the dashboard *write* boundary.**
Type the `DashboardConfig.filters` element. Verified:

```python
class DashboardFilterConfig(BaseModel):
    field: str
    type: Literal["select", "multiselect", "date"]   # 'range' refused, message enumerates the rest
```

Probe: `'select'` / `'multiselect'` / `'date'` OK · `'range'` →
`Input should be 'select', 'multiselect' or 'date'` · **`FilterType.SELECT` (a `StrEnum` member) still
validates**, so `tests/test_pydantic_models.py:156-181` stays green unmodified. A stored `range` is then
impossible to create, and the refusal is a **422 on a dashboard save naming one field** — the dashboard
still renders its last saved config, so the blast radius is a form, not a page.

**Primary (client, the only remaining live producer): drop an unevaluable restored value before it
reaches `/data/aggregated`.** Once the `range` control is deleted, the *only* way a range-shaped value
enters `FilterState` is a `sessionStorage` entry written by an older build (`DashboardView.tsx:56-73`).
`loadPersistedFilters` runs as a `useState` **initializer** (`DashboardView.tsx:79-81`) — *before*
`useDashboard` resolves (`:84-88`) — so it **cannot** consult the declared types. It can, however, decide
the one case that is decidable from the value alone:

- a **`number[]`** entry ⇒ a slider value ⇒ **drop the key, name the reason.** Unambiguous.
- a **`string[]`** entry ⇒ **ambiguous** ⇒ leave it. This is exactly the union's ambiguity restated.

**Backstop (server, read boundary): refuse by name in the service, so nothing is silently ignored.**
`DataService.validate_filter_values(dashboard_id, filters, db)` — reads `dashboard.config["filters"]`,
and for each submitted key: a declared `"range"` ⇒ refuse; a list value on a declared non-`multiselect`
⇒ refuse; **key not declared ⇒ permissive** (required: `_setup_dashboard_with_aggregates`
(`tests/test_aggregate_row_caps.py:32`) builds dashboards with `config={"graph_types": ["bar"]}` and **no
filters key**, so an undeclared-keyed `multiselect` must keep working).

`DataService.__init__` **already takes `dashboard_repo`** (`services/data_service.py:75`) and
`get_data_service` **already injects it** (`api/deps.py:452`) ⇒ **zero new DI wiring**. The route calls
the service method once before the per-graph loop (`api/routes/data.py:247-255`); the route keeps no logic.

**Assessment of the plan's prescription — it is still right, and the reason has changed.**

The plan says: *"the rejection must be raised at filter-change time, not as a 422 on the combined data
request."* That holds **a fortiori** now. The 422 no longer comes from a hand-rolled `json.loads` guard;
it comes from a typed model. But a typed model makes the situation *worse* for server-side placement,
not better: **any** failure on `/data/aggregated` is dashboard-scope (`DashboardView.tsx:203-207` renders
one `Alert` covering the whole charts `Grid` at `:193-239`), and `/data/aggregated` is the **only** surface
that sees the combined `filters` dict. So a per-filter reason **cannot** be reported per-filter from there,
no matter how the model is typed. The prescription therefore **forces the primary guard to the client and
the write boundary**, and demotes the server to a loud backstop. The plan does not say this, and an
implementor who puts the refusal in `DataService` alone will produce a named, correct, and still
dashboard-scope 422 — technically satisfying the text and functionally failing the intent.

### 1.4 The `range` control has a second, independent defect

`DashboardView.tsx:115-119` builds `filterDetails[].config` forwarding only `field`, `source`, `multi`.
It does **not** forward `min`/`max`. So `DashboardFilters.tsx:181-191`'s `config.min || 0` /
`config.max || 100` **always** fell back to `0`/`100` for a dashboard-config-driven range — the slider
could never bound to anything real, independently of the `str()` comparison. This is additional evidence
that `D-16-2`'s removal is correct, and it means the `a3db812` accessibility work is being deleted from
a control that never worked. Not this block's defect to fix.

---

## 2. Rejected alternatives

| # | Path | Reason for rejection |
|---|---|---|
| **B** | Keep the boundary scalar-only; client issues one request per selected value and unions in the browser. | N requests per filter change inside a 300 ms debounce (`DashboardFilters.tsx:57-60`). Union semantics move into the presentation tier, where nothing tests them. `DashboardFilters` already `switch`es on type, so the fan-out has no home. **Zero server change** is a real benefit but not worth N round trips + client-side set logic. Rejected. |
| **C** | Refuse `multiselect` too, with a clear message. | **Rejected by the ruling's own text** — `D-16-2`: *"The `multiselect` half of `CHTB-6` is INDEPENDENTLY UNBLOCKED and MUST NOT WAIT — it is the type dashboards actually use."* Recorded so the rejection is on the record, not assumed. Consistency with `range`'s fate is not an argument: `range` is refused because **no definition exists** (both `(a)` lexicographic and `(b)` measure-targeted were rejected in `D-16-2`); `multiselect` needs **no definition** — "value is one of these" is the ordinary meaning of a multi-select and the repository already reads the column it needs. |
| **D** | Widen the union, branch in the repository, and let `range` be caught by the union alone. | **Unsafe — the mechanism question's answer.** `['0','100']` is accepted as a `multiselect` (executed). A membership test over `dims` then matches nothing: the silent-empty-chart defect `CHT-009` names, reintroduced by the fix. |
| **E** | Remove `FilterType.RANGE` from `enums.py` (the plan's instruction). | **Rejected with evidence — see §4.3.** `filter_type` is a **live PG ENUM**; `test_enum_db_consistency.py::ENUM_MAPPINGS` does **not** include it (verified: only `user_role`, `dashboard_permission_level`, `processing_status`), so removing the Python member leaves the DB label with **no test asserting the drift**, and forces `enums.ts` + `enums.test.ts:161,166` edits for a member **no code path can create**. |
| **F** | A new per-filter validation endpoint (`POST /dashboards/{id}/filters/validate`). | Would close the residual, but `D-16-2`'s rejection is naturally at the **write** boundary (§1.3 primary), which needs no new route. A network round trip inside the debounce to validate a three-valued union is not justified. |
| **G** | Server-side guard only, in `DataService`, as the primary mechanism. | Correct message, **still dashboard-scope**. §1.3. Demoted to backstop. |
| **H** | Do nothing; treat the 422 as acceptable pending a product decision. | Not available: `D-16-2` is adjudicated and released, and the `multiselect` half was never gated. The 422 is a live defect blanking every chart on a dashboard. |

---

## 3. Answers to questions 1–8, each with a symbol-level evidence line

### Q1 — The right JSONB membership expression

**`(dims ->> :key) IN (:v1, :v2, …)`, i.e. `.astext.in_(values)`.** Reason: same `->>` operator as the
existing scalar branch, so the compatibility floor is structural rather than asserted; one predicate
regardless of element count, so `PRF-5`'s plan-time bound (`models/data.py:483-491`) is unaffected;
empty list is an explicit always-false predicate, not a syntax error.

- Compile, SQLAlchemy 2.0.50: `(aggregated_data.dims ->> %(dims_1)s) IN (%(param_1_1)s, %(param_1_2)s)` ·
  `params: {'dims_1': 'category', 'param_1_1': 'North', 'param_1_2': 'South'}` — **each element is its own
  bound parameter**; asyncpg needs no array codec and there is no interpolation surface.
- Empty list: `(aggregated_data.dims ->> %(dims_1)s) IN (NULL) AND (1 != 1)`.
- PG 18.6: `{North, South}` → rows 1,2 · wrong key → 0 · prefix key `cat` vs `category` → 0 (exact).
- asyncpg parameter binding: the key is bound as `->>`'s text argument (`:229`'s `dims[key]`), never
  interpolated. A key containing a quote is a value, not SQL.
- **Scalar branch untouched:** the list branch is one extra `conditions.append` inside the existing
  `for key, value in filters.items()` loop (`:227-230`); the scalar expression is not edited.
- **@> is out** (AND-probe 0 rows; `jsonb_build_object` array form is a PG18 error) · **`jsonb_exists_any`
  is out** (wrong direction, 0 rows) · **`@@` is out** (needs string interpolation).
- Index: `->>` is not GIN-reachable (measured) ⇒ `docs/09-database/indexes.md:87-89`'s "retained by
  decision" state is unchanged by this block; its claim that `@>` is also unreachable is **false** and
  should be corrected under `CHTB-8`.

**Recommendation: keep the empty-list case as "no condition" (skip the key), not "match nothing."**
Rationale: an empty multi-select shows no chips ⇒ the user has expressed no constraint. Returning zero
rows would blank every chart with no visible cause — the defect class this block exists to close. A test
must pin this, because the alternative looks defensible in code review.

### Q2 — The scalar branch's correctness: **a separate, already-closed concern. Do not change it in this block.**

The audit's flagged trap (`astext` on a jsonb number vs a stringified Python repr) is **re-derived and
partly refuted**. Measured on PG 18.6 with natively-typed rows:

| Stored `dims` value | `->>` renders | Python `str()` | Match? |
|---|---|---|---|
| `"North"` | `North` | `'North'` | ✅ |
| `2023` (jsonb number) | `2023` | `'2023'` | ✅ |
| `2024.0` | `2024.0` | `'2024.0'` | ✅ |
| `12345678901234567890` (beyond int8) | identical | identical | ✅ |
| `1e-07` (jsonb number) | **`0.0000001`** | `'1e-07'` | ❌ |
| `true` (jsonb bool) | **`true`** | `'True'` | ❌ |

So the plan's trap (b) — *"a `date` filter sending a string against a stored number never matches"* — is
**false for integers** (verified: `->>'year' = '2023'` matched both the jsonb `2023` and the jsonb `"2023"`
row, count 2) and **true only for jsonb floats and jsonb booleans**.

**Both true cases are unreachable**, because the only production writer canonicalises every dim scalar
to a string:

- `data/storage/manager.py::_canonicalize_dim_scalar` (`:74-96`, ruling `D-05-E`): `None → ""`;
  `isoformat` → ISO string; `int`/`float`/`bool` → `str(value)`; else `str(value)`. Its own docstring
  (`:82-85`) names this exact hazard: *"A `Float64` value holding `1e-07` becomes the string `'1e-07'`,
  which `->>` returns unchanged — native storage would render it through `numeric` as `0.0000001` and
  make it unreadable by the read path's `astext == str(value)` comparison."*
- Applied at **all three** write surfaces — `_bulk_insert`, `_bulk_upsert`, `upsert_aggregate`
  (`manager.py:15-17`, `:99-113`).
- The repository's own `AggregatedDataRepository.bulk_insert` (`aggregated_data_repo.py:93`) does **not**
  canonicalise, but it has **no production caller** — grep for `\bbulk_insert\b` across `*.py` returns
  exactly two hits: `interfaces/repository_interfaces.py:193` (the abstract declaration) and
  `aggregated_data_repo.py:93` (the implementation). Only `StorageManager.save_aggregates` writes rows in
  production (`workers/data_worker.py:1257`).
- The behaviour is already pinned: `tests/test_storage_manager.py::test_int_filter_value_reads_the_stored_row`
  (`:472-496`) writes `{"region": 5}`, reads it back through `get_by_graph_id(filters={"region": 5})`, and
  asserts one row with `dims["region"] == "5"`. Its section header (`:470`) calls this *"the frontend
  range-slider case"* — the scalar branch's correctness for a numeric dimension is a **tested contract
  today**, not an open gap. Also pinned: the float case (`:566-572`) and the boolean case (`:514-539`).

**Conclusion: the scalar branch is correct for every row the application can store. It needs no change,
and it is not a separate open defect — it is a separate, already-tested guarantee.** The plan's trap (b)
should be struck from the block text. The residual risk (a row written by some future un-canonicalised
writer) is a property of the **write** path, not of this read predicate; if it ever matters it belongs
with `D-05-E`, not `CHTB-6`.

### Q3 — Where the shape branch belongs: **CONFIRM, with a refinement the plan misses.**

**Confirm** the plan's claim. Evidence:

- `aggregated_data_repo.py::_graph_filter_conditions` (`:199-231`) is already a `@staticmethod` shared by
  **three** callers — `get_by_graph_id:259`, `get_by_graph_id_limited:308`, `count_by_graph_id:357`. The
  repo's own docstring (`:207-209`) states why both the row select and its `COUNT(*)` companion must share
  predicates: *"so the reported total can never disagree with the rows the same request is allowed to
  return."* A shape branch there covers all three at once, keeping `total_rows` and `data` in agreement —
  which is the contract `tests/test_openapi.py::TestAggregatedDataResponseCarriesTruncationContract` pins.
- Placing it in the route would mean the route builds SQLAlchemy expressions and hands them to
  `IDataService`, whose interface declares `filters: dict[str, Any] | None`
  (`services/data_service.py:203`, `:259`), not predicates. That is a strictly worse layering and breaks
  the `IDataService` contract.
- The route additionally loops the service **once per graph** (`api/routes/data.py:247-255`), so a
  route-level branch would either be recomputed N times or hoisted into a form that bypasses the
  repository entirely.

**Refinement — the plan conflates two different questions.** Two decisions, two homes:

| Decision | Home | Symbol |
|---|---|---|
| **How** to evaluate an admissible value (scalar compare vs membership) | **repository** | `AggregatedDataRepository._graph_filter_conditions` |
| **Whether** a value is admissible at all | **service / boundary model** | `DataService.validate_filter_values`, `DashboardConfig`'s filter element |

A repository that *raises* `AppException` for a bad value would be a business rule in the data layer. The
original plan's trap text only covers the first question; the second is where `range` actually has to be
refused, and it is **not** in the repository.

### Q4 — The `range` removal's true surface

**Full census (every occurrence of the `"range"` filter type):**

| Site | Nature | Action |
|---|---|---|
| `src/mkobi/models/enums.py::FilterType.RANGE` (`:39`) | Python `StrEnum` member; **DB-mapped** | **KEEP** — see §4.3 |
| `src/mkobi/models/types.py::FilterConfigDict.type` (`:224`) | `# Input type ("select", "multiselect", "range", "date")` — a **comment**; the field is `str \| None`, not a `Literal` | Update the comment; drop `"range"`, state the server refuses it by name |
| `frontend/src/shared/types/enums.ts::FilterType.RANGE` (`:35`) | Hand-written mirror, `as const` | **KEEP** — §4.3 |
| `frontend/src/shared/types/__tests__/enums.test.ts:161,166` | `expect(FilterType.RANGE).toBe('range')` **and** `expect(Object.keys(FilterType)).toHaveLength(4)` | **KEEP** unmodified — §4.3 |
| `frontend/.../DashboardFilters.tsx::case 'range'` (`:179-198`) | `<Slider>`, incl. `a3db812`'s `aria-labelledby={labelId}` (`:194`) and `labelId` (`:184`) | **DELETE.** `default: return null` (`:213-214`) then covers `range`. `Slider` import (`:9`) becomes unused → remove. `Typography` (`:7`) stays (used `:91`). The accessibility work dies with a control that never worked (§1.4). |
| `src/mkobi/db/models/filters.py:46-53` | `Enum(FilterType, name="filter_type", values_callable=…)` | Untouched |
| `alembic/versions/000000000000_initial_migration.py:35` | `ENUM("select", "multiselect", "range", "date", name="filter_type")` | Untouched — the label stays; see §4.3 |
| `src/mkobi/db/seeders/test_media_dash.py` | **No `range`.** Only `multiselect` (`:99`, `:105`, `:128`, `:143`) | Untouched |
| `tests/test_dev_seeders.py:222,365` | Asserts `FilterType.MULTISELECT` / `f["type"] == "multiselect"` | **Green unmodified** |
| `tests/` fixtures — `test_filter_persistence.py`, `test_filter_values_consistency.py` | `FilterType.SELECT` only | **Green unmodified** |
| `tests/test_repositories.py:414` | `FilterType.DATE` (update) | **Green unmodified** |
| `tests/test_pydantic_models.py:158,179` | `FilterType.SELECT` | **Green unmodified** (verified against a `Literal`) |
| `docs/02-dashboards/dashboards-api.md:660` | Filter Types table row `range` → "Range slider" | `CHTB-8` |
| `docs/09-database/enums.md:36,140,148,399` | Enum value list, Python snippet, UI table, summary table | `CHTB-8` |
| `docs/11-guides/create-dashboard.md:220` | `range` row | `CHTB-8` |
| `docs/11-guides/extend-filters.md:41,81,103` | Table row, Python snippet, TS mirror snippet | `CHTB-8` |
| `docs/11-guides/extend-graphs-filters.md:49,179,201` | **Byte-duplicate of `extend-filters.md`** | `CHTB-8` (and note the duplication) |
| Admin UI filter-type selector | **Does not exist.** `FilterType` in `*.tsx` appears only in `DashboardView.tsx:17,114` | Nothing to change |
| `tests/test_enum_db_consistency.py` | See §4.3 | **Green unmodified** |

**No `range` filter type in `docs/indexes.md`, `docs/SPEC.md`, `docs/07-frontend/**`, or
`docs/08-security/**`** (searched).

### Q4.3 — Is `FilterType` DB-mapped? **Yes. Removing the member implies a migration. VERIFIED — and I recommend against the removal.**

- **DB-mapped: yes.** `alembic/versions/000000000000_initial_migration.py:35` creates
  `ENUM("select", "multiselect", "range", "date", name="filter_type")`, and
  `db/models/filters.py:46-53` binds `Filter.type` to `Enum(FilterType, name="filter_type", …)`.
- **`test_enum_db_consistency.py::ENUM_MAPPINGS` (`:248-252`) contains only `user_role`,
  `dashboard_permission_level`, `processing_status`.** `filter_type` is **absent** — read directly, not
  assumed. `docs/09-database/enums.md:36` lists `filter_type` as one of six DB ENUM types, and
  `.ai/plans/_code-context/14-schema-migrations-code-context.md:390` records
  `filter_type | select, multiselect, range, date`.

**Consequence — the plan's instruction to "Remove `FilterType.RANGE`" is wrong in both directions:**

1. **It would not be caught.** No test asserts `filter_type`'s Python↔DB agreement, so removing the
   Python member leaves the DB label `'range'` in place and drifts silently.
2. **It would force collateral edits for an inert member.** `api/routes/filters.py` is a placeholder —
   **there is no HTTP write path for `filters.type` at all** — so after the block nothing can create a
   `range` row. Removing the member still forces `enums.ts` + `enums.test.ts:161,166` (both the value
   assertion *and* the exact-length assertion) for a value no code can produce.
3. **It makes a future `ALTER TYPE filter_type DROP VALUE` untested**, which is the wrong direction.

**Recommendation: keep `FilterType.RANGE` as an inert label; achieve `D-16-2` behaviourally** — remove
the control, refuse stored `range` at the write boundary and by name at the read boundary. Record
**enum-label removal + stored-row migration together as `C14-17`**, the phase-14 participation the plan
already names. `D-16-2` requires the *control* removed and stored filters *rejected with a message
naming the reason*; it does not require the enum label deleted, and deleting it here buys nothing while
creating untested drift. **The residual `FilterType.RANGE` must be recorded explicitly as "kept, inert,
retirement deferred to `C14-17`" in the block's log** so it does not read as an oversight.

### Q5 — The rejection message

**Reuse `ErrorCode.VALIDATION_ERROR`. Do not mint a new code.** Verified:

- `models/enums.py:268` — `VALIDATION_ERROR = "VALIDATION_ERROR"`.
- `utils/exceptions.py:56` — already mapped to `HTTP_422_UNPROCESSABLE_CONTENT` in
  `_ERROR_CODE_STATUS_MAP`; `:210` — `"Validation error"` in `get_error_title`.
- It is **already what `/data/aggregated` returns** for a bad `filters` payload
  (`api/routes/data.py:150-153`), and already asserted by
  `tests/test_filter_payload_bounds.py::test_twenty_one_keys_rejected` (`:79-80` asserts
  `body["code"] == "VALIDATION_ERROR"` and `body["status"] == 422`).
- **It reaches the client with no client change.** `frontend/src/shared/api/errorHandler.ts:57-75`: the
  RFC 7807 branch takes `message` from `data.detail` and `details` from `data.details`; `:62-68` handles
  the `VALIDATION_ERROR` case. `ErrorResponse` already carries `details`
  (`utils/exceptions.py:247-254`).
- A new code would need four registrations — `ErrorCode` (`enums.py`), `_ERROR_CODE_STATUS_MAP`,
  `get_error_title` (`exceptions.py`), and the client mirror `frontend/src/shared/types/enums.ts::ErrorCode`
  (31 members) plus its test — to carry a message `VALIDATION_ERROR` already carries. **Reject.**

**Exact recommended shape:**

```python
raise AppException(
    code=ErrorCode.VALIDATION_ERROR,
    detail=(
        f"Filter '{key}' cannot be applied: {reason}. "
        f"Declared filter type is '{declared_type}', which has no "
        "supported evaluation in aggregated-data filters."
    ),
    details={
        "filter": key,
        "declared_type": declared_type,
        "reason": reason,
    },
)
```

`reason` is one of two literals:
- `"the 'range' filter type has been removed and no range definition exists"`
- `"a list value is only valid for a filter declared 'multiselect'"`

`detail` names the filter **and** the reason — satisfying `D-16-2` — and `details` gives a client the
machine-readable pair without parsing prose.

**Where raised, so it does not blank the dashboard:**
- **Primary:** the `DashboardConfig` filter-element validator at `POST`/`PUT /dashboards`. A 422 on a
  dashboard *save*, naming one field; the dashboard keeps rendering its last saved config.
- **Backstop:** `DataService.validate_filter_values`, called once from `api/routes/data.py` before the
  per-graph loop. Dashboard-scope if it fires — which is why it is the backstop, not the primary.
- **Named fallback if a distinct machine code is wanted:** `ErrorCode.INVALID_FIELD_VALUE` (`enums.py:272`,
  already mapped to 422 at `exceptions.py:59`, titled "Invalid field value" at `:211`). Zero new
  registration. It loses the `filters` grouping that `errorHandler.ts:62` keys on, so `VALIDATION_ERROR`
  is the pick.

### Q6 — Regression surface

Baseline verified this session: `test_filter_payload_bounds.py` + `test_data_endpoint.py` = **11 passed**.

| Module / class | n | Asserts today | Verdict |
|---|---|---|---|
| `tests/test_filter_payload_bounds.py::TestFilterPayloadBounds` | 7 | 20 keys → 200; 21 keys → 422 + `VALIDATION_ERROR`; over-long key → 422; over-long value → 422; over-sized payload → 422; malformed JSON → 422; valid payload returns exactly the pre-change rows (`returned_rows == 1`, `total_rows == 1`, `data[0]["category"] == "Filter-cat-0"`, `:180-182`) | **All 7 green unmodified.** The over-long-value case (`:99-114`) sends `{"region": "v"*257}` — a **scalar**, so the per-list-element bound change does not touch it. **Note the gap the audit is right about: there is no list-valued test anywhere in the file, and a list is a 422 today, untested.** |
| `tests/test_filter_persistence.py::TestFilterStatePersistence` | 3 | Filter-**values** endpoint returns the distinct set after upload; filter values survive navigation to another dashboard; values cleared on overwrite | **Green unmodified — and zero bearing.** These assert `DashboardFilterValuesRepository.get_filter_values` / `dashboard_filter_values`, never `get_aggregated_data(filters=…)`. They do **not** test filter *state* despite the module docstring. Phase 12's `AZ-4` pin is **not** a filter-payload pin. |
| `tests/test_filter_values_consistency.py::TestFilterValuesConsistency` | 2 | Filter values rebuilt after OVERWRITE; accumulated after APPEND | **Green unmodified, zero bearing** — same reason. |
| `tests/test_data_service.py::TestDataServiceIntegration` | 11 | Includes `test_get_aggregated_data_with_filters` (`:314-337`): sends `{"year": 2023, "category": "Electronics"}` to the **unbounded** `get_aggregated_data` and asserts `result == []` | **Green unmodified — and provably non-discriminating.** The graph has **no stored rows**, so the assertion holds whether the scalar branch works, a list branch exists, or the filters are ignored entirely. It has **no bearing** on this work, exactly as the brief states. |
| `tests/test_services_integration.py::TestDataServiceIntegration` | 4 | `test_get_processing_status_missing_task`, `test_get_aggregated_data_empty`, `test_get_available_metrics_empty`, `test_get_available_dimensions_empty` (`:864-895`) | **Green unmodified, zero bearing.** None passes `filters`. |
| `tests/test_data_endpoint.py::TestAggregatedDataEndpointContract` | 4 | 200 without `graph_id`; 200 with `graph_id`; graph metadata keys; 403 without access | **Green unmodified, zero bearing.** The module **never sends a `filters` param** (read in full, 193 lines). |
| `tests/test_openapi.py` | 8 across 6 classes | `ErrorResponse` shape (3); `PUT` settings forbid unknown keys (1); `ProcessingStatusResponse.filename` (1); `AccessGrant.permission` is an enum ref (1); `TestAggregatedDataResponseCarriesTruncationContract` (3); `TestGraphDataResponseDeclaresServedRowKeys` (1); document-URL gating (2) | **All green unmodified.** Every assertion names **response** fields. **No test pins the `filters` query schema** ⇒ the widening is a published-schema change with **zero** coverage. `test_openapi.py` is named in the plan as the tripwire; this is the gap it is currently blind to. |

**Genuinely must change: none.** **Genuinely must be added: the whole discriminating set (§5), plus one
class in `tests/test_openapi.py` for the widened `filters` schema.**

### Q7 — Compatibility and rollout

- **Additive in the published schema: yes.** Executed — the widened union's JSON Schema is
  `{"additionalProperties": {"anyOf": [{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"type":"string"},"type":"array"}]}}`. Every previously-accepted value is still accepted with the same JSON Schema type; `anyOf` gains a branch. **No `required` list changes; no property is renamed or removed; no existing client is invalidated.** (Contrast `GraphConfigDict`'s narrowing, which `D-16-1` had to gate.)
- **`extra="forbid"` compatibility: yes — and the recorded trap does not apply here.** Executed against a
  model with `extra="forbid"`:
  - `{'filters': {'cat': ['A','B']}}` → **OK** — a list value is fully compatible.
  - `{'filters': {'cat': 'A'}, 'extra_key': 1}` → `extra_forbidden` at `('extra_key',)` — the forbid still works on the model's own fields.
  - `{'filters': {'cat': ['A'], 'inner': 1}}` → **OK** — correct: `inner` is a *filter name*.
  - `{'filters': {'cat': {'nested': 1}}}` → five union errors, correctly refused.
  
  The R1 implementor's finding (the board post of `716c755`) is the accurate statement of the trap: Pydantic
  propagates a parent `extra` policy into **nested models** (`GraphConfigDict`), **not** into `dict` values.
  `filters` is `dict[str, <union>]` — a dict value type — so `extra` does not reach it. The trap is real
  and it is **inapplicable to this field**. The constraint it *does* impose: **do not** introduce a nested
  `BaseModel` for a filter value in this block, or `extra="forbid"` would start rejecting a list member
  object the client may legitimately send.
- **A client that sends a list today:** it gets **422 `VALIDATION_ERROR`** on `/data/aggregated`, and
  `DashboardView.tsx:203-207` blanks **every chart on the dashboard**. After the change: **200**, and the
  list is evaluated as a membership test. **This is the fix, and it is the one visible behaviour change on
  the happy path.** Anyone whose dashboard was showing zero charts because of this 422 now sees charts.
- **A client that stops sending lists:** unaffected — `[]` → no condition (recommended) or always-false
  (the alternative). Pin the chosen semantics with a test.
- **`select` / `date` (scalar):** byte-identical path; the scalar expression is not edited and
  `test_filter_payload_bounds.py::test_valid_payload_returns_the_same_rows` already pins one case. Add a
  second, explicit byte-identity assertion — the plan's own compatibility floor, currently unasserted.
- **Rollout order matters.** The `range` removal must land **before or with** the client restore-drop, and
  the `DashboardConfig` write-boundary refusal should land **before** the client restore-drop. Reason: the
  restore-drop is the primary guard; if it lands first, a `range`-declared dashboard is refused on every
  save but a stale `sessionStorage` value can still blank the page until the next save. Landing
  write-boundary → restore-drop → server backstop in one commit is fine; splitting the backstop into a
  later commit is not, because the backstop is what turns the residual from silent into loud.
- **No migration is required by this block.** `filter_type` keeps its labels; `aggregated_data` is
  untouched; `dashboards.config` JSONB is untouched (the refusal is at the write boundary, so no stored row
  changes shape).

### Q8 — Is there a reason not to do this block? **No. Do it.**

Neither horn applies. `multiselect` should be **fixed**, not refused: it needs no product definition, the
repository already reads the column the membership test needs, and `D-16-2` released it explicitly. The
422 is **not** acceptable to wait on: it blanks a dashboard today, and no decision is pending that would
change it. The one genuine finding that changes the block's shape is §1.3 — the plain union widening is
**unsafe on its own** — and it is resolved by a mechanism (the declared type as the discriminator) that is
cheaper than the alternatives, not by deferring.

---

## 4. Exact shapes recommended, and where each change lives

### 4.1 `src/mkobi/models/data.py::AggregatedFiltersRequest` — transport admissibility only

```python
filters: dict[str, str | int | float | bool | list[str]]

@field_validator("filters")
@classmethod
def validate_filter_bounds(
    cls, v: dict[str, str | int | float | bool | list[str]]
) -> dict[str, str | int | float | bool | list[str]]:
```

- `model_config = ConfigDict(extra="forbid", …)` — **unchanged**; verified compatible with a list value.
- `parsed` property — **unchanged** (`dict(self.filters)`).
- **One required change inside `validate_filter_bounds`:** today's per-value check is
  `len(str(value))` (`:546-548`). For a list that measures `str(["A","B"])` — the **repr** — so a list
  would evade `MAX_FILTER_VALUE_LENGTH` element-wise. Change to: for a list value, check
  `len(element)` for each element (and the key-length check is unaffected). The whole-payload check
  (`:549-554`, `json.dumps`) already covers aggregate size and needs no change.
- **No new count bound.** `MAX_FILTER_KEYS = 20` (`:496`) bounds *keys*. A new
  `MAX_FILTER_VALUES_PER_KEY` is **not** required: the list compiles to **one** predicate regardless of
  element count, so `PRF-5`'s plan-time rationale (`:483-491`, planning 0.889 ms → 37.971 ms from K=0 to
  K=1000) does not apply; and `MAX_FILTER_PAYLOAD_BYTES = 4096` (`:499`) already caps total element count
  at roughly 4096 single-byte characters, while the scan is served by
  `idx_aggregated_data_dashboard_graph`. **Inventing a constant here would be overengineering**; state the
  reason in the docstring instead.
- Docstring must state the two-layer rule: **this model decides *shape*; `DataService.validate_filter_values`
  decides *admissibility*.** A `list[str]` here means "a list was supplied", not "a multiselect was meant".

### 4.2 `src/mkobi/models/dashboard.py` — add a typed filter element (**the `D-16-2` primary**)

New, in `models/dashboard.py` (or `models/types.py` alongside `FilterConfigDict`):

```python
class DashboardFilterConfig(BaseModel):
    """One declared dashboard filter.

    ``type`` is the closed vocabulary of filter controls the aggregate read can
    evaluate. ``"range"`` is deliberately absent: ``D-16-2`` removed it until a
    range definition exists, and this model is where a stored ``range`` is
    refused **by name** -- on a dashboard save, naming one field, which cannot
    blank an already-rendered dashboard.
    """
    field: str
    type: Literal["select", "multiselect", "date"]
    source: str | None = None
    multi: bool | None = None
    options: list[str | int] | None = None
    default: str | int | list[str | int] | None = None
```

and `DashboardConfig.filters: list[DashboardFilterConfig] | None = None`.

**Executed against the proposed element — the `options` risk is closed:**

| Input | Result |
|---|---|
| `{"field":"year","type": FilterType.SELECT}` | **OK** — the `test_pydantic_models.py:158,179` shape, green unmodified |
| `{"field":"year","type":"select","source":"data"}` | **OK** — the shape `DashboardView.tsx:113-118` reads |
| `{"field":"category","type":"multiselect","multi":True}` | **OK** |
| `{"field":"year","type":"select","options":["2023","2024"]}` | **OK** |
| `{"field":"year","type":"select","default":2023}` | **OK** |
| `{"field":"price","type":"range","min":0,"max":100}` | **FAIL** — `Input should be 'select', 'multiselect' or 'date'`, `input_value='range'` |
| `{"field":"r","type":"select","unknown_extra":1}` | **OK** — unknown keys are **ignored** (Pydantic's default `extra="ignore"`), so the element refuses only the declared vocabulary and does **not** turn every legacy dashboard filter shape into a 422 |

A repository-wide search for stored dashboard-config `filters` entries found **only**
`{"field": "year", "type": "select"}` (`models/dashboard.py:28,77,120,153`) and
`{"field": "year", "type": FilterType.SELECT}` (`test_pydantic_models.py:158,179`) — **no test or seed
ever passes `options`, `min`/`max`, or `multi` inside a dashboard `config.filters` entry.** The client
mirror's `options: Array<{label,value}>` (`api.types.ts:117-118`) is therefore a **declared-but-unexercised**
shape; `list[str | int]` is safe today, and if that ever changes, widen `options` to `list[Any]` rather
than tightening. **Confidence: HIGH.**

**Two facts the implementer must handle, both newly found:**

1. `models/dashboard.py:29`'s own `json_schema_extra` example advertises
   `{"field": "category", "type": "multi_select"}` — and `"multi_select"` is **rejected** by the proposed
   element (executed above). It is not a `FilterType` value, and the client sends `"multiselect"`
   (`DashboardFilters.tsx:151` switches on it). **The example must be fixed to `"multiselect"` in this
   block**, because leaving it would publish a value the boundary refuses. This is a live example in the
   OpenAPI document, so it is a `CHTB-8` line item with a **block dependency**, not a `CHTB-8`-only edit.
2. Because the element ignores unknown keys rather than forbidding them, a **deny-list** variant
   (`type: str` + a validator that raises only when `type == "range"`) is available if a
   compatibility-first maintainer prefers it: it still names the reason, and it cannot reject a legacy
   vocabulary the project has not inventoried. **The allow-list is recommended** because its message
   enumerates the supported set — which is exactly what `D-16-2`'s *"naming the reason"* asks for — and
   because the legacy vocabulary is now inventoried: four example/test shapes, all accepted.

### 4.3 `src/mkobi/db/repositories/aggregated_data_repo.py::_graph_filter_conditions` — the membership expression only

Inside the existing loop (`:227-230`), scalar branch byte-identical:

```python
if isinstance(value, list):
    if not value:
        continue          # empty multi-select == no constraint (see Q1); PIN WITH A TEST
    conditions.append(
        aggregated_data_model.AggregatedData.dims[key].astext.in_(value)
    )
else:
    conditions.append(
        aggregated_data_model.AggregatedData.dims[key].astext == str(value)
    )
```

- The scalar line must stay **textually unchanged** so the diff proves the compatibility floor.
- Docstring addition: record the measured reason for `->>` (same operator as the scalar branch ⇒ a `select`
  and a `multiselect` over one dimension cannot disagree) and record that the GIN index remains unreached
  by this form (§1.2).
- **No repository-side refusal.** A repository raising `AppException` is a business rule in the data layer
  (§Q3).

### 4.4 `src/mkobi/services/data_service.py` — admissibility, by declared name (the backstop)

New method on `DataService`, called **once** from `api/routes/data.py` before the per-graph loop
(`:247-255`):

```python
async def validate_filter_values(
    self, dashboard_id: UUID, filters: dict[str, Any] | None, db: AsyncSession
) -> None:
```

- Reads `dashboard.config["filters"]` via the **already-injected** `dashboard_repo`
  (`data_service.py:75`; `deps.py:452`) — **zero new DI**.
- Rule per submitted key: a declared `"range"` ⇒ refuse; a list value on a declared non-`multiselect`
  ⇒ refuse; **key not declared ⇒ permissive** (required by `_setup_dashboard_with_aggregates`,
  which builds dashboards with no `filters` key).
- Raises `AppException(code=ErrorCode.VALIDATION_ERROR, detail=…, details={…})` per §Q5.
- `IDataService` (`interfaces/service_interfaces.py`) must gain the signature.

### 4.5 `frontend/src/features/dashboards/ui/DashboardFilters.tsx`

- **Delete `case 'range'`** (`:179-198`), including `labelId` (`:184`) and `aria-labelledby` (`:194`).
  `default: return null` (`:213-214`) then covers a stored `type: "range"` — nothing renders, nothing
  sends a value.
- Remove the now-unused `Slider` import (`:9`). Keep `Typography` (`:7`) — used at `:91`.
- Optionally render an inline `Alert severity="warning"` in the `default` branch naming the reason, so a
  dashboard that still declares a `range` filter **says so** instead of showing nothing. Recommended:
  `D-16-2`'s *"do not ship a control that either does nothing"* cuts both ways — silence is the same
  defect wearing a different hat. Low cost, and it is the visible half of the message the ruling asks for.

### 4.6 `frontend/src/features/dashboards/ui/DashboardView.tsx::loadPersistedFilters` — the last live producer

Replace the bare `return parsed as FilterState` (`:68`) with a per-entry filter:

- **`number[]`** ⇒ slider value ⇒ **drop the key** and record the reason (a range is not evaluable).
  Decidable from the value alone; `loadPersistedFilters` runs before `useDashboard` resolves (`:79-88`),
  so it **must not** attempt the type-aware check.
- **`string[]`** ⇒ ambiguous ⇒ **keep**. The server's by-name backstop is what resolves it.
- The existing guards at `:67` (object, not array) stay.

### 4.7 Files **not** touched by this block

`enums.py::FilterType.RANGE` · `frontend/src/shared/types/enums.ts` · `enums.test.ts` ·
`alembic/…/000000000000_initial_migration.py` · `db/models/filters.py` · `db/seeders/test_media_dash.py` ·
`dashboard_data_repo` reads · `models/types.py::FilterConfigDict.type` (comment only — comment **is**
touched) · all `docs/**` (`CHTB-8`).

---

## 5. Tests required — each stated so it **discriminates**

Fixture: `_setup_dashboard_with_aggregates` (`tests/test_aggregate_row_caps.py:32`) — already imported by
`test_filter_payload_bounds.py:20`; stores `dims={"category": f"{name}-cat-{i}"}` for `i in range(rows)`
and creates the dashboard with **no `filters` config key** — exactly what the permissive-undeclared rule
needs. `.\Makefile.ps1 test-select -k <name> -v`.

**Backend — `tests/test_filter_payload_bounds.py` (the module the plan names for the missing list case)**

1. `test_multiselect_returns_the_union_of_the_scalar_results` —
   rows=5; `{"category": ["Filter-cat-1", "Filter-cat-3"]}` ⇒ `200`, `returned_rows == 2`,
   `total_rows == 2`, and `sorted(r["category"] for r in data) == ["Filter-cat-1","Filter-cat-3"]`.
   **Set equality, not a count.** *Discriminates: today → 422 (`string_type`).* Also cross-checks the two
   scalar filters in the same test so "union" is proven, not asserted.
2. `test_single_element_multiselect_matches_that_element` — `{"category": ["Filter-cat-2"]}` ⇒ 1 row,
   `data[0]["category"] == "Filter-cat-2"`. *Today → 422.*
3. `test_empty_multiselect_is_not_a_constraint` — `{"category": []}` ⇒ `returned_rows == 5` (all rows).
   *Discriminates the chosen empty-list semantics: `in_([])` gives `IN (NULL) AND (1 != 1)` ⇒ 0 rows.
   Without this test the two readings are indistinguishable in review.*
4. `test_multiselect_does_not_match_an_unlisted_value` — `{"category": ["Filter-cat-0","Nope"]}` ⇒ 1 row.
   *Proves the predicate is a membership test, not an "any non-empty list returns rows" stub.*
5. `test_scalar_filter_result_is_unchanged` — the compatibility floor, asserted: `{"category":
   "Filter-cat-4"}` ⇒ `returned_rows == 1` and `total_rows == 1` **and** the full `graphs[0]` data point
   equals the pre-change value. *Discriminates: passes on both, which is the point — it is the floor. State
   it as a floor, not as a fix.*
6. `test_list_value_element_respects_the_value_length_bound` — `{"category": ["v" * 257]}` ⇒ **422**.
   *Discriminates the `validate_filter_bounds` change: today → 422 with a *different* cause (union), after a
   naive widening → **200**, because `len(str(["v"*257])) = 259 > 256` accidentally passes today but a
   shorter-element list would not. Assert on the message, not just the status, so it pins the bound and not
   the union.*

**Backend — new `tests/test_openapi.py::TestAggregatedFiltersRequestPublishesListValues`** (the gap §Q6
identifies)

7. `test_filters_query_schema_publishes_a_string_array_branch` — read
   `components.schemas.AggregatedFiltersRequest.properties.filters.additionalProperties.anyOf`, assert a
   `{"type": "array", "items": {"type": "string"}}` branch **and** that the `string`/`integer`/`number`/
   `boolean` branches survive. *Discriminates: today → no array branch. Also pins "additive", which is the
   compatibility claim.*

**Backend — the `D-16-2` refusals** (new class; put the write-boundary tests in
`tests/test_dashboards.py`, the read-backstop test in `test_filter_payload_bounds.py`)

8. `test_stored_range_filter_is_refused_by_name` — `POST /dashboards` with
   `config={"graph_types":["bar"],"filters":[{"field":"price","type":"range"}]}` ⇒ **422**, and the body
   names `range` and enumerates the allowed types. *Discriminates: today → 201 (verified by executing
   `DashboardConfig` with a `range` filter).*
9. `test_stored_multiselect_filter_is_accepted` — same request with `"type":"multiselect"` ⇒ **201**.
   *Discriminates an over-tight `Literal`.*
10. `test_read_backstop_refuses_a_range_declared_filter_by_name` — a dashboard whose stored config declares
    `{"field":"price","type":"range"}` (written directly through the repository to simulate a pre-block row),
    then `GET /data/aggregated` with `{"price": [0,100]}` ⇒ **422**, `code == "VALIDATION_ERROR"`, and
    `details["filter"] == "price"`, `details["declared_type"] == "range"`.
    *Discriminates: today → 422 from the union with **no** `details`; after §4.1 alone → **200 with zero
    rows**, the `CHT-009` silent-empty defect. This is the test that proves §1.3's mechanism.*
11. `test_read_backstop_permits_a_list_on_a_declared_multiselect` — same shape with `"type":"multiselect"`
    ⇒ **200** with rows. *Discriminates a backstop that refuses too much.*
12. `test_read_backstop_permits_an_undeclared_filter_key` — the standard fixture (no `filters` config) with
    `{"category": ["Filter-cat-0","Filter-cat-1"]}` ⇒ **200**, 2 rows. *Discriminates a backstop that
    requires every key to be declared — which would break every existing fixture.*

**Backend — the removal**

13. `test_write_side_filter_type_still_rejects_an_unknown_type` — `FilterService._validate_filter_type("range")`
    now raises with a message that **does not** list `range`. *Discriminates `§4.3` "keep the enum": the
    Python member stays, so this test must be written against the **HTTP** surface or explicitly skipped —
    **`_validate_filter_type` is unreachable over HTTP** (`api/routes/filters.py` is a placeholder). State
    this in the block log rather than writing a test that cannot be reached.*

**Frontend — `frontend/src/features/dashboards/__tests__/`**
Run: `npm --prefix frontend exec -- vitest run --root frontend <path>`

14. `test_range_filter_renders_no_control` — a dashboard whose `config.filters` declares
    `{field:'price', type:'range'}` renders **no** slider (`queryByRole('slider')` is null) and produces **no**
    `/data/aggregated` request carrying `price`. *Discriminates: today → a `<Slider>` renders and a request
    carries `price: [0,100]`.* Note `filter-persistence.test.tsx:15-33` already mocks `PlotlyChart`,
    `LineChart`, `TableChart` and `UploadModal` — reuse that harness; it **mocks `DashboardFilters` away**,
    so this test must go in a new file that does not.
15. `test_restored_numeric_array_filter_is_dropped_before_any_request` — pre-seed
    `sessionStorage["dashboard-filters-<id>"] = {"price": [0, 100]}`, mount `DashboardView`, assert no
    `/data/aggregated` request carries `price`. *Discriminates §4.6: today → the array is cast straight
    through (`DashboardView.tsx:68`) and is sent.*
16. `test_restored_string_array_filter_is_preserved` — `{"category": ["A","B"]}` survives the restore.
    *Discriminates a restore-drop that is too aggressive and would break the fix this block ships.*
17. `test_restored_scalar_filter_is_unchanged` — `{"region": "North"}` survives, byte-identical to
    `filter-persistence.test.tsx:171-193`'s existing assertion. **Keep that file's 5 tests green
    unmodified** (they mock `DashboardFilters` and use scalars only — they cannot break).

**Must stay green unmodified:** the 7 in `TestFilterPayloadBounds`, the 3 in `TestFilterStatePersistence`,
the 2 in `TestFilterValuesConsistency`, all 11 + all 4 of the two `TestDataServiceIntegration` classes,
all 4 in `TestAggregatedDataEndpointContract`, all of `test_openapi.py`, all 5 in
`filter-persistence.test.tsx`, `tests/test_storage_manager.py::test_int_filter_value_reads_the_stored_row`
(the Q2 scalar-branch pin), `tests/test_pydantic_models.py:156-181`, `tests/test_dev_seeders.py`,
`tests/test_enum_db_consistency.py`.

**Must change:** **nothing existing.** Every one of the 17 tests is an addition.

---

## 6. Risks

**Implementation — LOW (was MEDIUM; closed by execution, see §4.2's table).**
- The **empty-list semantics** decision (`skip` vs always-false) is a product-adjacent call with no
  existing precedent; it is pinned by test 3 so it cannot drift silently.
- `DashboardConfig`'s element tightening (§4.2) touches **every** dashboard create/update path. The
  `options` shape mismatch between the client mirror (`Array<{label,value}>`, `api.types.ts:117-118`) and
  the server's `list[str | int]` (`models/types.py:225`) was flagged as an over-tightening risk; it is
  now **closed by execution** — all seven probed shapes behave as intended, unknown keys are ignored,
  `FilterType.SELECT` still validates, and a repository-wide search found **no** stored
  `config.filters` entry using `options`/`min`/`max`/`multi`. Residual: the fix to
  `models/dashboard.py:29`'s `"multi_select"` example is a **block dependency**, not a `CHTB-8`-only edit,
  because the OpenAPI document would otherwise publish a value the new boundary refuses. LOW.
- `test_filter_payload_bounds.py::validate_filter_bounds`'s `len(str(value))` change is easy to get
  subtly wrong for the whole-payload check's interaction; test 6 exists for that.
- `pyproject`/ruff line length: the type annotation
  `dict[str, str | int | float | bool | list[str]]` appears three times in `models/data.py`
  (`:514`, `:531`, `:532`). Expect a formatter/annotation-length nuisance. LOW.

**Regression — LOW.** Measured: no existing test asserts a 422 or a zero-row result for a list value, and
`test_data_service.py::test_get_aggregated_data_with_filters` is provably non-discriminating (no stored
rows). The two `TestDataServiceIntegration` classes the plan names as "will see a new 422 path" **will not
be affected at all** — neither passes `filters`. The one genuinely unguarded area is
**`tests/test_openapi.py`'s blindness to the `filters` query schema**, which is a coverage gap, not a
regression risk.

**Compatibility — MEDIUM.**
- Widening is additive in the published schema (verified), but a client that sends `[str, str]` today gets
  422 and will get **200 with N rows** after — a visible behaviour change on the dashboard-scope 422 path.
  Release-note it: *dashboards that were blank because a multi-select 422'd now render.*
- `str`-list ambiguity (§1.3) is **not** fully eliminable at the boundary. The mitigation is the by-name
  backstop; the residual is a **non-browser** client sending `[str, str]` for a `range`-declared filter,
  which the backstop catches. There is **no** residual silent case for any input the application itself
  can produce. State this bound explicitly rather than claiming the hole is closed.
- `a3db812`'s `aria-labelledby` is deleted. It is an accessibility regression *in name only* — the control
  it labels never worked (§1.4) and `D-16-2` is not this block's to re-litigate. Record the deletion
  explicitly so an accessibility reviewer does not read it as an accident.

**Rollout — LOW.** One commit is coherent (write-boundary refusal → client restore-drop → repository
membership → client control removal), because the three guards are independent and each is a strict
improvement. If split: the **client restore-drop must not land before the `DashboardConfig` refusal**, and
the **server backstop must not be deferred past the union widening** — that window is exactly the
silent-empty-chart window. No migration, no backfill, no feature flag: `range` is already
non-functional, so there is no working behaviour to roll back to.

---

## 7. What the original plan got wrong about this block

1. **"A `multiselect` filter silently returns zero rows"** — **wrong mechanism.** `a34b56b` made a list a
   **422 at the request boundary** (verified: `string_type`). The audit already corrected this; the plan
   did not. The blast radius is the **whole dashboard**, not one chart.

2. **"The shape branch belongs in the repository, not the route"** — **right conclusion, incomplete
   reason, and it hides the actual problem.** The repository is where *evaluation* belongs — but the plan
   never separates *evaluation* (repository) from *admissibility* (service/boundary), which is precisely
   where `range` must be refused. An implementor who reads only this sentence puts a shape branch in the
   repository and then discovers there is nowhere correct to put the refusal.

3. **Trap (b), "`str(value)` is also wrong for scalars whose JSONB form is a number … a `date` filter
   sending a string against a stored number never matches"** — **false for integers, and unreachable for
   the rest.** Measured: `->>` on jsonb `2023` is `'2023'`, identical to `str(2023)`; the only true cases
   are jsonb **floats** (`1e-07` → `'0.0000001'`) and jsonb **bools** (`true` → `'true'`), and
   `StorageManager._canonicalize_dim_scalar` (`manager.py:74-96`, `D-05-E`) converts both to strings at
   **all three** write surfaces. The repository's own `bulk_insert` bypasses canonicalisation but has
   **no production caller**. The behaviour is already pinned by
   `test_storage_manager.py::test_int_filter_value_reads_the_stored_row`. **Out of scope — and the plan's
   version of it would have produced a spurious change to a working, tested scalar branch.**

4. **"Remove `FilterType.RANGE`"** and its supporting claim that "`FilterType` is not DB-mapped … so no
   migration is implied"** — **half wrong, and the half that is wrong is the load-bearing one.**
   `test_enum_db_consistency.py::ENUM_MAPPINGS` genuinely does not include `filter_type` (verified), but
   `filter_type` **is** a live PG ENUM (`alembic/…/000000000000_initial_migration.py:35`;
   `db/models/filters.py:46-53`). Removing the Python member would leave the DB label with **no test
   asserting the drift**, and force `enums.ts` + `enums.test.ts:161,166` edits for a member **no code path
   can create** (`api/routes/filters.py` is an empty placeholder — there is no HTTP write path for
   `filters.type` at all). Keeping the label inert and refusing `range` behaviourally satisfies `D-16-2`
   at zero cost.

5. **"Both `TestDataServiceIntegration` classes … will see a new 422 path — the report names them as
   breaking."** — **wrong.** `test_data_service.py::TestDataServiceIntegration`'s only filter test
   (`:314-337`) queries a graph with **no stored rows** and asserts `result == []`, so it passes whether
   the branch exists or not; `test_services_integration.py::TestDataServiceIntegration`'s four tests pass
   no `filters` at all. Both classes are green unmodified **and have no bearing on this work**.

6. **"Both suites … pin the filter stack beneath" / "`TestFilterStatePersistence` is phase 12's `AZ-4`
   pin"** — **mischaracterised.** `test_filter_persistence.py` and `test_filter_values_consistency.py`
   assert the filter-**values** repository (`dashboard_filter_values`), never
   `get_aggregated_data(filters=…)`. `TestFilterStatePersistence` has 3 tests about distinct dimension
   values, not about filter state on the wire. The plan would have had an implementor strengthen tests
   that cannot discriminate anything.

7. **"The rejection must be raised at filter-change time, not as a 422 on the combined data request"** —
   **right, but for a reason the plan never states, and the plan never says how.** `/data/aggregated` is
   the **only** surface that sees the combined `filters` dict and `DashboardView.tsx:203-207` renders one
   `Alert` over every chart. So a per-filter reason **cannot** be reported per-filter from there, no
   matter how the 422 is produced — which is now more true than when the plan was written, because the 422
   comes from a typed model. The prescription forces the primary guard to the **client** and the
   **dashboard write boundary**, and demotes the server to a loud backstop. An implementor who puts the
   refusal in `DataService` alone produces a named, correct, and still dashboard-scope 422.

8. **"A `multiselect` filter with two values returns the union of the two single-value results"** as a
   *verification* — correct and keep it, but the plan does not mention the two ways the implementation
   can silently pass it: an **empty list** rendering as always-false, and a **`str`-list accepted as a
   `multiselect` when it was a degraded `range`** (executed: `['0','100']` is accepted). Both need their
   own test (3 and 10).

9. **`docs/09-database/indexes.md:87-89`'s "`@>` does not reach a GIN index of this shape … unreachable from
   either predicate form"** — **factually wrong, and the block inherits it.** Measured with
   `enable_seqscan = off` on PG 18.6: `dims @> …` and `dims @@ …` both produce
   `Bitmap Index Scan on idx_agg_dims_gin`; only `->>` and `jsonb_exists_any` are unreachable. The doc's
   `pg_stat_user_indexes.idx_scan = 0` is a true measurement of *today* only because nothing emits `@>`.
   `CHTB-8` should correct the sentence to name `->>`.

10. **"The `filters` model is not mentioned anywhere in the plan"** (audit finding 8) ⇒ the plan would have
    had an implementor shape-branch the repository into **unreachable code**, since a list can never reach
    it. §4.1 exists because of that finding.

11. **Unmentioned defect found during this research, in `DashboardView.tsx:115-119`:**
    `filterDetails[].config` forwards only `field`, `source`, `multi` — **not `min`/`max`** — so
    `DashboardFilters.tsx:181-191`'s `config.min || 0` / `config.max || 100` always fell back to `0`/`100`.
    The `range` slider could never bound to anything real, independently of the `str()` comparison. Strong
    additional support for `D-16-2`, and it means `a3db812`'s accessibility work was invested in a control
    that could not function.

12. **Unmentioned defect found during this research, at `models/dashboard.py:29`:** the model's own
    `json_schema_extra` example publishes `{"field": "category", "type": "multi_select"}`. `"multi_select"`
    is **not** a `FilterType` value (`enums.py:37-41` has `select`/`multiselect`/`range`/`date`), and the
    client sends `"multiselect"` (`DashboardFilters.tsx:151`). It is published in the live OpenAPI
    document, so it is a **`CHTB-8` item with a block dependency**: once `DashboardConfig.filters` is typed,
    a client that copied the example gets a 422 on a dashboard save (executed). The plan proposes a
    typed filter vocabulary and never notices that the repo advertises a value outside it.

13. **"Both suites … will see a new 422 path" as the reason the two `TestDataServiceIntegration` classes
    need attention** — already listed as item 5 above, restated here only because it is the plan's single
    most load-bearing factual error about the regression surface: an implementor budgeting time for those
    two suites would be budgeting for nothing, while the suite that actually **needs** a new test
    (`tests/test_openapi.py`, blind to the `filters` query schema) is named only as a tripwire to be
    discovered broken.

---

## 8. Handoff

- **Recommended path:** (A) — widen `AggregatedFiltersRequest.filters` to admit `list[str]`;
  `AggregatedDataRepository._graph_filter_conditions` branches on shape with
  `dims[key].astext.in_(values)` for a list and the **byte-identical** `== str(value)` for a scalar;
  empty list ⇒ no condition.
- **Mechanism:** the value union **cannot** discriminate `multiselect` from a degraded `range` (executed:
  `['0','100']` is accepted). The discriminator is the filter's **declared type**. Primary refusals:
  the `DashboardConfig` filter-element `Literal` (write boundary, per-field, cannot blank a dashboard)
  and a client restore-drop of `number[]` values (the only live producer once the control is gone).
  Backstop: `DataService.validate_filter_values` by declared name, using the **already-injected**
  `dashboard_repo` — loud, dashboard-scope, should never fire in the application path.
- **`range`:** control removed (`DashboardFilters.tsx:179-198`); `FilterType.RANGE` **kept, inert**;
  enum-label + stored-row migration filed as `C14-17`; stored `range` refused by name at the write
  boundary; `ErrorCode.VALIDATION_ERROR` reused with the reason in `detail` and
  `{filter, declared_type, reason}` in `details`.
- **Existing tests that must change: none.** 17 new tests, listed in §5, all discriminating.
- **Not done here (recorded, not deferred silently):** `docs/**` corrections → `CHTB-8`;
  `docs/09-database/indexes.md`'s `@>` claim → `CHTB-8`; enum-label removal + stored-row migration →
  `C14-17`; `loadPersistedFilters` becoming type-aware once `dashboard` is available (it is a
  `useState` initializer) → **not filed as a participation, but the ordering constraint is recorded
  here and belongs in the block log.**
