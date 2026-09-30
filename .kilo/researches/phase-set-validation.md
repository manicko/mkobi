# Phase-Set Validation — `.kilo/commands/audit/phases/`

Validation of the rewritten 16-file phase set against `.kilo/researches/rewrite-rulings.md`
(R1–R11) and the standard in `.kilo/researches/llm-audit-task-spec-design.md` §2–§7
(skeleton, B1–B14, D1–D11, C1–C9, RC1–RC7, AP1–AP19). No file was modified.

---

## 1. Verdict

**Accepted with fixes.** The mechanical skeleton is essentially clean: every file has exactly
three frontmatter keys, `name` matching the filename stem minus `audit-`, exactly four `##`
sections in the mandated order, no legacy section name, exactly one italic span and exactly one
trailing `Evidence:` line per block, and 157 block titles of which **zero** are duplicated and
**zero** carry a banned word, a path token, a framework noun, or a count about the system. The
prefix namespace matches the R4 table exactly, `AUT-` and `MED-` appear nowhere, the four
archived files are referenced by no active phase, and `.ai/audit/templates/audit-findings.md`
exists. What is not clean is the *ownership layer*. The two angles R6 and R7 were issued to
collapse are still instantiated three to seven times each, and the invariant that replaces the
old 8–13-block rule — no evidence fragment shared between two blocks — fails on five clusters,
one of them with a verbatim-shared fragment. Four of sixteen files collapse their four-band
severity taxonomy into a single bullet, three files issue 23 in-block deferrals naming no phase
number, and six seams are declared but never claimed by the phase they name. These are not
cosmetic: each one produces either a duplicated finding or a silently unexamined zone. All
defects below are fixable inside the existing files without adding a file to the set.

---

## 2. Conformance matrix

`blocks` = `###` headings; `ev` = `Evidence:` lines (verified last line of every block);
`fm` = frontmatter keys (must be 3). Total 157 blocks.

| File | blocks | ev | fm | name = stem − `audit-` | 4 sections, right order | findings path | prefix | four bands | Result |
|---|---|---|---|---|---|---|---|---|---|
| `01-audit-process-architecture.md` | 9 | 9 | 3 | ok | ok | `01-process-architecture` ok | `TOPO-` ok | ok | **pass** |
| `02-audit-configuration-secrets.md` | 10 | 10 | 3 | ok | ok | ok | `CFG-` ok | ok | **pass** (see D1, D5, D13, M4) |
| `03-audit-db-concurrency.md` | 10 | 10 | 3 | ok | ok | ok | `TXN-` ok | ok | **fail** (D5) |
| `04-audit-authentication.md` | 9 | 9 | 3 | ok | ok | ok | `AUTH-` ok | ok | **fail** (D2, D3, D4) |
| `05-audit-data-pipeline.md` | 10 | 10 | 3 | ok | ok | ok | `DP-` ok | ok | **fail** (D2, D5, M2, M4, M13) |
| `06-audit-file-artifacts.md` | 8 | 8 | 3 | ok | ok | ok | `ART-` ok | ok | **fail** (D3, M4, M5, M6, M14) |
| `07-audit-external-boundary.md` | 9 | 9 | 3 | ok | ok | ok | `EXT-` ok | ok | **fail** (D2, D10, M4, M5, M6) |
| `08-audit-code-quality.md` | 10 | 10 | 3 | ok | ok | ok | `QLT-` ok | ok | **fail** (D1, M9, M13) |
| `09-audit-test-coverage.md` | 9 | 9 | 3 | ok | ok | ok | `TST-` ok | **collapsed to 1 bullet** | **fail** (D1 ok as binder, M1, M2) |
| `10-audit-production-ops.md` | 13 | 13 | 3 | ok | ok | ok | `OPS-` ok | **collapsed to 1 bullet** | **fail** (M1, M2, D2) |
| `11-audit-performance.md` | 9 | 9 | 3 | ok | ok | ok | `PERF-` ok | **collapsed to 1 bullet** | **fail** (D1, D11, M1) |
| `12-audit-authorization.md` | 11 | 11 | 3 | ok | ok | ok | `AUTZ-` ok | **collapsed to 1 bullet** | **fail** (D2, D4, D10, M1) |
| `13-audit-client-tier.md` | 11 | 11 | 3 | ok | ok | ok | `FE-` ok | ok | **fail** (M2, M3, M7) |
| `14-audit-schema-migrations.md` | 9 | 9 | 3 | ok | ok | ok | `MIG-` ok | ok | **fail** (M2, M3, D11, M5) |
| `15-audit-security-baseline.md` | 9 | 9 | 3 | ok | ok | ok | `SEC-` ok | ok | **fail** (D1, D2, D3, M2, M3, M7) |
| `99-audit-validate.md` | 11 | 11 | 3 | ok | ok | `99-validation/…-validated-findings.md` (R1 exception) ok | audited phase's own + `VAL-` ok | ok | **pass** (see D13, M10) |

