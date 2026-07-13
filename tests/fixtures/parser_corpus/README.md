# Malformed parser corpus

These fixtures are deterministic, bounded regression inputs for OrbitOps public parsers.

- `protocol/`: malformed binary telemetry packets;
- `telemetry-recording/`: malformed version-1 replay records;
- `link-events/`: malformed link-event JSONL;
- `alarm-events/`: malformed alarm-event JSONL;
- `mission-profiles/`: malformed mission-profile TOML;
- `alarm-policies/`: malformed alarm-policy TOML.

Fixtures contain no credentials, private telemetry, or remotely sourced data. New parser
defects should be reduced to the smallest stable input before being added here.
