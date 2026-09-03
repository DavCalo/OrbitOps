# OrbitOps roadmap after v0.5.0

**Status:** approved planning baseline — 3 September 2026
**Latest completed release:** v0.5.0
**Current delivery commitment:** v0.5.1 Correctness Patch

This roadmap is directional. Only work marked **COMMITTED** is approved for issue creation and
near-term delivery. Later releases express sequencing and entry criteria, not promises of dates or
fixed scope.

## Strategic objective

Evolve OrbitOps from a terminal-first technical preview into a dependable, understandable local
telemetry and evidence platform without losing its defining strengths:

- deterministic behavior;
- explicit and independently reviewable contracts;
- minimal runtime dependencies;
- compatibility discipline;
- reproducible evidence;
- verified release artifacts;
- honest security and operational boundaries.

The order of work is deliberate:

1. correct known defects in existing behavior;
2. enforce the contracts already documented;
3. bound resource use and define failure behavior;
4. stabilize the machine-readable session-report ecosystem;
5. improve accessibility through a static local-data explorer;
6. only then add live control surfaces and their security obligations.

## Product boundaries

OrbitOps remains technical-preview simulation software. It is not flight software, a secure
communications system, an RF propagation model, a safety-certified alarm system, or a claim of
CCSDS compliance.

The roadmap must not blur these boundaries merely to make the project appear broader. New scope
must be justified by a concrete user problem and by evidence that the existing product foundation
can support it safely.

## Commitment levels

- **COMMITTED** — the next approved release. Its scope is narrow enough to turn into issues.
- **PLANNED** — the intended next product direction, with entry and exit criteria; issue slicing is
  deferred until the preceding release is complete.
- **CANDIDATE** — a plausible direction that still requires evidence and an explicit go/no-go
  decision.
- **RESEARCH** — an investigation topic, not product scope or a release promise.

Only one release milestone should be active at a time. Distant work stays in this document rather
than becoming speculative issue backlog.

## Release sequence

| Release | Commitment | Primary outcome |
|---|---|---|
| **v0.5.1** | **COMMITTED** | Correct known numeric/runtime defects without expanding public capability |
| **v0.6.0** | **PLANNED** | Enforce evidence contracts, bound resources, and stabilize report validation |
| **v0.7.0** | **CANDIDATE — preferred** | Static Session Explorer for local `orbitops.session_report/v1` files |
| **v0.8.0** | **CANDIDATE** | Local Operator Console built on a shared application-service boundary |
| **v0.9.0** | **CANDIDATE** | Operational trust, delivery, and long-term verification improvements |
| **v1.0.0** | **EXIT CRITERIA** | Stable public platform after multiple releases of demonstrated contract maturity |

---

## v0.5.1 — Correctness Patch

**Commitment:** COMMITTED
**Purpose:** remove confirmed correctness defects found during the post-v0.5.0 audit without adding
new product capability or changing public evidence formats.

### Required outcomes

#### 1. Thermal scenario range safety

- eliminate temperature wrap/sign inversion in long C++ thermal runs;
- define explicit behavior at and beyond the representable telemetry range;
- prefer visible, deterministic failure over silent corruption;
- cover the boundary and a long-running scenario in tests;
- exercise the relevant scenario path under ASan/UBSan.

The acceptance criterion is not a particular implementation such as clamping. It is that no public
scenario can silently emit numerically corrupted telemetry.

#### 2. Strict numeric public APIs

- reject Python `bool` values where the public API requires integers;
- require a real integer for `LinkRuntime.run(max_packets=...)`;
- perform a focused audit of adjacent public numeric inputs for the same inconsistency;
- add regression tests beside each corrected invariant.

#### 3. Minimum C++ scenario regression coverage

- separate enough scenario-generation logic from socket/sleep orchestration to test it directly;
- test thermal and power curves, mode transitions, and representable boundaries;
- keep the refactor minimal and release-focused.

#### 4. Patch-release documentation and verification

- document corrected behavior and any explicit scenario boundary;
- update changelog and release notes without changing the immutable v0.5.0 tag;
- build, publish, redownload, and verify v0.5.1 artifacts using the established release process.

### Expected issue slicing

