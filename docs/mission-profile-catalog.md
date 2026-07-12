# Mission profile catalog

OrbitOps v0.3 introduces a small, stable catalog of deterministic link-emulator
profiles. These profiles are reproducible examples and test fixtures. They are not
RF propagation models and do not make flight-readiness or CCSDS-compliance claims.

## Built-in profiles

| Name | Seed | Loss | Duplicate | Corrupt | Latency | Jitter | Reorder window |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `nominal` | 0 | 0 | 0 | 0 | 0 ms | 0 ms | 0 |
| `intermittent-loss` | 202603 | 0.15 | 0 | 0 | 80 ms | 20 ms | 1 |
| `high-latency` | 202604 | 0.01 | 0 | 0 | 750 ms | 150 ms | 2 |
| `degraded-link` | 42 | 0.05 | 0.02 | 0.01 | 120 ms | 30 ms | 3 |

The names and effective values above are compatibility-sensitive. Changing a
built-in profile changes the fingerprint of runs that use it and therefore requires
an explicit changelog entry.

## Python API

```python
from orbitops.profiles import (
    list_builtin_profiles,
    load_builtin_profile,
    load_mission_profile_file,
    resolve_mission_profile,
)
```

- `list_builtin_profiles()` returns the stable catalog order.
- `load_builtin_profile("nominal")` loads a bundled resource.
- `load_mission_profile_file("scenario.toml")` loads an explicit UTF-8 file.
- `resolve_mission_profile(...)` accepts built-in names, file paths, and explicit
  `builtin:<name>` or `file:<path>` references.

A bare string that matches both a built-in name and a local file is rejected as
ambiguous. The caller must select the intended namespace explicitly. Path-like
objects always identify external files.

## Packaging contract

The TOML files live in `orbitops.profiles.builtin` and are included as package data.
The CI package smoke test installs the wheel and loads every built-in profile through
`importlib.resources`; this detects missing resources before merge.
