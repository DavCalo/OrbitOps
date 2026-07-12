#include "orbitops/telemetry.hpp"

#include <arpa/inet.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>

#ifndef ORBITOPS_VERSION
#define ORBITOPS_VERSION "development"
#endif

namespace {

std::atomic_bool g_running{true};

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

void handle_signal(int) {
    g_running.store(false);
}

class UdpSocket {
public:
    UdpSocket() : fd_(::socket(AF_INET, SOCK_DGRAM, 0)) {
        if (fd_ < 0) {
            throw std::runtime_error("could not create UDP socket");
        }
    }

    ~UdpSocket() {
        if (fd_ >= 0) {
            ::close(fd_);
        }
    }

    UdpSocket(const UdpSocket&) = delete;
    UdpSocket& operator=(const UdpSocket&) = delete;

    [[nodiscard]] int get() const noexcept {
        return fd_;
    }

private:
    int fd_;
};

struct Options {
    std::string host = "127.0.0.1";
    int port = 9000;
    int interval_ms = 1000;
    int packets = 0; // 0 means unlimited
    int drop_every = 0;
    std::string scenario = "nominal";
};

int parse_int(const char* value, const char* name) {
    try {
        std::size_t consumed = 0;
        const std::string text(value);
        const int parsed = std::stoi(text, &consumed);
        if (consumed != text.size()) {
            throw std::runtime_error("trailing characters");
        }
        return parsed;
    } catch (const std::exception&) {
        throw std::runtime_error(std::string("invalid integer for ") + name);
    }
}

Options parse_options(int argc, char** argv) {
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string arg = argv[index];
        auto require_value = [&](const char* name) -> const char* {
            if (index + 1 >= argc) {
                throw std::runtime_error(std::string("missing value for ") + name);
            }
            return argv[++index];
        };

        if (arg == "--host") {
            options.host = require_value("--host");
        } else if (arg == "--port") {
            options.port = parse_int(require_value("--port"), "--port");
        } else if (arg == "--interval-ms") {
            options.interval_ms = parse_int(require_value("--interval-ms"), "--interval-ms");
        } else if (arg == "--packets") {
            options.packets = parse_int(require_value("--packets"), "--packets");
        } else if (arg == "--drop-every") {
            options.drop_every = parse_int(require_value("--drop-every"), "--drop-every");
        } else if (arg == "--scenario") {
            options.scenario = require_value("--scenario");
        } else if (arg == "--version") {
            std::cout << "orbitops_sim " << ORBITOPS_VERSION << '\n';
            std::exit(0);
        } else if (arg == "--help") {
            std::cout
                << "OrbitOps on-board simulator\n\n"
                << "Usage: orbitops_sim [options]\n\n"
                << "Options:\n"
                << "  --host IPv4\n"
                << "  --port PORT\n"
                << "  --interval-ms N\n"
                << "  --packets N        0 means unlimited\n"
                << "  --drop-every N     skip every Nth transmission\n"
                << "  --scenario nominal|thermal|power\n"
                << "  --version\n"
                << "  --help\n";
            std::exit(0);
        } else {
            throw std::runtime_error("unknown argument: " + arg);
        }
    }

    if (options.port <= 0 || options.port > 65535) {
        throw std::runtime_error("port must be between 1 and 65535");
    }
    if (options.interval_ms <= 0) {
        throw std::runtime_error("interval must be positive");
    }
    if (options.packets < 0 || options.drop_every < 0) {
        throw std::runtime_error("packet counts cannot be negative");
    }
    if (options.scenario != "nominal" && options.scenario != "thermal" &&
        options.scenario != "power") {
        throw std::runtime_error("scenario must be nominal, thermal, or power");
    }
    return options;
}

std::uint64_t now_ms() {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count());
}

