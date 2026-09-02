# v0.5.0 release readiness

This document is the release-hardening checklist for OrbitOps v0.5.0. It is intentionally narrow:
it records clean-install usability, external walkthrough evidence, documentation/version
consistency, package validation, and publication checks. It does not add product scope.

## Supported clean-room paths

OrbitOps has two distinct clean-room workflows. Keep them separate when diagnosing failures.

### New-user path

From a fresh clone, create a virtual environment and install only the runtime package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

orbitops --version

cmake -S onboard -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DORBITOPS_WARNINGS_AS_ERRORS=ON
cmake --build build

./build/orbitops_sim --version
make session-demo
```

This path is expected to reach the flagship demo without installing development-only Python
tools such as Ruff or mypy.

### Maintainer path

The repository quality/release gate requires the development toolchain:

```bash
make bootstrap
make verify
```

A runtime-only `pip install -e .` is therefore not evidence that `make verify` can run; use
`make bootstrap` before the maintainer gate.

## Pre-release clean-room evidence

On 2 September 2026, commit `db0998a0245249bf8e540e88122ddbafd8fa7ac2` was exercised from a
genuinely fresh clone and fresh virtual environment on macOS with Python 3.13.7, CMake 4.1.2,
and AppleClang 21.0.0.

The new-user path completed successfully, including the C++ build and flagship session demo. The
measured shell sequence reached the demo in 10 seconds on that machine. Both Python and C++
reported the pre-release baseline version `0.4.0`.

The maintainer path also completed after `make bootstrap`: the full `make verify` gate passed,
including 300 Python tests, the C++ test, integration/demo checks, package construction/resource
checks, installed session-inspection validation, and the benchmark smoke test.

These observations are environment-specific release evidence, not performance guarantees. The
release candidate must be revalidated after the v0.5.0 version/docs changes.

## Supported sample session

The repository ships a small synthetic bundle under [`../examples/session-inspection/`](../examples/session-inspection/).
It is privacy-safe, human-reviewable, and regression-checked. From the repository root:

```bash
orbitops session inspect \
  --telemetry examples/session-inspection/telemetry.jsonl \
  --link-events examples/session-inspection/link-events.jsonl \
  --alarm-events examples/session-inspection/alarm-events.jsonl
```

The expected report is complete and compatible with three sources, five normalized timeline
entries, and one diagnostic for the intentionally represented link corruption.

## External walkthrough

A real person who did not build OrbitOps must perform the walkthrough. The maintainer or assistant
must not substitute for that reviewer or fabricate findings.

Give the reviewer the repository URL and ask them to begin with the root README rather than a
maintainer-only command transcript. The reviewer should use a fresh clone/environment and record:

- operating system and relevant tool versions;
- commit/tag tested;
- start/end time or approximate time-to-first-success;
- commands actually followed;
- points of confusion or hidden assumptions;
- failures and exact error text;
- questions raised by the session report or evidence model;
- whether the bundled sample and flagship demo were understandable;
- any suggested wording or workflow changes.

A clean outcome is valid evidence. Do not manufacture friction merely to produce findings.

### Walkthrough record template

```text
Reviewer relationship to OrbitOps:
Environment:
Commit/tag:
Time to first successful demo:
README path followed:
Sample-bundle result:
Flagship-demo result:
Confusing or ambiguous steps:
Failures/errors:
Questions about the report/evidence:
Actionable findings:
Fixes made from those findings:
Retest result:
```

Retain only technical feedback needed for the release. Do not commit reviewer credentials,
private machine paths, or unrelated personal information.

## Release-candidate checklist

Before the v0.5.0 release PR is considered ready:

- [ ] external walkthrough completed and recorded with genuine findings or a clean outcome;
- [ ] README and focused docs agree with the public CLI and current roadmap;
- [ ] compatibility, operations, threat-model, known-limit, and security language reviewed;
- [ ] raw benchmark and 60-minute soak evidence remain retained with valid checksums;
- [ ] Python reports `0.5.0`;
- [ ] C++ simulator reports `0.5.0`;
- [ ] committed sample bundle passes its regression check;
- [ ] sdist/wheel build and package-resource checks pass;
- [ ] installed session-inspection workflow passes from the built artifact;
- [ ] fresh-clone maintainer `make verify` passes on the release candidate;
- [ ] changelog and release notes describe v0.5.0 without unsupported claims;
- [ ] all seven required CI checks are green;
- [ ] no unresolved `release blocker` remains other than issue #43 itself.

The release PR must reference issue #43 without auto-closing it; do not use `Closes #43` or an
equivalent closing keyword. Issue #43 remains the release blocker until publication verification.

After the release PR is merged, publication remains a maintainer action:

- [ ] synchronize `main` with `--ff-only` and verify the merged tree;
- [ ] create the `v0.5.0` tag/release from the maintainer account;
- [ ] verify the published install/artifact and both public version surfaces;
- [ ] close issue #43, epic #37, and the milestone only after publication verification.

## Boundaries to re-check

Release wording must stay consistent with the existing project boundaries:

- [session-inspection contract](session-inspection.md);
- [operations guide](operations.md);
- [threat model](threat-model.md);
- [security policy](../SECURITY.md);
- [changelog](../CHANGELOG.md).

OrbitOps remains a technical-preview simulator. The v0.5.0 release does not imply flight
readiness, CCSDS compliance, authenticated transport, or certified alarm thresholds.
