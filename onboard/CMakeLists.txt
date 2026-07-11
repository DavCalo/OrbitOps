cmake_minimum_required(VERSION 3.16)
project(orbitops_sim LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(orbitops_sim
    src/main.cpp
)

target_include_directories(orbitops_sim PRIVATE include)

if(MSVC)
    target_compile_options(orbitops_sim PRIVATE /W4)
else()
    target_compile_options(orbitops_sim PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()
add_executable(orbitops_packet_test tests/test_packet.cpp)
target_include_directories(orbitops_packet_test PRIVATE include)
add_test(NAME packet_encoding COMMAND orbitops_packet_test)
