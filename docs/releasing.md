# Release process

OrbitOps uses Semantic Versioning for published technical-preview releases. The maintainer performs
all GitHub writes, tagging, artifact attachment, and publication.

The release-specific issue is authoritative for release scope, blockers, and any additional gates.
The generic process below must not weaken those requirements.

## Release-candidate preparation

1. Start from a clean, current `main` after all release-blocking implementation issues have been
   merged and independently verified.
2. Create a focused release branch from that exact `main` commit.
3. Update the Python version in `ground_station/orbitops/__init__.py`.
4. Update the CMake project version in `onboard/CMakeLists.txt`.
5. Update exact-version package checks, README version surfaces, and any committed generated visual
   that displays the release version.
6. Review operations, threat-model, security, compatibility, sample-bundle, retained evidence, and
   release-readiness wording for impact from the release changes.
7. Complete an external usability walkthrough only when the release issue requires one or when the
   release materially changes the documented onboarding/operator workflow. Resolve and retest any
   material finding before making the release PR ready.
8. Once the intended publication date is known, move the accumulated `Unreleased` entries into a
   dated `CHANGELOG.md` section and finalize focused release notes under `docs/releases/`.
9. From a clean release-candidate checkout, run:

   ```bash
   make clean
   make bootstrap
   make verify
   ```

10. Confirm both public version surfaces report the intended release version:

    ```bash
    orbitops --version
    ./build/orbitops_sim --version
    ```

11. Run the supported sample session and installed demos:

    ```bash
    orbitops session inspect \
      --telemetry examples/session-inspection/telemetry.jsonl \
      --link-events examples/session-inspection/link-events.jsonl \
      --alarm-events examples/session-inspection/alarm-events.jsonl

    make profile-demo
    make alarm-demo
    make session-demo
    ```

12. Build the distribution artifacts and run the package-resource checks:

    ```bash
    make package
    ```

13. Validate the built wheel from a fresh virtual environment, without relying on the source checkout
    as the installed package. Set `VERSION` to the release version first:

    ```bash
    VERSION="$(PYTHONPATH="$PWD/ground_station" python3 -c 'import orbitops; print(orbitops.__version__)')"
    release_root="$(mktemp -d)"
    release_python="$release_root/venv/bin/python"
    release_wheel="dist/orbitops_ground_station-${VERSION}-py3-none-any.whl"

    python3 -m venv "$release_root/venv"
    "$release_python" -m pip install --no-deps "$release_wheel"

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

14. Confirm `docs/evidence/SHA256SUMS.txt` still validates any retained reference evidence that the
    release issue requires preserving. Do not reinterpret retained measurements as a performance SLA
    or general reliability guarantee.
15. Confirm supported Python versions and operating systems still match CI.
16. Review `docs/threat-model.md` and `SECURITY.md`; retain explicit non-flight, unauthenticated-UDP,
    non-RF, and non-CCSDS positioning unless a separately reviewed change explicitly alters a boundary.

## Compatibility review

For every release, record whether each public compatibility surface is unchanged, additively changed,
or intentionally broken. At minimum review:

- binary telemetry protocol version and byte layout;
- telemetry recording version;
- mission-profile schema;
- link-event emitted/readable schema versions;
- alarm-policy schema;
- alarm-event schema;
- built-in mission-profile and alarm-policy names and fingerprints;
- telemetry, link-event, and alarm-event source boundaries;
- session-inspection correlation semantics and source identity assumptions;
- the public `orbitops.session_report` format;
- CLI syntax and exit-code semantics.

A patch release must not silently change a serialized compatibility contract.

## Release PR

Before the release PR is ready to merge:

- all release-specific pre-publication requirements are complete;
- the PR carries `release` and `release blocker`;
- the PR references the release issue without an auto-closing keyword;
- all seven required CI checks are green on the final PR head;
- no unresolved release blocker remains other than the release issue itself, which stays open through
  publication verification.

## Tag and publish

After the release PR is squash-merged, synchronize `main` with `--ff-only` and run the complete
post-merge verification before creating a tag. Set `VERSION` to the verified release version:

```bash
VERSION="$(PYTHONPATH="$PWD/ground_station" python3 -c 'import orbitops; print(orbitops.__version__)')"
git tag -a "v${VERSION}" -m "OrbitOps v${VERSION}"
git push origin "v${VERSION}"
```

Create the GitHub Release from the matching `docs/releases/v${VERSION}.md` release-note source.
Attach the supported wheel and source distribution and publish a SHA-256 manifest for manually
attached artifacts.

After publication:

1. download the published assets again rather than trusting the pre-publication copies;
2. verify their SHA-256 checksums;
3. install the downloaded wheel into another fresh virtual environment;
4. verify `orbitops --version` and the supported installed package/session checks;
5. check out the published tag and verify the C++ simulator version surface from tagged source;
6. close the release issue and milestone only after every publication-verification gate passes.

Do not label a release as flight-ready, safety-certified, cryptographically secure, an RF model,
or CCSDS-compliant.
