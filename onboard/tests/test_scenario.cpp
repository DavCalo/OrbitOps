#include "orbitops/scenario.hpp"

#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

bool require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "scenario test failed: " << message << '\n';
        return false;
    }
    return true;
}

} // namespace

int main() {
    constexpr std::uint64_t kTimestampMs = 1726000000123ULL;

    const auto boot = orbitops::make_scenario_telemetry(
        0, kTimestampMs, orbitops::Scenario::Nominal);
    if (!require(boot.mode == orbitops::SpacecraftMode::Boot, "sequence 0 should be BOOT") ||
        !require(boot.timestamp_ms == kTimestampMs, "timestamp should be preserved") ||
        !require(boot.battery_mv == 8100, "nominal sequence 0 battery mismatch") ||
        !require(boot.bus_current_ma == 420, "nominal sequence 0 current mismatch") ||
        !require(boot.temperature_centi_c == 2400, "nominal sequence 0 temperature mismatch") ||
        !require(boot.roll_centi_deg == 0, "nominal sequence 0 roll mismatch") ||
        !require(boot.pitch_centi_deg == 320, "nominal sequence 0 pitch mismatch") ||
        !require(boot.yaw_centi_deg == 0, "nominal sequence 0 yaw mismatch")) {
        return 1;
    }

    const auto nominal = orbitops::make_scenario_telemetry(
        3, kTimestampMs, orbitops::Scenario::Nominal);
    if (!require(
            nominal.mode == orbitops::SpacecraftMode::Nominal,
            "sequence 3 should be NOMINAL")) {
        return 1;
    }

    const auto thermal_before_safe = orbitops::make_scenario_telemetry(
        50, kTimestampMs, orbitops::Scenario::Thermal);
    const auto thermal_safe = orbitops::make_scenario_telemetry(
        51, kTimestampMs, orbitops::Scenario::Thermal);
    if (!require(
            thermal_before_safe.temperature_centi_c == 5994,
            "thermal sequence 50 temperature mismatch") ||
        !require(
            thermal_before_safe.mode == orbitops::SpacecraftMode::Nominal,
            "thermal sequence 50 should be NOMINAL") ||
        !require(
            thermal_safe.temperature_centi_c == 6089,
            "thermal sequence 51 temperature mismatch") ||
        !require(
            thermal_safe.mode == orbitops::SpacecraftMode::Safe,
            "thermal sequence 51 should be SAFE")) {
        return 1;
    }

    const auto power_sample = orbitops::make_scenario_telemetry(
        28, kTimestampMs, orbitops::Scenario::Power);
    const auto power_before_safe = orbitops::make_scenario_telemetry(
        29, kTimestampMs, orbitops::Scenario::Power);
    const auto power_safe = orbitops::make_scenario_telemetry(
        30, kTimestampMs, orbitops::Scenario::Power);
    if (!require(power_sample.battery_mv == 7050, "power sequence 28 battery mismatch") ||
        !require(
            power_before_safe.mode == orbitops::SpacecraftMode::Nominal,
            "power sequence 29 should be NOMINAL") ||
        !require(power_safe.battery_mv == 6975, "power sequence 30 battery mismatch") ||
        !require(
            power_safe.mode == orbitops::SpacecraftMode::Safe,
            "power sequence 30 should be SAFE")) {
        return 1;
    }

    const auto last_thermal = orbitops::make_scenario_telemetry(
        419, kTimestampMs, orbitops::Scenario::Thermal);
    if (!require(
            last_thermal.temperature_centi_c == 32723,
            "thermal sequence 419 should remain representable")) {
        return 1;
    }

    bool boundary_rejected = false;
    try {
        (void)orbitops::make_scenario_telemetry(
            420, kTimestampMs, orbitops::Scenario::Thermal);
    } catch (const std::overflow_error&) {
        boundary_rejected = true;
    }
    if (!require(boundary_rejected, "thermal sequence 420 should fail closed")) {
        return 1;
    }

    bool long_run_rejected = false;
    try {
        (void)orbitops::make_scenario_telemetry(
            std::numeric_limits<std::uint32_t>::max(),
            kTimestampMs,
            orbitops::Scenario::Thermal);
    } catch (const std::overflow_error&) {
        long_run_rejected = true;
    }
    if (!require(long_run_rejected, "long thermal run should fail closed")) {
        return 1;
    }

    const auto long_power = orbitops::make_scenario_telemetry(
        std::numeric_limits<std::uint32_t>::max(),
        kTimestampMs,
        orbitops::Scenario::Power);
    if (!require(long_power.battery_mv == 0, "long power run battery should floor at zero") ||
        !require(
            long_power.mode == orbitops::SpacecraftMode::Safe,
            "long power run should remain SAFE")) {
        return 1;
    }

    std::cout << "scenario generation curves=ok modes=ok boundaries=ok long-run=ok\n";
    return 0;
}