Notes on the matrix: the leading space before `# Phase NN` in 09/10/11/12 (m1) renders as an ATX
heading and does not break parsing. `Scope Boundaries` is bolded in eight files and plain in
eight (m2). The `Audit Blocks` preamble in 05–07, 13–15 omits the "nothing here gates a finding
on this phase's own checks" clause that 01–04, 08–12 and 99 carry — a variance, not a breach.

---

## 3. Defects

### BLOCKER

**D1 — The vacuous-control angle is re-instantiated in three phases it was ruled out of, and one
evidence fragment is shared verbatim with its canonical owner.**

R6: *"Vacuous-control angle — defined **once**, in `99`. Phases 09 and 10 reference it with their
own binding in one clause each."* 09 b7 (`Bind the shared vacuous-control angle here, in the
gate-and-suite form`) and 10 b3 (`bind the shared vacuous-control angle here in its
deployed-surface form`) conform. The following do not:

- `02-audit-configuration-secrets.md:103` — `### 9. A guard that runs, reports clean, and examines
  nothing`
  `:105` — `*Enumerate every validation and gate over configuration, then ask three separate
  questions of each and answer all three: does it exist, what scope does it declares, and what did
  it actually examine.` — a full, unbound restatement of 99 b2's definition. There is no binding
  clause and no deferral to 99 anywhere in the file.
- `15-audit-security-baseline.md:119` — `### 9. Controls in This Zone That Exist, Load, and Decide
  Nothing`
  `:121` — `*Apply the vacuous-control angle as defined in the adjudication phase (99) to this
  zone: for each control, ask whether it exists, what scope it declares, what it actually
  examined…` — R6 authorised 09 and 10 only; 15 is a fourth binder.
  `:126` — `Evidence: … one control green over zero items; …` — **verbatim identical** to
  `99-audit-validate.md:67` — `Evidence: … one control green over zero items.` This is the only
  literal evidence-fragment collision in the set and it is between an angle's owner and a binder.
- `11-audit-performance.md:46` — `### 2. The performance discipline that exists, and the one that
  does not`
  `:50-51` — `A name registered in the test harness is not a performance control, and reading one
  as the other is how an empty discipline passes for a covered one. Where no such control exists,
  record the absence with a reached or un-reached verdict rather than omitting the question.` —
  R6 ruled explicitly: *"Phase 11 (performance) does not carry it: this repository has no latency,
  query-shape or load gate, so the instantiation would be vacuous by construction."*
- `08-audit-code-quality.md:136` b9 (`whether a check present in configuration is actually
  executed or merely declared`) and `:147` b10 (`Do not assume a gate exists until one is found
  running`) are further, unbounded instances of the same question.

This is C6's original defect — five near-verbatim instantiations — surviving at four to seven
copies. **Fix:** keep 02 b9 but reduce it to one clause binding 99 (`the vacuous-control angle is
99's; what a configuration gate examines is this block's`); delete 15 b9 entirely and let 99 b2
apply the angle to 15's controls, or keep 15 b9 as a one-clause binding with evidence
substituted from 15's own zone; delete or re-scope 11 b2's control-existence half; give 08 b9/b10
one binding clause. Change 15 b9's evidence fragment to something 15-only.

**D2 — Rate limiting is claimed by four blocks across three phases, with three separate evidence
fragments for the same reproduction, and 04 and 15 each claim it as owned.**

- `04-audit-authentication.md:15` (Purpose): `…abuse limiting on the surfaces that hold no
  credential yet.` — owned here.
- `15-audit-security-baseline.md:20-21` (Purpose): `which inbound surfaces are attempt-bounded and
  what a counter's own failure means` — owned here.
- `04-audit-authentication.md:111` (b9): `Whether a surface is rate-bounded at all is 15's.` — so
  04 defers coverage to 15.
- `15-audit-security-baseline.md:78-80` (b4): `Bounding the login surfaces specifically is another
  phase's… whether a surface is bounded at all is this block's.` — so 15 defers the surfaces back.
  This is a deferral in both directions on one seam (C4 breach), and neither "the login surfaces"
  nor "the surfaces that hold no credential yet" is a partition anyone can execute against.
- `07-audit-external-boundary.md:58` b3 `### 3. A guard built to bound abuse: what it does when
  its own store is unavailable` — evidence `:65`: `one outage probe whose outcome differed from
  the guard's intended direction.`
- `15:82` evidence: `one bounded path reproduced with its store unavailable, and the outcome.`
- `04:112` evidence: `…the limiter's behaviour with its store unavailable; …`
  Three blocks, one observation.