Issue numbers are intentionally not assigned yet. The preferred initial decomposition is:

1. C++ thermal range safety and scenario tests;
2. Python numeric API strictness audit and regression tests;
3. v0.5.1 release verification and closeout.

Split further only if audit evidence shows that one slice cannot remain reviewable.

### Non-goals

- UI work;
- new protocol or evidence-schema versions;
- a general resource-limit framework;
- session-inspection optimization beyond a correctness requirement;
- supply-chain redesign;
- command uplink.

### Exit criteria

- no thermal wrap or sign inversion in the documented scenario domain;
- behavior beyond the domain is explicit, deterministic, and tested;
- numeric public APIs reject invalid boolean/non-integer inputs consistently;
- C++ boundary and long-run regression tests pass, including the sanitizer path;
- full local verification and all seven required CI jobs pass;
- published v0.5.1 artifacts are downloaded and independently checksum/install/version verified.

---

## v0.6.0 — Bounded Evidence Core

**Commitment:** PLANNED
**Entry gate:** v0.5.1 published and verified, with no unresolved correctness blocker.
**Purpose:** make the existing evidence pipeline strict, bounded, independently validable, and
scalable enough to support later user interfaces.

The final issue decomposition is deferred until the v0.5.1 release boundary. The intended work must
fit into no more than roughly six focused issues.

### Planned workstreams

#### A. Link-event contract enforcement

- validate attributes by `event_type`, not only as a generic scalar mapping;
- define exact required/optional keys and value constraints;
- preserve and test intended schema-version-1 and schema-version-2 compatibility;
- document the migration impact of stricter rejection behavior.

#### B. Recording and replay time semantics

- decide whether timestamp regression is rejected or represented explicitly;
- remove silent ambiguity from negative inter-record delay handling;
- add bounded replay controls for unexpectedly large delays;
- align tests, operator documentation, and exit behavior.

#### C. Resource boundaries

- configurable limits for evidence-file bytes, JSONL line size, and record count;
- explicit pending-delivery queue limit and overflow/backpressure behavior;
- explicit stop policy for pending deliveries: drain, cancel, or selectable documented behavior;
- bounded terminal/report behavior, including a summary-first path or prudent default timeline cap;
- deterministic resource-limit errors and bounded CI tests.

#### D. Session-report contract ecosystem

- publish a JSON Schema for `orbitops.session_report/v1`;
- provide a standalone validator;
- maintain a positive/negative compatibility corpus;
- define additive, breaking, deprecated, and unsupported-version policy;
- generate a stable sample report from the real production path.

#### E. Correlation scalability

- replace repeated telemetry scans with a sequence-to-source-index structure while preserving
  exact/ambiguous/impossible semantics;
- rerun the existing benchmark methodology on the same reference class of host;
- publish before/after evidence without introducing arbitrary workstation thresholds in CI.

#### F. Core assurance baseline

- increase C++ behavioral coverage beyond packet encoding where the v0.5.1 extraction permits;
- add low-cost static/security automation such as CodeQL or dependency review when it produces
  actionable signal;
- defer mature SBOM/attestation and release-pipeline redesign to the operational-trust track.

### Non-goals

- browser UI;
- live local control plane;
- remote deployment;
- authentication/RBAC;
- database-backed session catalog;
- command uplink.

### Exit criteria

- documented link-event semantics are enforced by the loader;
- every primary evidence input and output path has an explicit resource policy;
- replay time behavior is unambiguous and tested;
- session-report v1 can be validated independently from the OrbitOps CLI;
- normalize/correlate is no longer dominated by the known repeated-scan algorithm;
- compatibility and migration impact are documented;
- published artifacts are verified using the same evidence-first release discipline.

---

## v0.7.0 — Accessible Session Explorer

**Commitment:** CANDIDATE — preferred direction
**Entry gate:** v0.6.0 must first establish the report schema, validator, compatibility policy, and
resource boundaries required by the explorer.

**User outcome:** a person can open a local session report and understand status, source
completeness, diagnostics, timeline, and limitations without using the terminal or uploading data.

### Candidate principles

