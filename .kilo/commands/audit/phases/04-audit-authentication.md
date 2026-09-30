---
name: 04-authentication
executor: auditor
problems-only: true
---

# Phase 04 — Credential Lifecycle

## Purpose

Audits how identity becomes a session and how a session stops being one: the one-time credential handshake end to end — issuance, where its cleartext rests, retrieval, and what its retrieval handle is exposed to — the two credentials that together constitute one session and whatever separates their lifetimes, what makes a secret acceptable and whether verification costs the same in every case, the single-use and retention guarantees in both the issuing and the spending direction, the identity namespace the handshake writes into and the privileged entries already occupying it, the conditions a credential carries against the conditions read from the stored record, session continuity, and the identity an abuse bound is keyed on together with whether the caller can choose it. The angle throughout is the guarantee as stated against the guarantee as implemented: an unbacked promise to be single-use, private or revocable is the class this phase exists to find.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: issuance, storage, single use, lifetime and refusal of every credential; what separates the two credentials that constitute one session; the identity namespace the handshake writes into; the conditions a credential carries against the conditions read from the stored record; the identity an abuse bound is keyed on and whether the caller can choose it; and what a revocation marker must be able to express to withdraw a credential. Not owned here: entry surfaces, topology and the settings that select a signing secret (01, 02); the exclusion and unit-of-work semantics behind the account and its revocation markers (03); the retrieval token's key lifetime as a store-expiry question, and the temp-file area (10, 06); outbound transport and any third-party call (07); the role hierarchy and per-object access decision, and which surfaces a request-forgery check reaches (12); the client tier's handling of the two channels and its own storage of them (13); the transport security and certificate lifecycle in front of the edge (10); hashing cost and password-at-rest policy as a general control (15); suite adequacy (09). This phase and 12 are negotiated, not partitioned: this phase owns identity resolution, binding and the session-layer consequences; 12 owns the per-request gate; neither files the same gate decision. There is no consent, personal-data or erasure zone in this system, so no deferral is declared for one. Deliberate asymmetry between tiers, environments or components is not a defect on its own; report it only where the code's own documentation misstates it.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others.

Evidence is a class, not a check list: observed behaviour, a reproduced divergence, or a static proof that a stated property does not hold; the method is the auditor's. A passing check is methodology, never a finding, and nothing here gates a finding on this phase's own checks. Where a property cannot be settled in the environment at hand — a store that cannot be reached, a path that needs a privileged identity this environment does not have — establish it from what is observable and state plainly what could not be verified and why; that residual is a limit on the report recorded in the appendix, never a finding.

### 1. The one-time credential handshake end to end: issuance, where the cleartext rests, retrieval, and what the retrieval handle is exposed to

*Establish every point at which the one-time credential is minted, what constrains how often, and what state the account is left in afterwards. Establish
where the cleartext rests between minting and use. Then map every surface the retrieval handle and the cleartext reach: the response that returns them,
the request path that carries the handle, every access and proxy record along that path, browser history, error text, caches — and rule each one inside or
outside the confidentiality boundary before calling it a leak. The handle is what authorises the read, so establish separately whether a handle that has
travelled through ordinary request logging is still a secret, and whether the account change is committed when the storage cannot accept the value at all.
Whether the stored form is recoverable at rest is 15's; the composition of every key in the store and each marker's lifetime is 10's.*
Evidence: the issuance points with the account state each leaves; the store the cleartext rests in; the per-surface inside/outside verdict for the handle and the cleartext; one handle observed in a request record or log line.

### 2. The two credentials that constitute one session: issuance paths, what each is accepted for, and what distinguishes them

*Enumerate every place a credential is minted, including the service-layer paths and any path no caller reaches, and establish what each is accepted for:
which gate reads which claim, over how long, and in which channel. Then establish whether anything inside the credential itself separates the two
lifetimes, or whether the separation rests entirely on which claim name a particular gate happens to read. A credential accepted where the other is
expected, and a gate that reads the shorter-lived claim where the longer one was presented, are both findings — as is a path that mints a credential no
gate will ever accept. The hashing cost and the at-rest policy for what the store holds are 15's.*
Evidence: the credential inventory with, per credential, its minting path, the gates that accept it and its lifetime; one gate accepting the wrong credential kind; one minting path with no reachable caller.

### 3. What makes a secret acceptable, and whether acceptance costs the same in every case

*Judge each secret as an unguessable bearer value against its own issuance and its acceptance window rather than as a bit count: where it is drawn from,
whether enumeration is infeasible within the window between issuance and use, and whether the value an attacker must enumerate can be narrowed from
anything the issuance path exposes. Judge its representation separately — safe to carry is not the same property as unpredictable. Then judge the
verification path's cost uniformity: whether presenting a secret for an identity that does not exist costs the same as presenting one that does, including
the comparison itself and any placeholder value the path substitutes when nothing matches. Demonstrate the uniformity rather than assuming it, since a
deliberately equal-cost step is exactly the kind of thing whose implementation quietly stops being one, and record the value used in place of a real secret
so its shape can be judged against what a real one takes.*
Evidence: each secret with its source, acceptance window and demonstrated enumeration cost; the comparison used when no identity matches; one submitted secret whose verification path measurably differs between a matching and a non-matching identity.

### 4. Single-use and lifetime guarantees, in both directions

