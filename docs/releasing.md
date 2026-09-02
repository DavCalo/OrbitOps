# Release process

OrbitOps uses Semantic Versioning for published technical-preview releases. The maintainer performs
all GitHub writes, tagging, artifact attachment, and publication.

## Release-candidate preparation

Technical preparation may proceed while the external walkthrough is pending, but the release PR is
not ready for merge and the release must not be published until that walkthrough is complete and any
material findings are resolved.

1. Start from a clean `main` with all required CI checks green.
2. Update the Python version in `ground_station/orbitops/__init__.py`.
3. Update the CMake project version in `onboard/CMakeLists.txt`.
4. Update exact-version package checks and any committed generated visual that displays the release
   version.
5. Review README, operations, threat-model, security, compatibility, sample-bundle, benchmark/soak,
   and release-readiness wording.
6. Complete the external walkthrough required by `docs/release-readiness.md` and resolve/retest any
   material finding.
7. Once the actual publication date is known, move the accumulated `Unreleased` entries into a dated
   `CHANGELOG.md` section and finalize the v0.5.0 release notes.
8. From a clean release-candidate checkout, run:

   ```bash
   make clean
   make bootstrap
   make verify
   ```

9. Confirm both public version surfaces report `0.5.0`:

   ```bash
   orbitops --version
   ./build/orbitops_sim --version
   ```

10. Run the supported sample session and the installed demos:

    ```bash
    orbitops session inspect \
      --telemetry examples/session-inspection/telemetry.jsonl \
      --link-events examples/session-inspection/link-events.jsonl \
      --alarm-events examples/session-inspection/alarm-events.jsonl

    make profile-demo
    make alarm-demo
    make session-demo
    ```

11. Build the distribution artifacts and run the package-resource checks:

    ```bash
    make package
    ```

12. Validate the built wheel from a fresh virtual environment, without relying on the source checkout
    as the installed package:

    ```bash
    release_root="$(mktemp -d)"
    release_python="$release_root/venv/bin/python"

    python3 -m venv "$release_root/venv"
    "$release_python" -m pip install --no-deps dist/orbitops_ground_station-0.5.0-py3-none-any.whl

    "$release_root/venv/bin/orbitops" --version
    "$release_root/venv/bin/orbitops" session inspect \
      --telemetry examples/session-inspection/telemetry.jsonl \
      --link-events examples/session-inspection/link-events.jsonl \
      --alarm-events examples/session-inspection/alarm-events.jsonl

    PATH="$release_root/venv/bin:$PATH" \
      "$release_python" scripts/alarm_event_package_check.py
    PATH="$release_root/venv/bin:$PATH" \
      "$release_python" scripts/session_inspection_package_check.py
    ```

13. Confirm `docs/evidence/SHA256SUMS.txt` still validates the retained benchmark and 60-minute soak
    JSON evidence. Those measurements are reference evidence only, not a performance SLA or general
    reliability guarantee.
14. Confirm supported Python versions and operating systems still match CI.
15. Review `docs/threat-model.md` and `SECURITY.md`; retain explicit non-flight, unauthenticated-UDP,
    non-RF, and non-CCSDS positioning.

## Compatibility review for v0.5.0

The v0.5.0 release makes these explicit compatibility decisions:

- binary telemetry protocol remains version `1`;
- telemetry recording remains record version `1`;
- mission-profile schema remains version `1`;
- link-event emission remains schema version `2`, with schema-version-1 reading preserved;
- alarm-policy schema remains version `1`;
- alarm-event schema remains version `1`;
- built-in mission profiles and alarm policies keep their published names and deterministic
  fingerprints for unchanged behavior;
- telemetry recordings, link events, and alarm events remain separate source contracts;
- `orbitops session inspect` validates those sources independently and does not claim provenance merely
  because files were selected together;
- telemetry/alarm exact correlation still requires one unique decoded packet-sequence match;
- link `packet_index` remains a separate namespace from telemetry `packet_sequence`;
- session filters affect rendered timeline entries only and do not rewrite unfiltered source counters;
- the public JSON report contract remains `orbitops.session_report/v1`;
- CLI exit codes distinguish complete, incomplete, usage, incompatible, malformed, and I/O outcomes;
- retained benchmark and soak files remain reproducibility evidence, not release-performance budgets or
  certification.

## Release PR

Before the release PR is ready to merge:

- all items in `docs/release-readiness.md` that apply before publication are complete;
- the PR carries `release` and `release blocker`;
- the PR references issue #43 without an auto-closing keyword;
- all seven required CI checks are green;
- no unresolved `release blocker` remains other than issue #43 itself, which stays open through
  publication verification.

## Tag and publish

After the release PR is merged, `main` is synchronized with `--ff-only`, and the merged tree is
verified:

```bash
VERSION=0.5.0
git tag -a "v${VERSION}" -m "OrbitOps v${VERSION}"
git push origin "v${VERSION}"
```

Create the GitHub Release from that tag using `docs/releases/v0.5.0.md` as the release-note source.
Attach the built wheel and source distribution when they are part of the supported publication path,
and publish SHA-256 checksums for manually attached artifacts.

After publication, install the published wheel/artifact into another fresh virtual environment and
verify `orbitops --version`, the installed session-inspection workflow, and the C++ version surface
from the tagged source. Close #43, epic #37, and the v0.5.0 milestone only after those checks pass.

Do not label the release as flight-ready, safety-certified, cryptographically secure, an RF model,
or CCSDS-compliant.
