#include "orbitops/telemetry.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>

namespace {

bool require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "packet test failed: " << message << '\n';
        return false;
    }
    return true;
}

} // namespace

int main() {
    orbitops::Telemetry telemetry;
    telemetry.sequence = 42;
    telemetry.timestamp_ms = 1726000000123ULL;
    telemetry.mode = orbitops::SpacecraftMode::Nominal;
    telemetry.battery_mv = 8120;
    telemetry.bus_current_ma = 455;
    telemetry.temperature_centi_c = 2734;
    telemetry.roll_centi_deg = -125;
    telemetry.pitch_centi_deg = 75;
    telemetry.yaw_centi_deg = -17750;

    const auto packet = orbitops::encode(telemetry);
    constexpr std::array<std::uint8_t, orbitops::kPacketSize> expected{
        0x4F, 0x52, 0x42, 0x54, 0x01, 0x00, 0x00, 0x00, 0x00, 0x2A, 0x00, 0x00,
        0x01, 0x91, 0xDD, 0x9D, 0xEC, 0x7B, 0x01, 0x1F, 0xB8, 0x01, 0xC7, 0x0A,
        0xAE, 0xFF, 0x83, 0x00, 0x4B, 0xBA, 0xAA, 0x28, 0xEC, 0x5B, 0x7A,
    };

    if (!require(packet.size() == expected.size(), "unexpected packet size")) {
        return 1;
    }
    if (!require(
            std::equal(packet.begin(), packet.end(), expected.begin(), expected.end()),
            "packet differs from golden vector")) {
        return 1;
    }

    const std::uint32_t encoded_crc =
        (static_cast<std::uint32_t>(packet[packet.size() - 4]) << 24) |
        (static_cast<std::uint32_t>(packet[packet.size() - 3]) << 16) |
        (static_cast<std::uint32_t>(packet[packet.size() - 2]) << 8) |
        static_cast<std::uint32_t>(packet[packet.size() - 1]);
    const std::uint32_t calculated_crc = orbitops::crc32(packet.data(), packet.size() - 4);
    if (!require(encoded_crc == calculated_crc, "CRC mismatch")) {
        return 1;
    }

    std::cout << "packet size=" << packet.size() << " golden-vector=ok crc=ok\n";
    return 0;
}
