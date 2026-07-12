# Release process

OrbitOps uses Semantic Versioning for published technical-preview releases.

## Pre-release checklist

1. Ensure `main` is clean and CI is green.
2. Update the Python version in `ground_station/orbitops/__init__.py`.
3. Update the CMake project version in `onboard/CMakeLists.txt`.
4. Move entries from `Unreleased` into a dated `CHANGELOG.md` section.
5. Review compatibility contracts:
   - telemetry protocol;
   - deterministic SplitMix64 decisions;
   - mission-profile schema and built-in values;
   - canonical effective-configuration representation and golden fingerprints;
   - link-event schema and legacy loading.
6. Run:

   ```bash
   make clean
   make bootstrap
   make verify
   ```

7. Confirm both CLIs report `0.3.0`:

   ```bash
   orbitops --version
   ./build/orbitops_sim --version
   ```

8. Run the supported profile workflow:

   ```bash
   make profile-demo
   ```

9. Confirm the demo uses the installed CLI and validates profile identity, effective fingerprint, packet delivery, and final counters.
10. Confirm supported Python versions and operating systems match CI.
11. Review the threat model and retain the explicit non-flight, non-secure, non-CCSDS positioning.

## Compatibility review for v0.3.0

The v0.3.0 release makes these explicit decisions:

- mission-profile schema version remains `1`;
- built-in profile names and values become compatibility-sensitive;
- effective-configuration schema version remains `1`;
- link-event schema advances from `1` to `2`;
- new logs begin with `run_metadata`;
- schema-version-1 logs remain readable and summary-verifiable;
- packet-event attributes and summary counter names remain unchanged;
- fingerprints are reproducibility identifiers, not authenticity evidence.

## Tag and publish

After the release PR is merged and `main` CI is green:

```bash
VERSION=0.3.0
git tag -a "v${VERSION}" -m "OrbitOps v${VERSION}"
git push origin "v${VERSION}"
```

Create a GitHub Release from the tag and include:

- changelog summary;
- supported platforms and Python versions;
- profile catalog and precedence semantics;
- event-schema compatibility notes;
- demo command and expected validation;
- known security and deployment limitations;
- GitHub-generated source archives;
- checksums for manually attached artifacts.

Do not label the release as flight-ready, safety-certified, cryptographically secure, an RF model, or CCSDS-compliant.
