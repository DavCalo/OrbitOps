# OrbitOps roadmap after v0.5.1

**Status:** approved planning revision — 24 September 2026
**Latest completed release:** v0.5.1
**Verified baseline:** `156a8a099fc2129645b7cb14bcf9f059e04c1190`
**Current delivery commitment:** focused v0.5.2 corrective patch, then planned v0.6.0 Bounded Evidence Core

This revision records the maintainer-approved update to the 3 September 2026 planning baseline.
It becomes canonical through the reviewed documentation merge. Issue creation follows a focused
scope review; implementation still requires the normal issue, branch, review, and verification process.
Published tags v0.5.0 and v0.5.1 must remain unchanged.

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

The near-term product outcome is narrower than a general ground segment: a technical user can
produce, inspect, and share a trustworthy explanation of an OrbitOps telemetry session; an
independent reviewer can understand the result without learning the entire toolchain.

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
| **v0.5.1** | **COMPLETED** | Published and independently verified correctness patch |
| **v0.5.2** | **COMMITTED** | Prevent conflicting recordings, unsafe text presentation, and uncaught input-boundary failures |
| **v0.6.0** | **PLANNED** | Enforce evidence contracts, bound resources, and stabilize report validation |
| **v0.7.0** | **CANDIDATE — preferred** | Static Session Explorer for local `orbitops.session_report/v1` files |
| **v0.8.0** | **CANDIDATE** | Portable review packages, reliable delivery, and one validated integration use case |
| **v0.9.0** | **CANDIDATE — conditional** | Local Operator Console only if observed user needs justify live control |
| **v1.0.0** | **EXIT CRITERIA** | Stable public platform after multiple releases of demonstrated contract maturity |

---

## v0.5.1 — Correctness Patch

**Delivery state:** COMPLETED on 24 September 2026.
**Historical purpose:** remove confirmed correctness defects found during the post-v0.5.0 audit without adding
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

### Completed delivery references

- #56 / PR #59 — C++ thermal range safety and scenario tests;
- #57 / PR #60 — strict numeric Python API invariants;
- #58 / PR #61 — release preparation, publication verification, and milestone closeout.

Release commit: `156a8a099fc2129645b7cb14bcf9f059e04c1190`.
The published tag remains immutable. Historical release notes and reference evidence are retained.

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

## v0.5.2 — Focused Input and Evidence Safety Patch

**Commitment:** COMMITTED; next focused patch before minor-release implementation.
**Basis:** targeted isolated reproductions against reconstructed v0.5.1 content, with the affected
source paths cross-checked on GitHub at the verified baseline. Reproduce on the maintainer checkout
and turn each accepted finding into a regression test before implementation.

### Required outcomes

- reject telemetry-record and alarm-log destinations that alias the same file before either file
  is opened or truncated; cover identical, normalized, symlink, and hard-link cases where supported;
- render untrusted attribute names and other operator-controlled strings without emitting terminal
  control sequences or injecting extra report lines;
- convert hostile JSON nesting failures into the documented malformed-input outcome rather than
  an unhandled traceback; do not mask unrelated programming failures with a blanket exception;
- reject non-finite or platform-unrepresentable replay delays derived from otherwise finite input
  parameters; keep ordinary valid replay behavior unchanged;
- preserve published binary formats and avoid mixing new product capability into this patch.

The existing documented overwrite behavior for a single recording is not itself classified as a
bug. The conflicting-output finding concerns two simultaneously active writers with incompatible
contracts. Terminal-output reproduction demonstrates raw control characters in captured stdout,
not remote code execution. JSON/sleep failure thresholds depend on interpreter/platform behavior.

### Exit criteria

Each fix has focused positive/negative tests, the complete local verification passes, the seven
existing functional CI checks pass, and new artifacts pass the established publication lifecycle.
No changes to resource-limit defaults, browser UI, or general schema design belong in this patch.

---
## v0.6.0 — Bounded Evidence Core

**Commitment:** PLANNED
**Entry gate:** v0.5.1 is published and verified; accepted v0.5.2 safety findings are resolved and
independently verified before new minor-release work.
**Purpose:** make the existing evidence pipeline strict, bounded, independently validable, and
scalable enough to support later user interfaces.

Scope is still subject to issue-design review. Plan six technical slices plus release verification
(seven issues) rather than hiding core assurance inside a release issue. This is an explicit,
bounded exception to the approximate three-to-six guideline, not permission to expand scope.
Only one principal implementation branch/PR is active at a time.

### Planned workstreams

#### A. Link-event contract enforcement

- validate attributes by `event_type`, not only as a generic scalar mapping;
- define exact required/optional keys and value constraints;
- preserve and test intended schema-version-1 and schema-version-2 compatibility;
- document the migration impact of stricter rejection behavior;
- decide duplicate-key, nesting, scalar-range, and string-control policies at the decoding boundary;
- preserve valid historical samples; do not silently rewrite imported evidence to pass validation.

#### B. Recording and replay time semantics

