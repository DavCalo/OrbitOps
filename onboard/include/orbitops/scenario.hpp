#pragma once

#include "orbitops/telemetry.hpp"

#include <cstdint>

namespace orbitops {

enum class Scenario {
    Nominal,
    Thermal,
    Power,
};

Telemetry make_scenario_telemetry(
    std::uint32_t sequence,
    std::uint64_t timestamp_ms,
    Scenario scenario);

} // namespace orbitops
