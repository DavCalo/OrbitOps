# OrbitOps telemetry protocol

OrbitOps protocol version 1 uses one fixed-width, network-byte-order telemetry packet.

The format is intentionally small and inspectable. It is **not CCSDS-compliant**, authenticated, or encrypted.

## Binary layout

| Offset | Field | Type | Size | Description |
|---:|---|---|---:|---|
| 0 | magic | bytes | 4 | ASCII `ORBT` |
| 4 | version | uint8 | 1 | Protocol version, currently `1` |
| 5 | flags | uint8 | 1 | Reserved; must be `0` in version 1 |
| 6 | sequence | uint32 | 4 | Monotonic sequence number with 32-bit wraparound |
| 10 | timestamp_ms | uint64 | 8 | Unix timestamp in milliseconds |
| 18 | mode | uint8 | 1 | `0=BOOT`, `1=NOMINAL`, `2=SAFE` |
| 19 | battery_mv | uint16 | 2 | Battery voltage in millivolts |
| 21 | bus_current_ma | uint16 | 2 | Bus current in milliamperes |
| 23 | temperature_centi_c | int16 | 2 | Temperature in hundredths of °C |
| 25 | roll_centi_deg | int16 | 2 | Roll in hundredths of a degree |
| 27 | pitch_centi_deg | int16 | 2 | Pitch in hundredths of a degree |
| 29 | yaw_centi_deg | int16 | 2 | Yaw in hundredths of a degree |
| 31 | crc32 | uint32 | 4 | IEEE CRC-32 over bytes 0–30 |

Total size: **35 bytes**.

## Validation rules

A receiver rejects a packet when:

- its length is not exactly 35 bytes;
- the magic is not `ORBT`;
- the protocol version is unsupported;
- reserved flags are nonzero;
- the spacecraft mode is not defined;
- its CRC-32 does not match.

CRC-32 protects against accidental corruption only. It does not authenticate the sender and does not prevent deliberate modification.

## Golden vector

The project uses this cross-language reference packet in tests:

| Field | Value |
|---|---:|
| sequence | 42 |
| timestamp_ms | 1726000000123 |
| mode | NOMINAL |
| battery_mv | 8120 |
| bus_current_ma | 455 |
| temperature_centi_c | 2734 |
| roll_centi_deg | -125 |
| pitch_centi_deg | 75 |
| yaw_centi_deg | -17750 |

Encoded hexadecimal representation:

```text
4f52425401000000002a00000191dd9dec7b011fb801c70aaeff83004bbaaa28ec5b7a
```

C++ encoding and Python decoding must both agree with this vector.

## Compatibility policy

- Field meaning and position do not change within protocol version 1.
- A breaking wire-format change requires a new protocol version.
- Reserved fields must not be repurposed without a versioning decision.
- Receivers reject unsupported versions rather than guessing a layout.
- New packet families should add an explicit packet type or schema identifier.

## Future evolution

Potential version 2 work includes:

- packet type and schema identifier;
- command packets and acknowledgements;
- separate housekeeping and payload telemetry;
- authenticated envelopes;
- optional framing explored in a separate CCSDS research track.