- decide whether timestamp regression is rejected or represented explicitly;
- remove silent ambiguity from negative inter-record delay handling;
- add bounded replay controls for unexpectedly large delays;
- align tests, operator documentation, and exit behavior;
- separate forensic inspection (preserve/analyze observed time regressions) from timed replay
  (reject or explicitly request a documented transform, never silently hide a regression);
- check derived timing values as well as the input operands; make cancellation interrupt long waits.

#### C. Resource boundaries

- configurable limits for evidence-file bytes, JSONL line size, and record count;
- explicit pending-delivery queue limit and overflow/backpressure behavior;
- explicit stop policy for pending deliveries: drain, cancel, or selectable documented behavior;
- bounded terminal/report behavior, including a summary-first path or prudent default timeline cap;
- deterministic resource-limit errors and bounded CI tests;
- enforce file/line/record limits while reading, not after allocating the entire input;
- budget diagnostics, ambiguous-correlation candidates, normalized objects, serialized bytes, and
  output writes as well as rendered timeline entries;
- audit profile/policy input paths and long-running recorders for explicit resource policies;
- distinguish injected packet loss from runtime overload or recorder failure;
- partial/interrupted evidence must remain visibly incomplete, not become a successful full run;
- treat `flush`, file synchronization, and crash/power-loss durability as different guarantees.

#### D. Session-report contract ecosystem

- publish a JSON Schema for `orbitops.session_report/v1`;
- provide a standalone validator;
- maintain a positive/negative compatibility corpus;
- define additive, breaking, deprecated, and unsupported-version policy;
- generate a stable sample report from the real production path;
- use a qualified JSON Schema implementation with pinned dialect and locally resolved references;
  keep optional validation dependencies explicit rather than writing a general schema engine;
- complement structural validation with documented semantic checks: counters, truncation,
  source-reference domains, and correlation cardinality; do not demand that a valid reference must
  be visible in a filtered/truncated timeline;
- define integer precision and large-number behavior before browser consumption; ordinary
  JavaScript number parsing must not silently round valid evidence values;
- validation certifies contract conformance, not authenticity, physical truth, or mission success;
- retain the version-1 contract where possible; any incompatible correction requires explicit
  versioning, migration evidence, and review rather than silently tightening the emitted domain.

#### E. Correlation scalability

- replace repeated telemetry scans with a sequence-to-source-index structure while preserving
  exact/ambiguous/impossible semantics;
- rerun the existing benchmark methodology on the same reference class of host;
- publish before/after evidence without introducing arbitrary workstation thresholds in CI;
- preserve exact/ambiguous/impossible decisions and original source-record references;
- include dense diagnostics, repeated sequences, high ambiguity, and large pending queues in
  bounded performance cases, not only nominal telemetry;
- examine validation/copying and repeated scheduler scans when profiling identifies them;
- report complexity including result size; an index alone does not bound a large candidate output.

#### F. Core assurance baseline

- increase C++ behavioral coverage beyond packet encoding where the v0.5.1 extraction permits;
- add low-cost static/security automation such as CodeQL or dependency review when it produces
  actionable signal;
- establish an owned CodeQL/security-analysis baseline and dependency triage when actionable;
- cover C++ option parsing, signal/shutdown behavior, and I/O failure boundaries without a rewrite;
- retain deterministic parser corpora and add targeted property/metamorphic tests around contracts;
- keep long fuzzing or security campaigns outside the normal PR latency budget;
- retain the existing seven functional CI job identities; explicitly document any additional
  security gate and update aggregate-check tooling rather than assuming the total stays seven;
- automate local gate capture and artifact verification with real stop-on-failure checks;
- prepare/test artifacts automatically but keep publication maintainer-controlled; any write-capable
  release workflow requires explicit protocol approval, narrow permissions, and an immutable tag;
- defer broad release-pipeline redesign and enterprise infrastructure; evaluate small provenance
  improvements independently instead of postponing every security measure until v0.9.0.

### Proposed issue ownership and dependencies

1. Link-event contracts and compatibility corpus (A).
2. Evidence-reader, replay, and report resource/time policies (B and input/output part of C).
3. Runtime pending-delivery bounds and termination policy (runtime part of C).
4. Indexed correlation and adverse-case scaling evidence (E).
5. Report schema, semantic validator, and browser-safe interoperability contract (D).
6. Core assurance baseline and C++ failure-path coverage (F).
7. Release v0.6.0 verification and publication.

Draft the report contract and resource/error policy early. Their implementation and final corpus
must reflect preceding contract and limit decisions. Freeze the public contract only after
compatibility review; correlation optimization must preserve semantics rather than redefine them.
The release issue depends on all accepted technical requirements. Re-slice an oversized issue
explicitly rather than disguising unrelated changes inside it.

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
- published artifacts are verified using the same evidence-first release discipline;
- resource exhaustion, partial capture, and malformed data cannot silently produce a misleading
  success; documented status/exit meanings are maintained;
- explain that `complete compatible` concerns evidence structure and compatibility, not fault-free
  operation, physical causality, or an autonomous control response;
