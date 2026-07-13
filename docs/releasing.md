# Release process

OrbitOps uses Semantic Versioning for published technical-preview releases.

## Pre-release checklist

1. Ensure `main` is clean and CI is green.
2. Update the Python version in `ground_station/orbitops/__init__.py`.
3. Update the CMake project version in `onboard/CMakeLists.txt`.
4. Move entries from `Unreleased` into a dated `CHANGELOG.md` section.
5. Review compatibility contracts:
   - telemetry protocol and telemetry recording;
   - deterministic SplitMix64 decisions;
   - mission-profile schema, catalog, and effective fingerprints;
   - link-event schemas and legacy loading;
   - alarm-policy schema, catalog, and effective fingerprints;
   - alarm lifecycle identities, hysteresis, and transition ordering;
   - alarm-event schema, metadata, partial-run handling, and summaries.
6. Run:

   ```bash
   make clean
   make bootstrap
   make verify
   ```

7. Confirm both CLIs report `0.4.0`:

   ```bash
   orbitops --version
   ./build/orbitops_sim --version
   ```

8. Run the supported installed workflows:

   ```bash
   make profile-demo
   make alarm-demo
   ```

9. Confirm `make alarm-demo` validates:
   - installed `orbitops` executable use;
   - `thermal-demo` policy identity and fingerprint;
   - warning, critical-update, and SAFE-mode ordering;
   - cooperative listener shutdown;
   - final raised, updated, cleared, and total counters.
10. Build the wheel and run profile, alarm-policy, and alarm-event package checks.
11. Confirm supported Python versions and operating systems match CI.
12. Review the threat model and retain explicit non-flight, non-secure, non-RF, and non-CCSDS
    positioning.

## Compatibility review for v0.4.0

The v0.4.0 release makes these explicit decisions:

- binary telemetry protocol remains version `1`;
- telemetry recording remains record version `1`;
- mission-profile schema remains version `1`;
- link-event emission remains schema version `2`, with schema-version-1 reading preserved;
- alarm-policy schema begins at version `1`;
- built-in alarm-policy names and behavior-affecting values become compatibility-sensitive;
- the `standard` policy preserves v0.3 thresholds and zero hysteresis;
- one logical temperature identity uses `updated` for severity changes;
- alarm-event schema begins at version `1`;
- alarm logs require policy-aware metadata and independently verified complete-run summaries;
- interrupted alarm logs may omit the summary and remain inspectable;
- telemetry recordings, link events, and alarm events remain separate formats;
- fingerprints remain reproducibility identifiers, not authenticity evidence.

## Tag and publish

After the release PR is merged and `main` CI is green:

```bash
VERSION=0.4.0
git tag -a "v${VERSION}" -m "OrbitOps v${VERSION}"
git push origin "v${VERSION}"
```

Create a GitHub Release from the tag and include:

- changelog summary;
- supported platforms and Python versions;
- mission-profile and alarm-policy catalogs;
- link and alarm event-schema compatibility notes;
- `make alarm-demo` and its expected validated transitions;
- parser-hardening scope and separation from future continuous fuzzing;
- known security, metadata, and deployment limitations;
- GitHub-generated source archives;
- checksums for manually attached artifacts.

Do not label the release as flight-ready, safety-certified, cryptographically secure, an RF
model, or CCSDS-compliant.
