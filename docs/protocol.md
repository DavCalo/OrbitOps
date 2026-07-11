# OrbitOps telemetry protocol

OrbitOps uses a fixed-width network-byte-order packet for the MVP.

The format is intentionally small and easy to inspect. It is not claimed to be CCSDS-compliant.

## Binary layout

| Field | Type | Size | Description |
|---|---:|---:|---|
| magic | 4 bytes | 4 | ASCII `ORBT` |
| version | uint8 | 1 | Protocol version, currently `1` |
| flags | uint8 | 1 | Reserved, currently `0` |
| sequence | uint32 | 4 | Monotonic sequence number |
| timestamp_ms | uint64 | 8 | Unix timestamp in milliseconds |
| mode | uint8 | 1 | `0=BOOT`, `1=NOMINAL`, `2=SAFE` |
| battery_mv | uint16 | 2 | Battery voltage in millivolts |
| bus_current_ma | uint16 | 2 | Bus current in milliamperes |
| temperature_centi_c | int16 | 2 | Temperature in hundredths of °C |
| roll_centi_deg | int16 | 2 | Roll in hundredths of a degree |
| pitch_centi_deg | int16 | 2 | Pitch in hundredths of a degree |
| yaw_centi_deg | int16 | 2 | Yaw in hundredths of a degree |
| crc32 | uint32 | 4 | CRC-32 over all previous bytes |

Total size: **35 bytes**.

## Validation rules

A receiver must reject a packet when:

- its length is not 35 bytes;
- the magic is not `ORBT`;
- the protocol version is unsupported;
- its CRC-32 does not match.

## Evolution

A future version can add:

- a packet type;
- a schema identifier;
- command acknowledgements;
- separate housekeeping and payload packets;
- optional framing compatible with a CCSDS research branch.
