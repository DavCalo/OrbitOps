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

### Walkthrough result — 2 September 2026

An independent reviewer with no prior OrbitOps experience tested release-candidate commit
`b052f9967f87572a4fd3ab665e2f602492e60a25` from a fresh clone on macOS. AppleClang
21.0.0.21000101 was recorded; Python and CMake versions were not recorded. The reviewer reached the
first successful demo in approximately 11–12 minutes and reported roughly 40–45 minutes of active
walkthrough time.

The runtime CLI and C++ simulator both reported `0.5.0`. The supported sample bundle and flagship
session demo passed. The reviewer also successfully exercised the focused alarm/profile demos,
built-in alarm-policy commands, and manual multi-terminal workflows. Attempts to run generated-file
and illustrative external-file examples exposed the documentation findings below.

The walkthrough found documentation/usability friction rather than a runtime or packaging defect:

- the `sessions/mission-*.jsonl` inspection examples appeared runnable before the README had
  generated those files, producing file-not-found errors;
- the external alarm-policy example referenced an illustrative file that is not shipped; the
  analogous external mission-profile path had the same latent ambiguity;
- a first-time reader needed clearer guidance for interpreting `SUMMARY`, `SOURCES`, `DIAGNOSTICS`,
  and `TIMELINE`, and for understanding the conservative provenance wording;
- `fingerprint` needed an early plain-language definition;
- the static session visual could be mistaken for a UI launched by `make session-demo`;
- the distinctions among `session-demo`, `alarm-demo`, and `profile-demo`, and the roles of the
  terminals in manual workflows, needed clearer signposting.

The walkthrough-fix tranche addresses these findings by making the committed sample the first
runnable session-inspection example, clarifying generated-file prerequisites, replacing placeholder
validation paths with bundled resources, explaining the terminal-only demo and static visual, and
describing the purpose of the focused demos and terminal roles. The amended documentation was
subsequently independently retested at commit
`757e2989dadfb1f782796ea0c00d7f137abdaa3d`, with all targeted findings reported as resolved.

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

### Independent remediation retest — 2 September 2026

A second independent reviewer with no prior OrbitOps involvement retested the walkthrough
remediation at commit `757e2989dadfb1f782796ea0c00d7f137abdaa3d`.

Outcome: **PASS WITH MINOR COMMENTS**.

All targeted walkthrough findings were independently reported as resolved:

- the repository-hosted session-inspection sample is discoverable and runnable from a fresh clone;
- generated `sessions/mission-*.jsonl` paths are identified as outputs that must exist before
  inspection;
- the alarm-policy and mission-profile validation examples are runnable rather than placeholder
  paths;
- `make session-demo` is clearly described as a terminal-only workflow and the README visual as a
  static representation;
- the report reading order and the meanings of fingerprint and cross-stream provenance are
  understandable at a new-user level;
- the purposes of `session-demo`, `alarm-demo`, and `profile-demo` are distinguishable;
- multi-terminal ground-station, link-emulator, and simulator roles are understandable.

No command errors were reported during the targeted retest.

The reviewer noted three residual, non-blocking usability observations: the term
“session inspection” may not be immediately discoverable to a non-technical first-time user;
“fingerprint” can initially evoke credentials or other unrelated meanings before its explanation
is read; and the role of the third terminal may still require minor inference. These observations
are accepted as non-blocking for the v0.5.0 technical-preview release and do not invalidate the
successful remediation retest.

## Release-candidate checklist

Before the v0.5.0 release PR is considered ready:

- [x] external walkthrough completed and recorded with genuine findings or a clean outcome;
- [x] walkthrough findings resolved and independently retested on commit `757e2989dadfb1f782796ea0c00d7f137abdaa3d`;
- [x] README and focused docs agree with the public CLI and current roadmap;
- [x] compatibility, operations, threat-model, known-limit, and security language reviewed;
- [x] raw benchmark and 60-minute soak evidence remain retained with valid checksums;
- [x] Python reports `0.5.0`;
- [x] C++ simulator reports `0.5.0`;
- [x] committed sample bundle passes its regression check;
- [x] sdist/wheel build and package-resource checks pass;
- [x] installed session-inspection workflow passes from the built artifact;
- [x] fresh-clone maintainer `make verify` passes on the release candidate;
- [x] changelog and release notes describe v0.5.0 without unsupported claims;
- [x] all seven required CI checks are green;
- [x] no unresolved `release blocker` remains other than issue #43 itself.

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