*Establish, for minting and for spending alike, whether each guard is evaluated in the same indivisible step as the state change it protects, and whether
two concurrent claimants resolve to exactly one winner under real concurrency rather than under a single-threaded simulation. Then establish the failure
direction at both ends: what happens when the issuing side cannot reach the store the redemption depends on — whether the account change is still
committed, leaving a credential nobody can ever claim — and what the reading side does when the same store is unavailable, whether that is distinguishable
from a credential already claimed. Establish the retention bound, and treat a bound with no eviction guarantee as the finding rather than as the bound. A
refusal that cannot distinguish never-existed from already-claimed from cannot-be-checked-now is a finding; so is a guard defined but never reached.*
Evidence: concurrent-claim and concurrent-spend outcomes; the issuing path's behaviour when its store is unavailable and the account state afterwards; the reading side's refusal under store unavailability against a genuine double claim; the retention bound and what its own unavailability leaves behind.

### 5. The identity namespace the handshake writes into, and the privileged entries already in it

*Establish whether claiming creates an account, and whether the namespace real identities resolve into can already be occupied by an account an operator
provisioned rather than a person registered — including one keyed on a non-address default value that a real caller could supply. Establish what the
conflict clause on an existing account leaves untouched and what it overwrites, particularly any privilege or credential state that belonged to that
account before the handshake ran: a conflict path that preserves an existing privilege is a finding, and so is one that silently overwrites a live
credential. Establish also which identity the credential binds and which the per-request gate resolves later, and treat a divergence between the two as a
finding rather than as a naming difference.*
Evidence: the identity namespace inventory with its privileged occupants and the keys they occupy; one collision between an operator-provisioned entry and a registrable identity; the conflict path's before-and-after state for the privilege and credential fields.

### 6. Account state the credential cannot carry: the completion path

*Establish what spending the credential does once it is accepted: whether every guard that can refuse precedes the irreversible write, whether the visible
failure is uniform across its causes so a caller cannot distinguish a wrong secret from an unavailable dependency, and whether the credential is bound to
the client that obtained it. Record what a refused attempt leaves behind — an account record in a state neither the issuing path nor the accepting path
expects, a flag set with no corresponding write completed. Where an account carries a flag demanding a change before ordinary use, establish whether any
consuming path consults it, and a flag set at issuance and read by nothing is a finding.*
Evidence: the guard-and-write ordering per completion path; the cause-by-response matrix for refusals; one account state left behind by a refused attempt; the change-required flag with a reached/un-reached verdict.

### 7. A condition carried inside a credential against the condition read from the stored record

*Establish, for every condition the handshake encodes into the credential it hands out, the condition the stored account record is actually read under
when that credential is presented. The two are set independently and can drift apart, and a condition the credential asserts while no path reads the
record under it is a guard that exists only in something the caller holds and can present unchanged. Establish, per surface that reads either, which
one it consults, and record the drift where the issuing path and the presenting path disagree about the same account. Which account states exist, which
are consulted, on which surface, and by which resolution is 12's, and so is the per-request gate itself — an absent payload, an unresolvable identity,
a check that raises.*
Evidence: the claim-carried condition against the stored-record condition, per surface that reads either; one credential asserting a condition the stored record does not carry; one account whose claim-carried and stored-record conditions disagree.

### 8. Session continuity: what a captured long-lived credential is worth, and what a revocation marker must be able to express

*Establish what survives a credential rotation and what is actually replaced when a credential is used: whether use issues a new credential or consumes the
presented one, whether the long-lived credential is bound to the client that obtained it, and what an observer who captures it can do for its whole
remaining lifetime. Then establish, for every marker that claims to withdraw a credential, what it expresses: whether it names the specific credential, the
identity behind all of them, or a time window, and whether the gate that must honour it consults it at all. A marker whose expressiveness does not match
what the gate looks up is a finding — including one honoured on one path and not on another, and one written by an operation whose own writer no longer
checks it. The composition of every key in the store and each marker's lifetime are 10's; whether a surface is rate-bounded at all, and what credential
material the store holds, are 15's.*
Evidence: the rotation inventory with, per credential, what use replaces and what survives; one captured long-lived credential traced to the end of its lifetime; the marker inventory with, per marker, what it expresses against what the gate looks up.

### 9. The identity an abuse bound is keyed on, and whether the caller can choose it

*Establish, for every bound applied before a caller holds a credential, what identity the bound is keyed on and whether the caller chooses that identity
or it is derived from the connection — a forwarded address the caller can append to, a header the caller sets, and a value the code falls back to when
the peer address cannot be determined are each a bucket the caller chose rather than one the guard observed. Establish where an intermediary in front
makes that derived value identical for every caller, and record what the bound then distinguishes. Record the key namespaces in use and whether an
observed caller identity and a caller-supplied one can resolve to the same bucket — a caller who knows the namespace shares a bucket without needing
to forge anything. Whether a surface is rate-bounded at all is 15's; what a bound does when the store behind it is unavailable is 07's; and whether the
limiting step is one indivisible operation is 03's exclusion question.*
Evidence: the identity each bound is keyed on, observed against caller-chosen; one bound observed keyed on a value the caller supplied; one namespace where a supplied value and an observed value resolve to the same bucket.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a session established for an identity other than the one the credential was verified against; a credential's cleartext reaching a surface outside its delivery boundary; a credential still both retrievable and re-usable after a guard should have refused it.
- **HIGH** — an irreversible write preceding a guard that can still refuse; one gate admitting an account state another refuses; a claim binding an identity it never verified; a revocation marker that does not withdraw what it claims to withdraw.
- **MEDIUM** — a refusal whose visible form distinguishes causes it should not; a bearer credential with no binding to the client that obtained it; a caller identity for limiting that is asserted rather than observed; a limiter whose own unavailability silently disables it.
- **LOW** — refusals, repeated attempts and abandoned handshakes leaving no operator-visible trace; residue no reclamation path reaches; unhelpful diagnostic text on a refusal path.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/04-authentication/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `AUTH-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A refusal observed without a live store is recorded as a limit on the report, not a finding; a shipped test asserting the current behaviour is a remediation blocker, not a gate