- `07:67` b4 `### 4. The aggregate ingress budget: what bounds arrival, on which caller identity…`
  and `12-audit-authorization.md:100-101` b7 (`where an abuse limit is derived from a peer address
  that a fronting tier makes identical for every caller, and what that limit then actually bounds`)
  make it four blocks. 12 b7 carries no deferral naming 07 or 15 — B12 breach and a strayed
  angle.

**Fix:** 15 b4 keeps "does a surface have a bound at all"; 04 b9 keeps "what identity the bound is
keyed on and whether it can be chosen by the caller"; 07 b3 keeps only the store-unavailable
failure mode of the counter and defers the keying to 04; delete 12 b7's abuse-limit sentence and
replace it with `the limit's keying and its derived identity are 04's`. Give each of the three a
distinct evidence fragment.

**D3 — The one-time secret and its retrieval handle are claimed by four blocks in four phases, with
three evidence fragments for one observation.**

- `04:23` b1 `### 1. The one-time credential handshake end to end: issuance, where the cleartext
  rests, retrieval, and what the retrieval handle is exposed to`; body `:28-29` `Then map every
  surface the retrieval handle and the cleartext reach: the response that returns them, the request
  path that carries the handle, every access and proxy record along that path, browser history,
  error text, caches`; evidence `:32` `…one handle observed in a request record or log line.`
- `06:73` b5 `### 5. A one-time secret held outside the database: how it is created, how it is
  collected once, and what a failure at each step leaves behind`; body `:76` `whether the stored
  form is recoverable from the store that holds it`; evidence `:81` `…one failure in which the
  caller is told a secret exists and it does not.`
- `15:57` b2 `### 2. Short-Lived Credentials Handed to Another Person: the Store, the Lifetime, the
  Retrieval`; evidence `:64` `…one retrieval handle observed travelling outside the response that
  issued it.`
- `07:99-100` b7 `Include every endpoint whose input is a secret or a handle for one, and establish
  where such a handle is carried and who can read it there.`; evidence `:103` `…one secret handle
  and where it travels; …`

None of the four defers the handle-exposure half to any other phase. 06 b5's Purpose-level
boundary names only 10, 04 and 15 for adjacent questions. "Whether the stored form is recoverable"
appears in 04 b1, 06 b5 and 15 b2 with no owner. **Fix:** name one owner for the handle's travel
(04 — it owns the handshake end to end), one for recoverability at rest (15), one for the creation
and collection failure residue (06); delete the other statements; substitute 07 b7's evidence
fragment with an endpoint-class verdict.

**D4 — The account-state × surface matrix is claimed twice with no deferral in either direction.**

`04:83` b7 `### 7. Account state the request path does not consult`; body `:85` `*Enumerate every
condition an account record carries, and establish which of them a gate evaluates, on which
surface, and at which point in the request.`; evidence `:90` `Evidence: the account-condition
inventory with, per condition, the surfaces that evaluate it; …`
`12:96` b7 `### 7. Account State: which states are consulted, on which surface, and by which
resolution`; body `:98` `*Establish which account states exist, which are consulted, on which
surfaces, and whether a read surface consults the states a mutating one does.`; evidence `:103`
`Evidence: the state-by-surface coverage matrix, with server-enforced against caller-delegated each;
…`

Both are the same matrix. 04 b7's only deferral is `The per-request gate itself — an absent
payload, an unresolvable identity, a check that raises — is 12's decision`, which does not reach
the matrix. **Fix:** 12 keeps the matrix (it owns the per-request gate); 04 b7 keeps only
"conditions carried inside a credential against conditions read from the stored record" (its own
line `:88-89`) and defers the rest to 12.

**D5 — `03` keeps a residual cross-resource instantiation, and adds a second, contrary to R6's
"exactly one live instance".**

R6: *"Cross-resource side-effect angle — owned by 05. It has exactly one live instance… Phases 01,
03 and 06 defer to 05."* `01:93-94` and `06:26` defer correctly. `03` does not:

`03:117-119` (b10) — `Every effect of this shape belongs to 05 (data-pipeline), which owns the
live instance where a work record and the temporary file it names are written and deleted by
different processes; this block records the boundary, defers the instance, and covers only the
effects this phase's own writes create.` — the sentence grants ownership to 05 and then retains
the category, so the same finding will still be filed. Evidence `:120` keeps `per multi-resource
effect, the resources, the commit order and one observed intermediate state`.
`03:46-47` (b3) — `Establish which domain operations change more than one row, or a row and
something that only means anything beside it, and whether the boundary sits where the invariant
does.` — a second multi-resource instance with no deferral.
`03`'s Purpose never lists the cross-resource deferral to 05 (C3 breach); it lists only
`the ingestion and aggregation pipeline this phase's transaction boundary protects (05)`.

**Fix:** delete `03` b10 outright and add its one-line deferral (`the record-and-file effect
written by different processes is 05's`) to `03` b3; add the cross-resource deferral to `03`'s
Purpose boundary.

---