orbitops::Telemetry make_telemetry(std::uint32_t sequence, const Options& options) {
    const double phase = static_cast<double>(sequence) / kScenarioPhaseDivisor;
    double temperature =
        kNominalTemperatureC + kTemperatureOscillationC * std::sin(phase);
    double battery =
        kNominalBatteryV -
        kNominalBatteryDrainPerPacketV * static_cast<double>(sequence);

    if (options.scenario == "thermal") {
        temperature += kThermalRisePerPacketC * static_cast<double>(sequence);
    } else if (options.scenario == "power") {
        battery -= kPowerDrainPerPacketV * static_cast<double>(sequence);
    }

    orbitops::SpacecraftMode mode = orbitops::SpacecraftMode::Nominal;
    if (temperature >= kSafeTemperatureC || battery <= kSafeBatteryV) {
        mode = orbitops::SpacecraftMode::Safe;
    } else if (sequence < kBootPacketCount) {
        mode = orbitops::SpacecraftMode::Boot;
    }

    orbitops::Telemetry telemetry;
    telemetry.sequence = sequence;
    telemetry.timestamp_ms = now_ms();
    telemetry.mode = mode;
    telemetry.battery_mv = static_cast<std::uint16_t>(
        std::round(std::max(0.0, battery) * kMillivoltsPerVolt));
    telemetry.bus_current_ma = static_cast<std::uint16_t>(std::round(
        kNominalBusCurrentMa + kBusCurrentOscillationMa * std::sin(phase * 0.7)));
    telemetry.temperature_centi_c = static_cast<std::int16_t>(
        std::round(temperature * kCentiUnitsPerUnit));
    telemetry.roll_centi_deg = static_cast<std::int16_t>(
        std::round(kRollAmplitudeCentiDeg * std::sin(phase * 0.5)));
    telemetry.pitch_centi_deg = static_cast<std::int16_t>(
        std::round(kPitchAmplitudeCentiDeg * std::cos(phase * 0.4)));
    telemetry.yaw_centi_deg = static_cast<std::int16_t>(
        std::fmod(
            static_cast<double>(sequence) * kYawStepCentiDeg + kHalfTurnCentiDeg,
            kFullTurnCentiDeg) -
        kHalfTurnCentiDeg);
    return telemetry;
}

const char* mode_name(orbitops::SpacecraftMode mode) {
    switch (mode) {
        case orbitops::SpacecraftMode::Boot:
            return "BOOT";
        case orbitops::SpacecraftMode::Nominal:
            return "NOMINAL";
        case orbitops::SpacecraftMode::Safe:
            return "SAFE";
    }
    return "UNKNOWN";
}

} // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        std::signal(SIGINT, handle_signal);
        std::signal(SIGTERM, handle_signal);

        const UdpSocket socket;
        sockaddr_in destination{};
        destination.sin_family = AF_INET;
        destination.sin_port = htons(static_cast<std::uint16_t>(options.port));
        if (::inet_pton(AF_INET, options.host.c_str(), &destination.sin_addr) != 1) {
            throw std::runtime_error("invalid IPv4 address: " + options.host);
        }

        std::cout << "OrbitOps simulator " << ORBITOPS_VERSION << " -> " << options.host << ':'
                  << options.port << " scenario=" << options.scenario << '\n';

        std::uint32_t sequence = 0;
        while (g_running.load() &&
               (options.packets == 0 || sequence < static_cast<std::uint32_t>(options.packets))) {
            const auto telemetry = make_telemetry(sequence, options);
            const bool intentionally_dropped = options.drop_every > 0 && sequence > 0 &&
                                               sequence % static_cast<std::uint32_t>(options.drop_every) == 0;

            if (intentionally_dropped) {
                std::cout << "DROP seq=" << sequence << " (fault injection)\n";
            } else {
                const auto packet = orbitops::encode(telemetry);
                const auto sent = ::sendto(
                    socket.get(),
                    packet.data(),
                    packet.size(),
                    0,
                    reinterpret_cast<const sockaddr*>(&destination),
                    sizeof(destination));
                if (sent != static_cast<ssize_t>(packet.size())) {
                    throw std::runtime_error("failed to send complete UDP packet");
                }

                std::cout << std::fixed << std::setprecision(2)
                          << "TX seq=" << telemetry.sequence
                          << " mode=" << mode_name(telemetry.mode)
                          << " battery=" << telemetry.battery_mv / 1000.0 << "V"
                          << " temp=" << telemetry.temperature_centi_c / 100.0 << "C\n";
            }

            ++sequence;
            std::this_thread::sleep_for(std::chrono::milliseconds(options.interval_ms));
        }

        std::cout << "OrbitOps simulator stopped after " << sequence << " cycle(s).\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "error: " << exc.what() << '\n';
        return 1;
    }
}