- one independent user can run a supported scenario and interpret its evidence using the docs.

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
- no analytics by default;
- one shared contract corpus and separate semantic-validator rules, without duplicating correlation;
- lossless handling or explicit rejection of out-of-domain numbers before precision is lost;
- bounded input/decompression/worker memory, cancellation, virtualization, and safe text rendering;
- a committed usable demo, offline/local-file path, and clear provenance/unknown-state explanations;
- show that simulator SAFE transitions are scenario outputs, not feedback control driven by alarms.

### Go/no-go evidence

Before committing this release, validate the information architecture with real report samples and
at least one external usability review. The goal is comprehension, not merely adding a frontend
framework.

---

## v0.8.0 — Portable Review and Trustworthy Delivery

**Commitment:** CANDIDATE; subject to user evidence after the Session Explorer.
**User outcome:** another person can verify and inspect a session result without depending on the
original workstation or undocumented maintainer knowledge.

Select a small subset of these outcomes, not a universal archive platform:

- a versioned review package with report, exact source digests, producer/schema versions, applied
  filters, and limit policy; raw input inclusion is optional and privacy-reviewed;
- safe archive inspection with path, entry-count, and decompressed-size limits and no executable hooks;
- retain the existing JSONL sources and report contract rather than replace storage solely for novelty;
- distinguish file-integrity verification from proof that independent streams share provenance;
- test the exact wheel/sdist later published; retain redownload and fresh-install verification;
- practical build provenance/attestation verification and license/SBOM information where useful;
- one real integration or supported SDK example selected from an external user's workflow;
- versioned installation/support/recovery guidance and operational maintenance ownership.

A semantic A/B comparison is optional and must define incomparable runs and unmatched identities.
It must never infer causality merely from timestamps or equal packet numbers.

Do not add a database, multi-tenancy, SSO, or cloud hosting to deliver these outcomes.

---
## v0.9.0 — Optional Local Operator Console

**Commitment:** CANDIDATE — conditional, not a mandatory step toward v1.0.0.
**Entry gate:** independent users repeatedly need orchestration of live local runs, and a shared
application-service boundary plus a dedicated threat model have been approved.

Candidate scope:

- optional local entry point, localhost by default;
- explicit session state machine and safe subprocess supervision;
- start, cancel/stop, progress, status, evidence, and final report;
- bounded duration, datagrams, event rates, file sizes, pending queues, and storage;
- versioned API with the simplest sufficient live update transport;
- session authentication, Origin checks, no arbitrary filesystem access or shell interpolation;
- capture/recorder failures visible to the caller and in resulting evidence;
- UI and CLI share use cases, never duplicate domain semantics.

If user evidence does not justify this surface, leave it unimplemented. Remote mission control,
command uplink, enterprise tenancy, and flight/safety claims remain outside scope.

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

## Separate opportunity: Verification Lab

**Commitment:** RESEARCH; separate product-discovery track, not an OrbitOps feature or milestone.

The proposed laboratory would control experiments against external software/hardware, evaluate
requirements, and reproduce/reduce failures. OrbitOps presently generates and inspects telemetry;
these are related but different product responsibilities. No Rust rewrite, virtual-time kernel,
physical-model framework, temporal-logic engine, or hardware commanding is authorized here.

Bound discovery to interviews, one real test workflow, and an integration/reproduction prototype.
Re-evaluate implementation after v0.6.0 and the first independently useful v0.7.0. Require a target
user, an observed recurring problem, access to a realistic target, and evidence of repeated use
before launching a second principal development effort. Keep OrbitOps in bounded maintenance if
that new opportunity is approved; do not wait indefinitely for every candidate release.

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
- delivery state is separate from commitment: COMPLETED is historical fact, not permission for new work;
- the v0.6.0 proposal explicitly allows six technical issues plus release; do not conceal assurance
  changes or omit workstreams to meet an arbitrary issue count;
- new capabilities need a measurable user outcome and support/maintenance cost, not an enterprise label;
- output-only shell checks are not guards: check command exit codes and structured values before writes;
- scripts must avoid stale shell-state assumptions, pager-hidden output, broken quoting, and permissive
  checks that accept an expected hash merely because it appears somewhere in JSON;
- unsupported marketing claims never become acceptance criteria.

## Decision recorded on 3 September 2026

The earlier idea of beginning the Session Explorer immediately after v0.5.0 is superseded.
OrbitOps will first complete v0.5.1 correctness work and the planned v0.6.0 bounded-core foundation.
The Session Explorer remains the preferred v0.7.0 candidate, subject to its entry gate and user
validation.


## Decision recorded on 24 September 2026

Retain OrbitOps's C++/Python architecture and local evidence identity. Resolve the newly reproduced
input/evidence-safety defects in a focused patch; keep v0.6.0 as the bounded-core milestone; make
v0.7.0 a polished, independently tested review experience. Bring inexpensive assurance forward and
put portable review/delivery ahead of an optional live console. Explore Verification Lab separately.
The implementation scope remains subject to issue-level review and maintainer-controlled delivery.