### MAJOR

**M1 — Four files collapse their four-band severity taxonomy into a single bullet.**
`09:130-131`, `10:174-175`, `11:124-125`, `12:145-146`. Quote (`09:130-131`):
`- **CRITICAL** — the suite's green is affirmatively false today: … . - **HIGH** — a gap that will
be mistaken for coverage and is silent today: …` — three of the four bands are not list items.
The skeleton (§2.2) and the task's criterion A require four effect-class bullets; `99` b3 grades
findings against "the audited phase's own rubric", so a rubric the validator cannot enumerate
block-by-block is a rubric it cannot apply. **Fix:** split each into four `- **BAND** —` bullets
in every one of the four files.

**M2 — `## Report Output` deviates from the six-bullet form in eight files.**
`13:169-174`, `14:141-146`, `15:147-152` use **seven** bullets, splitting the reserved empty-state
string out of the `problems-only` bullet (`- Empty state, exactly: \`No problems found in this
phase.\``). `05:146`, `06:126`, `07:141`, `08:176` reduce the sixth bullet to `- A shipped test
asserting current behaviour is a remediation blocker, not a gate`, dropping the RC5 residual clause
and the RC1 `Violates invariant X` clause that `01:136`, `02:140`, `03:140`, `04:132` carry.
`09:143`, `10:186`, `11:135`, `12:158` append `— cumulative: a new run appends or supersedes, it
does not restart` to the findings-path bullet, duplicating the `Incremental append` bullet. AP14.

**M3 — 23 in-block deferrals name no phase number, so reciprocity cannot be checked.**
`13` has 7 (`b1:55`, `b2:65`, `b3:73`, `b4:82-83`, `b5:91`, `b6:101`, `b8:117-118`, `b10:134`,
`b11:143` — e.g. `The rule that each fixed value has exactly one home… are another phase's`);
`14` has 5 (`b2:57`, `b3:66`, `b6:92`, `b7:101`, `b8:110`, `b9:118` — e.g. `Whether a drift gate
exists, is loaded and would notice is another phase's`); `15` has 11 (`b1:53`, `b2:61`, `b3:70-71`,
`b4:78-79`, `b5:88`, `b6:97`, `b7:106`, `b8:115`). B12 requires the number. `08:121`
(`User-facing text is another phase's`), `10:87` (`How such a component is configured and sized is
another phase's`) and `99:54-55` (`the drift gate that would have caught the drift before the
report was written is another phase's`) each name no number **and** no owner appears in the
respective Purpose boundary — three dangling deferrals.

**M4 — `the blocking-work bridge` is deferred three times to `03`, which never claims it; and the
deferral mechanism is assigned to `01` by two other phases.**
`05:19-20` `transaction, lock and pooler semantics, and the blocking-work bridge (03);`
`07:20` `transaction, lock, pooler semantics and the blocking-work bridge (03);`
`08:23` `transaction, lock and pooler semantics, and the blocking-work bridge (03);`
A search of `03-audit-db-concurrency.md` returns no occurrence of "bridge"; its nearest block,
`03:92` b8 `### 8. Background and one-shot operation safety`, covers invocation, interruption and
repeat-safety — not the mechanism that carries work out of the request path. Meanwhile
`11:96` states `The mechanism carrying work across the loop boundary is 01's` and `01:65` b5
enumerates `every mechanism work can be submitted to`. Two owners, and the zone three phases were
told to skip is nobody's. **Fix:** assign the deferral mechanism to `01` in 05, 07 and 08 and
delete the phrase `and the blocking-work bridge (03)`; add a matching clause to `03`'s boundary.

**M5 — `the file-age and retention thresholds, and the queue-broker configuration` deferred to `02`,
which never mentions any of them.** `05:18-19` `settings values, the file-age and retention
thresholds, and the queue-broker configuration (02);` and `:124` `Settings values and the
queue-broker configuration are 02's`; `06:18-19` `settings values, the file-age and retention
thresholds, and the configuration of the shared transient store (02);`. A search of
`02-audit-configuration-secrets.md` returns no occurrence of "queue", "broker", "retention" or
"file-age". Two zones with three deferrals and no owner. **Fix:** name the owning block in `05`
b10 (`the sweep's clock and bound are this block's; the configured value is 02's`) and either
delete the phrase from 06 or add the claim to `02` b3's inventory.

**M6 — Two more declared-but-unclaimed zones.** `01:15` `the health endpoint's effect on the
result the client sees (11);` — `11` contains no occurrence of "health". `13:33-34`
`credential storage policy, request-rate bounding coverage and failure-response disclosure (15);`
and `13:82-83` `Deployed-build provenance is another phase's, and whether a store reachable by
script running in the page is acceptable for this credential is a further phase's` — `15`'s nine
blocks contain no browser-credential-storage question. **Fix:** assign the health-endpoint client
effect to `11` b9 (per-request materialisation) or delete it from 01; assign browser credential
storage to `15` b1 or to `13` b4 outright and name the number.

