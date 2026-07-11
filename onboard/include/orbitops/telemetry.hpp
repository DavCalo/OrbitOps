#pragma once

#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace orbitops {

constexpr std::array<std::uint8_t, 4> kMagic{'O', 'R', 'B', 'T'};
constexpr std::uint8_t kVersion = 1;
constexpr std::size_t kPacketSize = 35;

enum class SpacecraftMode : std::uint8_t {
    Boot = 0,
    Nominal = 1,
    Safe = 2,
};

struct Telemetry {
    std::uint32_t sequence{};
    std::uint64_t timestamp_ms{};
    SpacecraftMode mode{SpacecraftMode::Boot};
    std::uint16_t battery_mv{};
    std::uint16_t bus_current_ma{};
    std::int16_t temperature_centi_c{};
    std::int16_t roll_centi_deg{};
    std::int16_t pitch_centi_deg{};
    std::int16_t yaw_centi_deg{};
};

inline void append_u16(std::vector<std::uint8_t>& out, std::uint16_t value) {
    out.push_back(static_cast<std::uint8_t>((value >> 8) & 0xFF));
    out.push_back(static_cast<std::uint8_t>(value & 0xFF));
}

inline void append_i16(std::vector<std::uint8_t>& out, std::int16_t value) {
    append_u16(out, static_cast<std::uint16_t>(value));
}

inline void append_u32(std::vector<std::uint8_t>& out, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        out.push_back(static_cast<std::uint8_t>((value >> shift) & 0xFF));
    }
}

inline void append_u64(std::vector<std::uint8_t>& out, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        out.push_back(static_cast<std::uint8_t>((value >> shift) & 0xFF));
    }
}

inline std::uint32_t crc32(const std::uint8_t* data, std::size_t size) {
    std::uint32_t crc = 0xFFFFFFFFu;
    for (std::size_t index = 0; index < size; ++index) {
        crc ^= data[index];
        for (int bit = 0; bit < 8; ++bit) {
            const std::uint32_t mask = -(crc & 1u);
            crc = (crc >> 1u) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

inline std::vector<std::uint8_t> encode(const Telemetry& telemetry) {
    std::vector<std::uint8_t> out;
    out.reserve(kPacketSize);
    out.insert(out.end(), kMagic.begin(), kMagic.end());
    out.push_back(kVersion);
    out.push_back(0); // reserved flags
    append_u32(out, telemetry.sequence);
    append_u64(out, telemetry.timestamp_ms);
    out.push_back(static_cast<std::uint8_t>(telemetry.mode));
    append_u16(out, telemetry.battery_mv);
    append_u16(out, telemetry.bus_current_ma);
    append_i16(out, telemetry.temperature_centi_c);
    append_i16(out, telemetry.roll_centi_deg);
    append_i16(out, telemetry.pitch_centi_deg);
    append_i16(out, telemetry.yaw_centi_deg);
    append_u32(out, crc32(out.data(), out.size()));

    if (out.size() != kPacketSize) {
        throw std::runtime_error("encoded packet has unexpected size");
    }
    return out;
}

} // namespace orbitops
