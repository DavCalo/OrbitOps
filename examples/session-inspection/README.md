# Session-inspection sample bundle

This directory contains a deliberately small, synthetic evidence bundle for the public
`orbitops session inspect` workflow. It contains no credentials, private telemetry, or captured
operator data.

The three files exercise the independent evidence lanes supported by the inspector:

- `telemetry.jsonl`: two valid telemetry packets with sequences 10 and 11;
- `link-events.jsonl`: a complete schema-v2 link run with one observed corruption;
- `alarm-events.jsonl`: a complete schema-v1 alarm run with one transition correlated to packet
  sequence 11.

Inspect the bundle from the repository root after installing OrbitOps:

```bash
orbitops session inspect \
  --telemetry examples/session-inspection/telemetry.jsonl \
  --link-events examples/session-inspection/link-events.jsonl \
  --alarm-events examples/session-inspection/alarm-events.jsonl
```

Expected high-level result:

```text
status: complete compatible
sources: 3
diagnostics: 1
```

The normalized session contains five timeline entries. The one diagnostic reports the link
corruption event; the alarm transition has an exact correlation to telemetry packet sequence 11.

The `sample/*` references and `sha256:111...` / `sha256:222...` values are fixed illustrative metadata. They are not
signatures, authentication data, or provenance proofs, and they intentionally do not claim to
identify a production configuration.

`tests/test_session_sample.py` regression-checks this bundle against the production inspector so
that documentation and committed evidence cannot silently drift apart.