**M7 — `01` b6 and `03` b9 both own what the destructive store drop does to live connections.**
`01:83` `The path that drops and recreates the whole store sits here rather than in the pipeline's
zone: its acquisition semantics and its behaviour against live connections are this block's
question.` `03:108-109` `Include the path that drops and recreates the whole store, and establish
what it does to connections other components already hold and to the work in flight on them.`
Neither defers to the other. C4 breach; two auditors, one finding or two.

**M8 — `01` b6 and `08` b10 both derive the non-migration schema-mutation population.**
`01:78-79` `*Enumerate every path that can mutate the schema or the reference data — the
orchestrated one-shot, the in-process path behind a setting, an ad-hoc invocation, automation, and
the test harness — and derive the population rather than accepting the declared set.`
`08:152-153` `Establish separately whether schema or reference data is mutated from a code path
rather than from a migration — a boot-time bootstrap, a development seeder, a test-data seeder, a
repair run — and per path whether it is idempotent if run twice`. `08`'s evidence fragment is
distinct (`an idempotency verdict`) so the invariant holds, but the population derivation is
duplicated with no deferral in either direction. **Fix:** `01` owns the population, `08` owns
idempotency, and each names the other.

**M9 — Transport security has three declared owners; `10` b9 and `12` b11 share one question.**
`12:18-19` `…and the transport-security policy (02), this phase owning only whether the server
re-checks what the browser already enforced…`; `02:15` `…transport security, probes and backup
that consume these values (10);`; `10:16-17` `the fronting tier, transport security and
certificate lifecycle (from 07, 02)`. Then `10:127-128` `Establish where the configuration
declares a transport requirement stricter than the only transport the deployed topology offers,
and what a credential requiring that transport then experiences.` and `12:134-135` `Establish
whether the deployed transport can carry the credential at all when its declared transport
requirement is stricter than what the deployment offers…` are the same question, with neither
deferring to the other.

**M10 — `12`'s Purpose asserts an identical paragraph that does not exist in `02`, which will make
`99` b11 file a false drift finding.** `12:19` `…one paragraph, identical in 02 and 12, the policy
half in 02 and the enforcement half here`. `02`'s Purpose contains no such paragraph, and `02:68-69`
(b5) words the seam differently: `Which origins and cookie attributes are honoured per variant is
the policy half and belongs here; which surfaces a request-forgery check reaches, and whether it
runs on each, is 12's` against `12:136-137` `Which origins and which credential attributes are
honoured, per environment, is 02's; which surfaces carry an ambient credential and whether anything
re-checks it is this phase's.` The reciprocal deferral exists; the identity assertion is false.
**Fix:** delete the clause from `12:19`, or move the paragraph into `02`'s Purpose verbatim.

**M11 — `11` b3, `14` b6 and `15` b6 write an R10 live defect into the prompt as a premise.**
R10: *"They are **not** to be written into the phase files as findings — a phase states the angle,
not the answer."* `11:57-58` `*Establish what a statement does as the caller widens a filter: a
caller-supplied selection parsed into one equality predicate per key, applied to a document-valued
column through a scalar extraction, with no bound on key count, key length or value length.` — the
architecture is asserted, not established. `15:96-97` `Caller-supplied structured content consumed
as a key set against a document-valued column is the pattern to establish` — same defect, same
premise. `14:89-90` `…including predicates over structured document columns and predicates whose
shape the caller supplies` is the durable form and is fine. A prompt that asserts its own
premise will produce the expected finding whether or not the code is there — a false-positive
generator, and the exact failure mode R10 was written to prevent. **Fix:** rewrite `11` b3's
opening as an establish-the-shape question and `15` b6's as "a payload whose content selects an
unconstrained key set is the shape to establish".

**M12 — The collision clause appears in five different wordings, and one variant re-introduces the
assertion family R4 retired.** R4: *"Phrase it as a re-derivation obligation — **never** assert
that a prefix is or is not already present in shipped source."* `05:143`, `06:123`, `07:138`,
`08:173`: `check for a collision before minting an identifier; a shipped test, comment or report may
already carry one from a prior cycle` — reintroduces "in shipped source". `09:145`, `10:188`,
`11:137`, `12:160`: `re-derive before minting: an identifier already issued may resolve to a
different finding`. `13:171`, `14:143`, `15:149`: `re-derive it from the set's current
declarations`. `01-04`: `derive each identifier afresh`. Compounding this,
`99:27-28` says `The namespace ruling is this phase's, and 08, 09, 10 and 11 currently carry such
notes` — but `05`, `06` and `07` carry the same note, so the validator is pointed at four of seven
carriers. **Fix:** one clause, verbatim, in all sixteen files; correct the carrier list in `99`.

**M13 — `14`'s prefix bullet carries rewrite provenance instead of a re-derivation obligation.**
`14:143` `- Finding-ID prefix: \`MIG-\` — this phase takes the shorter database stem released to it
from the concurrency phase; re-derive it from the set's current declarations…`. The first clause
describes the rewrite's history, not the audited system.

