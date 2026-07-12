# Alarm-policy catalog

OrbitOps distributes four versioned alarm policies as Python package resources. They
are deterministic operational examples and test fixtures, not flight-certified limits.

| Name | Purpose |
| --- | --- |
| `standard` | Preserves the effective OrbitOps v0.3 thresholds and zero hysteresis. |
| `conservative` | Raises warnings earlier and requires wider recovery margins. |
| `thermal-demo` | Makes the deterministic thermal scenario produce visible lifecycle transitions quickly. |
| `power-demo` | Makes the deterministic power scenario produce visible low-battery transitions quickly. |

## References

Alarm policies use the same explicit local-resolution model as mission profiles:

- `builtin:standard` always selects a bundled policy;
- `file:policies/custom.toml` always selects a local UTF-8 TOML file;
- `standard` may select the built-in policy when no file named `standard` exists;
- a bare reference matching both namespaces is rejected as ambiguous;
- path-like Python values always select local files.

OrbitOps never downloads policy files or resolves remote URLs.

## CLI

```console
orbitops alarm-policy list
orbitops alarm-policy show conservative
orbitops alarm-policy validate file:policies/custom.toml
orbitops listen --alarm-policy thermal-demo
```

`show` and `validate` emit compact, sorted-key JSON for scripting. Policy resolution and
validation complete before the listener binds UDP or creates a telemetry recording.

Running `orbitops listen` without `--alarm-policy` uses the immutable backward-compatible
`standard` policy.

## Packaging contract

The TOML resources live under `orbitops.alarm_policies.builtin` and are included in the
wheel through setuptools package-data configuration. CI installs the built wheel and runs
`scripts/alarm_policy_package_check.py` to verify catalog identity, resource availability,
fingerprint uniqueness, and standard-policy compatibility.
