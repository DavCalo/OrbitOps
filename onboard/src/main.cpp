#include "orbitops/telemetry.hpp"

#include <arpa/inet.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>

namespace {

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
        return std::stoi(value);
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
        } else if (arg == "--help") {
            std::cout
                << "OrbitOps on-board simulator\n\n"
                << "Options:\n"
                << "  --host HOST\n"
                << "  --port PORT\n"
                << "  --interval-ms N\n"
                << "  --packets N        0 means unlimited\n"
                << "  --drop-every N     skip every Nth transmission\n"
                << "  --scenario nominal|thermal|power\n";
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
    if (options.scenario != "nominal" && options.scenario != "thermal" && options.scenario != "power") {
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
    const double phase = static_cast<double>(sequence) / 8.0;
    double temperature = 24.0 + 1.8 * std::sin(phase);
    double battery = 8.1 - 0.0025 * sequence;

    if (options.scenario == "thermal") {
        temperature += 0.72 * sequence;
    } else if (options.scenario == "power") {
        battery -= 0.035 * sequence;
    }

    orbitops::SpacecraftMode mode = orbitops::SpacecraftMode::Nominal;
    if (temperature >= 60.0 || battery <= 7.0) {
        mode = orbitops::SpacecraftMode::Safe;
    } else if (sequence < 3) {
        mode = orbitops::SpacecraftMode::Boot;
    }

    orbitops::Telemetry telemetry;
    telemetry.sequence = sequence;
    telemetry.timestamp_ms = now_ms();
    telemetry.mode = mode;
    telemetry.battery_mv = static_cast<std::uint16_t>(std::max(0.0, battery) * 1000.0);
    telemetry.bus_current_ma = static_cast<std::uint16_t>(420.0 + 35.0 * std::sin(phase * 0.7));
    telemetry.temperature_centi_c = static_cast<std::int16_t>(temperature * 100.0);
    telemetry.roll_centi_deg = static_cast<std::int16_t>(450.0 * std::sin(phase * 0.5));
    telemetry.pitch_centi_deg = static_cast<std::int16_t>(320.0 * std::cos(phase * 0.4));
    telemetry.yaw_centi_deg = static_cast<std::int16_t>(
        std::fmod(sequence * 725.0 + 18000.0, 36000.0) - 18000.0);
    return telemetry;
}

const char* mode_name(orbitops::SpacecraftMode mode) {
    switch (mode) {
        case orbitops::SpacecraftMode::Boot: return "BOOT";
        case orbitops::SpacecraftMode::Nominal: return "NOMINAL";
        case orbitops::SpacecraftMode::Safe: return "SAFE";
    }
    return "UNKNOWN";
}

} // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        const int socket_fd = ::socket(AF_INET, SOCK_DGRAM, 0);
        if (socket_fd < 0) {
            throw std::runtime_error("could not create UDP socket");
        }

        sockaddr_in destination{};
        destination.sin_family = AF_INET;
        destination.sin_port = htons(static_cast<std::uint16_t>(options.port));
        if (::inet_pton(AF_INET, options.host.c_str(), &destination.sin_addr) != 1) {
            ::close(socket_fd);
            throw std::runtime_error("invalid IPv4 address: " + options.host);
        }

        std::cout << "OrbitOps simulator -> " << options.host << ':' << options.port
                  << " scenario=" << options.scenario << '\n';

        std::uint32_t sequence = 0;
        while (options.packets == 0 || static_cast<int>(sequence) < options.packets) {
            const auto telemetry = make_telemetry(sequence, options);
            const bool intentionally_dropped =
                options.drop_every > 0 && sequence > 0 && sequence % options.drop_every == 0;

            if (intentionally_dropped) {
                std::cout << "DROP seq=" << sequence << " (fault injection)\n";
            } else {
                const auto packet = orbitops::encode(telemetry);
                const auto sent = ::sendto(
                    socket_fd,
                    packet.data(),
                    packet.size(),
                    0,
                    reinterpret_cast<const sockaddr*>(&destination),
                    sizeof(destination));
                if (sent != static_cast<ssize_t>(packet.size())) {
                    ::close(socket_fd);
                    throw std::runtime_error("failed to send complete UDP packet");
                }

                std::cout << "TX seq=" << telemetry.sequence
                          << " mode=" << mode_name(telemetry.mode)
                          << " battery=" << telemetry.battery_mv / 1000.0 << "V"
                          << " temp=" << telemetry.temperature_centi_c / 100.0 << "C\n";
            }

            ++sequence;
            std::this_thread::sleep_for(std::chrono::milliseconds(options.interval_ms));
        }

        ::close(socket_fd);
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "error: " << exc.what() << '\n';
        return 1;
    }
}
