# OrbitOps label policy

OrbitOps labels are controlled repository metadata used for triage, review,
release planning, and historical navigation.

Labels do not replace issue state, milestones, dependency relationships,
pull-request status, or CI results.

## Work labels

Every manually managed issue and pull request must have exactly one work label:

- `bug` — defect or unintended behavior;
- `feature` — new product capability or user-visible enhancement;
- `documentation` — documentation-only improvement;
- `maintenance` — refactoring, tooling, cleanup, or repository maintenance;
- `performance` — benchmarking, efficiency, scalability, or soak work;
- `release` — release preparation, validation, or publication.

Work labels are mutually exclusive.

## Product domains

An issue or pull request may have at most one product-domain label when the
domain materially improves filtering:

- `telemetry`
- `link`
- `alarms`
- `session inspection`
- `simulator`

Do not add a domain label merely because a related file is touched.
Cross-cutting release or repository-maintenance work may have no domain label.

## Operational qualifiers

Apply these only when they change triage or release handling:

- `epic` — coordinates multiple related issues;
- `release blocker` — must be resolved before the target release;
- `blocked` — cannot proceed until a prerequisite is resolved;
- `security` — concerns a security boundary, threat model, or vulnerability.

Qualifiers do not replace the required work label.

## GitHub triage and automation labels

The following GitHub-standard triage labels remain available:

- `duplicate`
- `invalid`
- `question`
- `wontfix`
- `good first issue`
- `help wanted`

The following automation labels may coexist with the OrbitOps taxonomy:

- `dependencies`
- `github_actions`
- `python`

## Examples

Session-inspection defect:

```text
bug
session inspection
```

Benchmark work required for a release:

```text
performance
session inspection
release blocker
```

Repository-template maintenance:

```text
maintenance
```

Release preparation spanning the product:

```text
release
release blocker
```

## Governance

- Apply labels before an issue enters active planning.
- Apply labels before a manual pull request is ready for review.
- Reassess labels when scope changes materially.
- Do not encode open, closed, merged, draft, or CI state in labels.
- Do not create one-off labels or synonyms.
- Taxonomy changes require a reviewed pull request.
- Prefer a small, stable catalog over exhaustive classification.