- static web application;
- no backend and no cloud upload;
- browser-local file processing;
- consumes `orbitops.session_report/v1` through its published schema;
- never reimplements correlation or alarm semantics;
- malformed or unsupported reports fail clearly;
- overview, diagnostics, and virtualized/filterable timeline;
- persistent indication of local file, demo data, truncation, and incompleteness;
- keyboard accessibility, responsive layout, and WCAG 2.2 AA target;
- component, end-to-end, and accessibility regression tests;
- no analytics by default.

### Go/no-go evidence

Before committing this release, validate the information architecture with real report samples and
at least one external usability review. The goal is comprehension, not merely adding a frontend
framework.

---

## v0.8.0 — Local Operator Console

**Commitment:** CANDIDATE
**Entry gate:** the Session Explorer must demonstrate real value, and OrbitOps must have a shared
application-service boundary rather than separate CLI/UI logic.

Candidate scope:

- optional `orbitops console` entry point;
- localhost-only bind by default;
- explicit session state machine;
- safe process supervision;
- versioned local API and SSE if sufficient;
- start, stop, status, events, and final report;
- session token and Origin checking;
- no shell interpolation or arbitrary filesystem browsing;
- duration, packet, file, event-rate, and queue limits;
- dedicated web/API threat model.

This release must not become a disguised remote mission-control product.

---

## v0.9.0 — Operational Trust and Delivery

**Commitment:** CANDIDATE

Potential outcomes, selected only when justified by actual use:

- separate release workflow;
- build once, test the same artifact, publish the same artifact;
- Trusted Publishing through OIDC if PyPI distribution is adopted;
- SBOM and artifact attestations;
- scheduled security and dependency analysis;
- coverage-guided fuzzing campaigns outside the pull-request budget;
- structured internal logs and vendor-neutral optional telemetry export;
- regression budgets based on multiple release observations rather than one host/run;
- improved maintainer documentation and reduced single-maintainer operational risk.

Command uplink is not automatically part of v0.9.0.

---

## v1.0.0 — Stable Public Platform

**Commitment:** EXIT CRITERIA, not a date or promised release

A v1.0 decision requires evidence accumulated across multiple releases, including:

- stable public contracts and deprecation policy;
- explicit support matrix and migration guide;
- versioned documentation;
- automated and attestable release process;
- active security automation;
- performance history and justified regression budgets;
- stable, accessible Session Explorer;
- stable local console only if user evidence supports it;
- repeated independent usability feedback;
- no known blocker in public contract behavior;
- maintainer guide, recovery exercise, and reduced bus-factor risk;
- third-party dependency licensing notices;
- a tabletop exercise of the security and release process.

---

## Research track

These subjects are not assigned to a release until a concrete user, problem, contract, threat-model
impact, and acceptance evidence are defined:

- command uplink;
- signed run manifests;
- CCSDS adapters;
- hardware-in-the-loop;
- multi-satellite orchestration;
- remote deployment and authentication;
- session catalog or database;
- RF propagation;
- machine-learning anomaly detection.

## Maintenance lane

Security fixes, dependency updates, CI pin maintenance, and small documentation corrections may be
handled independently of the product roadmap when they are focused and fully verified. A confirmed
correctness regression may trigger a patch release without waiting for the next planned minor
release.

## Roadmap governance

A capability enters a release only after answering:

1. Who uses it?
2. Which concrete problem does it solve?
3. Which contract does it change or depend on?
4. How is it tested?
5. How does it fail?
6. Which security surface does it add?
7. Which evidence demonstrates completion?
8. What remains explicitly out of scope?

Operational rules:

- one active release milestone at a time;
- one main application branch/PR in progress at a time, except bounded maintenance;
- an epic only when several issues genuinely require coordination;
- approximately three to six focused issues per release as a planning guardrail;
- no speculative issue creation for candidate or research releases;
- roadmap review at every release boundary;
- unsupported marketing claims never become acceptance criteria.

## Decision recorded on 3 September 2026

The earlier idea of beginning the Session Explorer immediately after v0.5.0 is superseded.
OrbitOps will first complete v0.5.1 correctness work and the planned v0.6.0 bounded-core foundation.
The Session Explorer remains the preferred v0.7.0 candidate, subject to its entry gate and user
validation.
