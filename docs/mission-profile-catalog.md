# Mission profile catalog

OrbitOps v0.3 ships a small stable catalog of deterministic link-emulator profiles. They are reproducible examples and test fixtures, not RF propagation models or flight-qualified channel definitions.

## Built-in profiles

| Name | Seed | Loss | Duplicate | Corrupt | Latency | Jitter | Reorder window |
|---|---:|---:|---:|---:|---:|---:|---:|
| `nominal` | 0 | 0 | 0 | 0 | 0 ms | 0 ms | 0 |
| `intermittent-loss` | 202603 | 0.15 | 0 | 0 | 80 ms | 20 ms | 1 |
| `high-latency` | 202604 | 0.01 | 0 | 0 | 750 ms | 150 ms | 2 |
| `degraded-link` | 42 | 0.05 | 0.02 | 0.01 | 120 ms | 30 ms | 3 |

Names and effective values are compatibility-sensitive. Changing one changes future run fingerprints and requires an explicit changelog and compatibility review.

## CLI

```bash
orbitops profile list
orbitops profile show intermittent-loss
orbitops profile validate file:profiles/custom.toml
orbitops link --profile intermittent-loss
```

Resolution forms:

- short built-in name;
- existing file path;
- `builtin:<name>`;
- `file:<path>`.

A short string matching both a built-in and a local file is rejected as ambiguous.

## Override semantics

```text
LinkConfig defaults -> selected profile -> explicit CLI options
```

Explicit zero values override non-zero profile values. Omitted options preserve the profile.

## Fingerprints and logs

The fingerprint covers the effective `LinkConfig` after overrides. Profile name, description, source formatting, and reference syntax do not change the fingerprint when effective values are equal.

Schema-version-2 link logs begin with `run_metadata`, recording:

- effective configuration fingerprint;
- profile name;
- original profile reference;
- profile schema version.

The fingerprint supports reproducibility comparison. It does not authenticate a profile or log.

## Python API

```python
from orbitops.profiles import (
    configuration_fingerprint,
    list_builtin_profiles,
    load_builtin_profile,
    load_mission_profile_file,
    resolve_mission_profile,
)
```

The TOML resources live in `orbitops.profiles.builtin` and are included in the wheel. CI installs the wheel and loads every built-in profile through `importlib.resources`.
