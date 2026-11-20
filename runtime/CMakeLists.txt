# UltraTiny portable runtime.
# - Inside ESP-IDF (ESP_PLATFORM set): registers an IDF component named "runtime".
# - Otherwise: builds static lib `utiny`, host CLI `utiny-host` and CTest tests.

set(UT_SRCS
    src/crc32.c
    src/mathx.c
    src/model.c
    src/forward.c
    src/alphabet.c
    src/console.c)

# Deterministic float math: no FMA contraction, no fast-math, float literals.
set(UT_FLAGS -ffp-contract=off -fno-fast-math -fsingle-precision-constant)

if(ESP_PLATFORM)
    idf_component_register(SRCS ${UT_SRCS} INCLUDE_DIRS include)
    target_compile_options(${COMPONENT_LIB} PRIVATE ${UT_FLAGS})
    return()
endif()

cmake_minimum_required(VERSION 3.20)
project(utiny C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_compile_options(-Wall -Wextra -Werror ${UT_FLAGS})

add_library(utiny STATIC ${UT_SRCS})
target_include_directories(utiny PUBLIC include)
target_link_libraries(utiny PUBLIC m)

add_executable(utiny-host host/utiny_host.c host/json.c)
target_include_directories(utiny-host PRIVATE host)
target_link_libraries(utiny-host PRIVATE utiny)

enable_testing()
set(FIXTURES ${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures)

add_executable(test_runtime tests/test_runtime.c host/json.c)
target_include_directories(test_runtime PRIVATE host)
target_link_libraries(test_runtime PRIVATE utiny)
add_test(NAME runtime COMMAND test_runtime ${FIXTURES})

add_executable(test_console_logic tests/test_console_logic.c)
target_link_libraries(test_console_logic PRIVATE utiny)
add_test(NAME console_logic COMMAND test_console_logic ${FIXTURES})

add_test(NAME parity_tiny
         COMMAND utiny-host --model ${FIXTURES}/tiny.utny --golden ${FIXTURES}/tiny_golden.json)