**M14 — `06` b7 and `03` b7 both build the mutual-exclusion inventory.**
`06:93-94` `Establish which long-lived processes read, create and remove artefacts… and per
operation whether it is mutually excluded and by what.` `03:84-88` `*Enumerate every mutual-
exclusion mechanism in the system as one inventory and derive it rather than accepting the
mechanisms a caller already knows about.*` `06:62` defers `Locking and repeat-run safety are 03's`
but only inside b3; b7 does not. **Fix:** `06` b7 defers the exclusion verdict to `03` and keeps
only "what a second remover meeting an already-removed artefact produces".

---

### MINOR

- **m1.** `09:6`, `10:6`, `11:6`, `12:6` — a leading space before the H1 (` # Phase 09 — Test
  Coverage`). Parses as an ATX heading; delete the space.
- **m2.** `**Scope Boundaries**` is bolded in 01/02/03/04/13/15/99 and plain in 05/06/07/08/10/11/12/14.
- **m3.** `02`, `03`, `04` have no Purpose-level deliberate-asymmetry sentence (D7/AP19), although
  `02` b5/b6 and `03` b1 compare peers.
- **m4.** `14:23-29`'s `Other phases own` list omits 04, 07, 12, 13 and 99, so five of the set's
  ownerships are invisible from 14.
- **m5.** The R8 transient-store seam is worded `every key` in `01:92`, `04:99`, `10:112` but
  `every entry` in `06:23` and `07:24`. R8 requires identical wording across the three-way split.
- **m6.** `15:80` says `whether a surface is bounded at all`; `04:111` and `10:117` say
  `whether a surface is rate-bounded at all`.
- **m7.** The evidence preamble reads `not a check list` in 01–05, 08–12, 99 and `not a checklist`
  in 06, 07, 13, 14, 15.
- **m8 — set-level, outside the 16 files but caused by one of them.**
  `99:185` declares `.ai/audit/99-validation/{NN}-{phase-name}-validated-findings.md` and
  `audit-multi-phase.md:94` writes the same string, but `audit-multi-phase.md:105` verifies
  `Check that \`.ai/audit/99-validation/{PHASE_NUMBER}-{PHASE_NAME}-validated.md\` exists.` — the
  orchestrator's post-validation gate will always miss, retry once, and escalate. Either the
  orchestrator line or `99:185` must change.

---

## 4. Seam verification

### R6 — vacuous-control angle (owner: 99; authorised binders: 09, 10)
**FAIL.** 09 b7 and 10 b3 are correctly bound in one clause each. 02 b9 is a full unbound
restatement; 15 b9 is an unauthorised fourth binder that also shares `one control green over zero
items` verbatim with 99 b2; 11 b2 carries the form R6 explicitly forbade for 11; 08 b9 and 08 b10
carry two further unbounded instances. Six live instances where the ruling says two. Evidence:
`02:105`, `15:121`, `11:50-51`, `08:141-142`, `08:150-151`, `99:60-62`.

### R6 — cross-resource side-effect angle (owner: 05; defers required from 01, 03, 06)
**PARTIAL FAIL.** 05 owns it: `05:13-14` `One angle is owned here alone: side effects that span a
record and the file it names, written by different processes.` 01 b7 and 06 b7 defer correctly and
number the owner (`01:93-94`, `06:26`). 03 b10 grants ownership to 05 and then retains the
category (`03:117-119`), and 03 b3 adds a second multi-resource instance with no deferral; 03's
Purpose never declares the deferral.

### R7 — declared-contract angle (owner: 08; defer required from 05, 06, 07, 10, 12)
**PASS, with two minor gaps.** 08 b8 owns it and 08's Purpose states ownership explicitly
(`08:14-16`). Deferrals present and numbered: `05:53` (`Whether a declared transition table is
enforced by its writers is 08's angle`), `10:165-166` (`Where the claim is a declaration made in
production source, whether it is executable and whether any path consults it is 08's`), `12:64-65`
(`Where the privilege is declared rather than enforced, whether the declaration is executable and
whether any path consults it is 08's`). Gaps: `07:100-101` asks the same question inside b7 with
only the Purpose-level deferral, no in-block clause (B12); `06:60-61` b3 (`Establish the naming
rule each component that reads the area independently relies on, and whether the rules agree`) is
the same shape with no in-block deferral.

