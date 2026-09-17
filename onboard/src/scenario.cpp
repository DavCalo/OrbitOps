#include "orbitops/scenario.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

namespace orbitops {
namespace {

// Deterministic demonstration curves, not physical spacecraft models. Names
// include units because these values are compatibility-sensitive to demos.
constexpr double kScenarioPhaseDivisor = 8.0;
constexpr double kNominalTemperatureC = 24.0;
constexpr double kTemperatureOscillationC = 1.8;
constexpr double kNominalBatteryV = 8.1;
constexpr double kNominalBatteryDrainPerPacketV = 0.0025;
constexpr double kThermalRisePerPacketC = 0.72;
constexpr double kPowerDrainPerPacketV = 0.035;
constexpr double kSafeTemperatureC = 60.0;
constexpr double kSafeBatteryV = 7.0;
constexpr std::uint32_t kBootPacketCount = 3;
constexpr double kMillivoltsPerVolt = 1000.0;
constexpr double kCentiUnitsPerUnit = 100.0;
constexpr double kNominalBusCurrentMa = 420.0;
constexpr double kBusCurrentOscillationMa = 35.0;
constexpr double kRollAmplitudeCentiDeg = 450.0;
constexpr double kPitchAmplitudeCentiDeg = 320.0;
constexpr double kYawStepCentiDeg = 725.0;
constexpr double kHalfTurnCentiDeg = 18000.0;
constexpr double kFullTurnCentiDeg = 36000.0;

template <typename T>
T checked_fixed_width(double value, const char* field, std::uint32_t sequence) {
    const double lowest = static_cast<double>(std::numeric_limits<T>::lowest());
    const double highest = static_cast<double>(std::numeric_limits<T>::max());
    if (!std::isfinite(value) || value < lowest || value > highest) {
        throw std::overflow_error(
            std::string(field) + " value " + std::to_string(value) + " is outside [" +
            std::to_string(lowest) + ", " + std::to_string(highest) + "] at sequence " +
            std::to_string(sequence));
    }
    return static_cast<T>(value);
}

} // namespace

Telemetry make_scenario_telemetry(
    std::uint32_t sequence,
    std::uint64_t timestamp_ms,
    Scenario scenario) {
    const double phase = static_cast<double>(sequence) / kScenarioPhaseDivisor;
    double temperature =
        kNominalTemperatureC + kTemperatureOscillationC * std::sin(phase);
    double battery =
        kNominalBatteryV -
        kNominalBatteryDrainPerPacketV * static_cast<double>(sequence);

    if (scenario == Scenario::Thermal) {
        temperature += kThermalRisePerPacketC * static_cast<double>(sequence);
    } else if (scenario == Scenario::Power) {
        battery -= kPowerDrainPerPacketV * static_cast<double>(sequence);
    }

    SpacecraftMode mode = SpacecraftMode::Nominal;
    if (temperature >= kSafeTemperatureC || battery <= kSafeBatteryV) {
        mode = SpacecraftMode::Safe;
    } else if (sequence < kBootPacketCount) {
        mode = SpacecraftMode::Boot;
    }

    const double battery_mv =
        std::round(std::max(0.0, battery) * kMillivoltsPerVolt);
    const double bus_current_ma = std::round(
        kNominalBusCurrentMa + kBusCurrentOscillationMa * std::sin(phase * 0.7));
    const double temperature_centi_c =
        std::round(temperature * kCentiUnitsPerUnit);
    const double roll_centi_deg =
        std::round(kRollAmplitudeCentiDeg * std::sin(phase * 0.5));
    const double pitch_centi_deg =
        std::round(kPitchAmplitudeCentiDeg * std::cos(phase * 0.4));
    const double yaw_centi_deg =
        std::fmod(
            static_cast<double>(sequence) * kYawStepCentiDeg + kHalfTurnCentiDeg,
            kFullTurnCentiDeg) -
        kHalfTurnCentiDeg;

    Telemetry telemetry;
    telemetry.sequence = sequence;
    telemetry.timestamp_ms = timestamp_ms;
    telemetry.mode = mode;
    telemetry.battery_mv = checked_fixed_width<std::uint16_t>(battery_mv, "battery_mv", sequence);
    telemetry.bus_current_ma =
        checked_fixed_width<std::uint16_t>(bus_current_ma, "bus_current_ma", sequence);
    telemetry.temperature_centi_c = checked_fixed_width<std::int16_t>(
        temperature_centi_c, "temperature_centi_c", sequence);
    telemetry.roll_centi_deg =
        checked_fixed_width<std::int16_t>(roll_centi_deg, "roll_centi_deg", sequence);
    telemetry.pitch_centi_deg =
        checked_fixed_width<std::int16_t>(pitch_centi_deg, "pitch_centi_deg", sequence);
    telemetry.yaw_centi_deg =
        checked_fixed_width<std::int16_t>(yaw_centi_deg, "yaw_centi_deg", sequence);
    return telemetry;
}

} // namespace orbitops
