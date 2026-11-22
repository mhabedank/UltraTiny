# UltraTiny portable runtime.
# - Inside ESP-IDF (ESP_PLATFORM set): registers an IDF component named "runtime".
# - Otherwise: builds static lib `utiny`, host CLI `utiny-host` and CTest tests.

set(UT_SRCS
    src/crc32.c
    src/mathx.c
    src/model.c
    src/forward.c
    src/alphabet.c
    src/console.c
    src/facts.c)

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

# Hybrid chemistry teacher (specs/006): UTNY v2 with <fn>, fact table rendering (C vs. Python).
add_executable(test_facts tests/test_facts.c host/json.c)
target_include_directories(test_facts PRIVATE host)
target_link_libraries(test_facts PRIVATE utiny)
add_test(NAME facts COMMAND test_facts ${FIXTURES})
add_test(NAME parity_tiny_v2
         COMMAND utiny-host --model ${FIXTURES}/tiny_v2.utny --facts ${FIXTURES}/facts_small.utft
                 --golden ${FIXTURES}/tiny_v2_golden.json)

# Word-access check (specs/005-nodemcu-port/contracts/runtime-image-access.md): a second build in
# which every ut_ld32 traps on an unaligned address, plus a lint against byte reads of the image.
option(UT_IMAGE_ACCESS_CHECK "Also build and test the runtime with alignment-checked image reads" ON)
set(MODELS ${CMAKE_CURRENT_SOURCE_DIR}/../models)
if(UT_IMAGE_ACCESS_CHECK)
    add_library(utiny_checked STATIC ${UT_SRCS})
    target_include_directories(utiny_checked PUBLIC include)
    target_compile_definitions(utiny_checked PUBLIC UT_IMAGE_ACCESS_CHECK)
    target_link_libraries(utiny_checked PUBLIC m)

    add_executable(utiny-host-checked host/utiny_host.c host/json.c)
    target_include_directories(utiny-host-checked PRIVATE host)
    target_link_libraries(utiny-host-checked PRIVATE utiny_checked)

    add_executable(test_runtime_checked tests/test_runtime.c host/json.c)
    target_include_directories(test_runtime_checked PRIVATE host)
    target_link_libraries(test_runtime_checked PRIVATE utiny_checked)
    add_test(NAME runtime_checked COMMAND test_runtime_checked ${FIXTURES})
    add_executable(test_facts_checked tests/test_facts.c host/json.c)
    target_include_directories(test_facts_checked PRIVATE host)
    target_link_libraries(test_facts_checked PRIVATE utiny_checked)
    add_test(NAME facts_checked COMMAND test_facts_checked ${FIXTURES})
    add_test(NAME parity_tiny_v2_checked
             COMMAND utiny-host-checked --model ${FIXTURES}/tiny_v2.utny
                     --facts ${FIXTURES}/facts_small.utft --golden ${FIXTURES}/tiny_v2_golden.json)
    add_test(NAME parity_tiny_checked
             COMMAND utiny-host-checked --model ${FIXTURES}/tiny.utny
                     --golden ${FIXTURES}/tiny_golden.json)
    add_test(NAME parity_starter_checked
             COMMAND utiny-host-checked --model ${MODELS}/starter.utny
                     --golden ${MODELS}/starter_golden.json)
    add_test(NAME parity_nodemcu_checked
             COMMAND utiny-host-checked --model ${MODELS}/nodemcu.utny
                     --golden ${MODELS}/nodemcu_golden.json)
endif()

# NodeMCU PoC model (specs/005-nodemcu-port): host parity with the committed golden file.
add_test(NAME parity_nodemcu
         COMMAND utiny-host --model ${MODELS}/nodemcu.utny --golden ${MODELS}/nodemcu_golden.json)

add_test(NAME image_access_lint
         COMMAND sh ${CMAKE_CURRENT_SOURCE_DIR}/tests/image_access_lint.sh
                 ${CMAKE_CURRENT_SOURCE_DIR}/src)