### R8 — shared transient store, three-way split, identical wording
**FAIL on wording; PASS on ownership.** Ownership is correct and reciprocal: `10:26-28` Purpose
paragraph plus `10:118` (`What a revocation marker must be able to express is 04's, whether a
surface is rate-bounded at all and what credential material the store holds is 15's`);
`04:99` (`The composition of every key in the store and each marker's lifetime are 10's; whether a
surface is rate-bounded at all, and what credential material the store holds, are 15's`);
`15:61-62` (`The composition of every key in the shared transient store and each marker's lifetime
is another phase's; the credential material that store holds is this block's`); `15:78-79`;
`11:105-106` defers all four questions away, as R8 requires. Defects: `06:23` and `07:24` use
`every entry` where the split says `every key`; `15:80` drops `rate-` from `rate-bounded at all`;
`15`'s Purpose does not restate the three-way split at all, so the seam exists only in `15` b2/b4
and only without phase numbers (M3).

### Reciprocal-deferral check (all 16 × all 16)
**6 non-reciprocal seams**, all listed above:

| Defers to | Defending phase | Claimed zone | Owner |
|---|---|---|---|
| 03 | 05, 07, 08 | `the blocking-work bridge` | **none** (01 b5 and 11 b7 name 01) |
| 02 | 05, 06 | `the file-age and retention thresholds`, `the queue-broker configuration` | **none** |
| 11 | 01 | `the health endpoint's effect on the result the client sees` | **none** |
| 15 | 13 | `credential storage policy` (browser-side) | **none** |
| 02 / 10 | 12, 02, 10, 07 | `transport-security policy` | **three** (12→02, 02→10, 10←07+02) |
| 04 | 08, 07 | `User-facing text` (08 b7), `how such a component is configured and sized` (10 b5), `the drift gate` (99 b1) | **none named in the defending Purpose** |

Everything else resolves reciprocally: 01↔10 (health contract), 01↔11 (ceiling), 01↔03 (entry vs
unit of work), 02↔03 (connection semantics), 02↔12 (origin/cookie policy vs server re-check),
02↔15 (credential material), 03↔11 (pool sizing), 03↔14 (chain linearity), 03↔05 (write
boundary), 04↔12 (negotiated, stated in both), 04↔15 (hashing vs handshake), 05↔08 (fixed values
and boundary models), 05↔15 (rate coverage), 06↔10 (store composition), 06↔12 (who may collect),
07↔15 (bound values), 08↔09 (sanctioned suppressions vs gate scope), 09↔10 (gate existence, each
side named), 11↔14 (index inventory vs query cost), 12↔13 (client route guard), 13↔14/11 (cache
key), 14↔08 (drift gate). No deferral points at a number outside 01–15 or 99.

---

## 5. Coverage map

| Zone | Owner | Notes |
|---|---|---|
| Process topology, entry, lifecycle, boot ordering | 01 | clean |
| Configuration resolution, secrets, guards, defaults | 02 | clean; two zones deferred away (M5) |
| Transactions, unit of work, exclusion, error tolerance | 03 | deferral mechanism mis-routed (M4) |
| Credential lifecycle, handshake, session continuity | 04 | collides with 06/15/07 (D3), 12 (D4) |
| Ingestion, aggregation, reclamation | 05 | clean; owns the cross-resource instance |
| Stored artefacts, naming, residence, reclamation | 06 | collides with 04/15 (D3), 03 (M14) |
| Inbound boundary, dependency set, ingress budget | 07 | collides with 04/15 (D2), 10/12 (M9) |
| Conventions versus enforcement, declared contracts | 08 | owns the declared-contract angle |
| Test sufficiency, harness, gates-as-suite | 09 | clean; bound to the vacuous-control angle |
| Deployed operations, edge, backup, observability | 10 | bound; 13 blocks is the set maximum |
| Performance cost, materialisation, ceilings | 11 | clean on seams; R10 premises in b3 (M11) |
| Authorization, ownership, refusal disclosure | 12 | collides with 04 (D4), 07/15 (D2), 10 (M9) |
| Client tier | 13 | clean; one unowned deferral (M6) |
| Schema and migrations | 14 | clean |
| Security baseline, at-rest credentials, headers | 15 | four collisions (D1, D2, D3, M6) |
| Adjudication, namespace, seams | 99 | owns both shared angles |

**Gaps (a zone no phase owns):** the request-to-worker deferral mechanism, as named by 05/07/08
(M4); the configured retention/file-age thresholds and the queue-broker configuration (M5);
browser-side credential storage policy (M6); user-facing text ownership (M3).

**Collisions (a zone two phases both claim):** rate limiting (04/07/15/12 — D2); the one-time
secret and its retrieval handle (04/06/15/07 — D3); the account-state × surface matrix (04/12 —
D4); the vacuous-control angle (99/02/15/11/08 × 2 — D1); the cross-resource angle (05/03 — D5);
the destructive store path against live connections (01/03 — M7); the non-migration mutation
population (01/08 — M8); transport security and the declared-vs-deployed transport requirement
(12/02/10/07 — M9); the mutual-exclusion inventory (03/06 — M14).

