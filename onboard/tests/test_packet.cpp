#include "orbitops/telemetry.hpp"

#include <cassert>
#include <cstdint>
#include <iostream>

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
    assert(packet.size() == orbitops::kPacketSize);
    assert(packet[0] == 'O' && packet[1] == 'R' && packet[2] == 'B' && packet[3] == 'T');

    const std::uint32_t encoded_crc =
        (static_cast<std::uint32_t>(packet[packet.size() - 4]) << 24) |
        (static_cast<std::uint32_t>(packet[packet.size() - 3]) << 16) |
        (static_cast<std::uint32_t>(packet[packet.size() - 2]) << 8) |
        static_cast<std::uint32_t>(packet[packet.size() - 1]);
    const std::uint32_t calculated_crc = orbitops::crc32(packet.data(), packet.size() - 4);
    assert(encoded_crc == calculated_crc);

    std::cout << "packet size=" << packet.size() << " crc=ok\n";
    return 0;
}