---

## 6. Fix list

Apply in this order. Each item names the file and the edit; no re-derivation is needed.

1. **D1** — `02` b9: replace lines 105–111 with a one-clause binding to 99 and a
   configuration-gate-specific evidence fragment. Delete `15` b9 entirely (99 b2 already applies
   the angle to 15's controls). Delete `11` b2's control-existence half (`A name registered in the
   test harness is not a performance control…`), keeping the harness-coverage half. Add one
   binding clause to `08` b9 and delete `08` b10's `Do not assume a gate exists until one is found
   running` duplication.
2. **D2** — `04` b9 keeps caller-identity keying only; `15` b4 keeps coverage only; `07` b3 keeps
   the store-unavailable failure mode only and defers keying to 04; delete `12` b7's abuse-limit
   sentence and replace it with `the limit's keying and its derived identity are 04's`. Give each
   of the three surviving blocks a distinct reproduction.
3. **D3** — `04` b1 owns the handle's travel (evidence `one handle observed in a request record or
   log line` stays); `15` b2 owns recoverability at rest (delete its handle-travel fragment);
   `06` b5 owns creation-and-collection residue (delete its recoverability clause); `07` b7 deletes
   its handle sentence and replaces the evidence fragment with an endpoint-class verdict.
4. **D4** — `12` b7 owns the state-by-surface matrix; reduce `04` b7 to the claim-carried versus
   stored-record condition and defer the rest to 12.
5. **D5** — delete `03` b10; add `the record-and-file effect written by different processes is
   05's` to `03` b3; add the same deferral to `03`'s Scope Boundaries.
6. **M1** — split the taxonomy into four `- **BAND** —` bullets in `09`, `10`, `11`, `12`.
7. **M2** — restore the six-bullet `## Report Output` in `05`, `06`, `07`, `08`, `09`, `10`, `11`,
   `12`, `13`, `14`, `15`: rejoin the empty-state string to the `problems-only` bullet in 13/14/15;
   restore the RC1+RC5 sixth bullet in 05/06/07/08; drop the `— cumulative: …` clause in
   09/10/11/12.
8. **M3** — replace every `another phase's` / `a further phase's` / `another phase's suite concern`
   in `13`, `14`, `15` with the phase number (23 edits). Add an owner for `User-facing text` to
   `08`'s boundary, for `configured and sized` to `10`'s boundary, for `the drift gate` to `99`'s.
9. **M4** — replace `and the blocking-work bridge (03)` with `the deferral mechanism (01)` in
   `05`, `07`, `08`; add `the mechanism that defers work out of the request path (01)` to `03`'s
   boundary.
10. **M5** — in `05:18-19` and `06:18-19`, replace `the file-age and retention thresholds, and the
    queue-broker configuration` with `the configured bound the sweep reads (02's b3 guard
    inventory)` or delete; make `05` b10 name the owning block rather than the file.
11. **M6** — assign or delete `the health endpoint's effect on the result the client sees` (`01:15`);
    assign browser-side credential storage to `15` b1 and make `13:83` name `15`.
12. **M7/M8** — `01` b6 keeps the destructive path against live connections; `03` b9 defers to 01.
    `01` b6 keeps the mutation-path population; `08` b10 defers to 01 and keeps idempotency.
13. **M9/M10** — `10` owns transport security and the declared-vs-deployed transport requirement;
    `12` b11 defers that sentence to 10 and keeps the server-side re-check; `02` deletes
    `transport security` from its own deferral list; delete the `— one paragraph, identical in 02
    and 12…` clause from `12:19`.
14. **M11** — rewrite `11:57-58` and `15:96-97` as establish-the-shape questions with no asserted
    architecture.
15. **M12/M13** — install one collision clause verbatim in all sixteen files
    (`check for a collision before minting an identifier; report the collision rather than
    creating a second namespace`) and correct `99:27-28` to name `05, 06, 07, 08, 09, 10, 11`;
    delete the provenance clause from `14:143`.
16. **M14** — `06` b7 defers the mutual-exclusion verdict to `03` and keeps only the
    second-remover outcome.
17. **m8** — change `audit-multi-phase.md:105` from `-validated.md` to
    `-validated-findings.md` (or change `99:185`; they must agree).
18. **MINORs** — strip the leading space in `09/10/11/12` line 6; bold `Scope Boundaries`
    consistently; add the deliberate-asymmetry sentence to `02`, `03` and `04`'s Purpose; complete
    `14`'s owner list; normalise `every entry` → `every key` and `bounded at all` →
    `rate-bounded at all` in the R8 seam; normalise `check list` vs `checklist`.

After items 1–5 the set satisfies the evidence-fragment invariant. After item 6–7 and 17 the
structural signature is uniform across all sixteen files.
