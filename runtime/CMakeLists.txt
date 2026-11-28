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
    src/knowledge.c)

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
set(MODELS ${CMAKE_CURRENT_SOURCE_DIR}/../models)
add_test(NAME console_logic COMMAND test_console_logic ${FIXTURES} ${MODELS})

add_test(NAME parity_tiny
         COMMAND utiny-host --model ${FIXTURES}/tiny.utny --golden ${FIXTURES}/tiny_golden.json)

# Knowledge images (specs/006 + 008): UTNY v2 with <fn>, UTKI v1 lookup and rendering (C vs.
# Python). Every committed image with a cases file (models/<topic>.utki + <topic>_cases.tsv) is
# tested, so a new topic needs no change here (specs/008 SC-004).
add_executable(test_knowledge tests/test_knowledge.c host/json.c)
target_include_directories(test_knowledge PRIVATE host)
target_link_libraries(test_knowledge PRIVATE utiny)
add_test(NAME knowledge_mini
         COMMAND test_knowledge ${FIXTURES}/kb_mini.utki ${FIXTURES}/kb_mini_cases.tsv)
file(GLOB KB_CASES ${MODELS}/*_cases.tsv)
foreach(cases ${KB_CASES})
    get_filename_component(topic ${cases} NAME)
    string(REPLACE "_cases.tsv" "" topic ${topic})
    add_test(NAME knowledge_${topic}
             COMMAND test_knowledge ${MODELS}/${topic}.utki ${cases})
    add_test(NAME kb_cases_${topic}
             COMMAND utiny-host --facts ${MODELS}/${topic}.utki --kb-cases ${cases})
endforeach()
add_test(NAME parity_tiny_v2
         COMMAND utiny-host --model ${FIXTURES}/tiny_v2.utny --facts ${MODELS}/chemie.utki
                 --golden ${FIXTURES}/tiny_v2_golden.json)

# Word-access check (specs/005-nodemcu-port/contracts/runtime-image-access.md): a second build in
# which every ut_ld32 traps on an unaligned address, plus a lint against byte reads of the image.
option(UT_IMAGE_ACCESS_CHECK "Also build and test the runtime with alignment-checked image reads" ON)
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
    add_executable(test_knowledge_checked tests/test_knowledge.c host/json.c)
    target_include_directories(test_knowledge_checked PRIVATE host)
    target_link_libraries(test_knowledge_checked PRIVATE utiny_checked)
    add_test(NAME knowledge_mini_checked
             COMMAND test_knowledge_checked ${FIXTURES}/kb_mini.utki ${FIXTURES}/kb_mini_cases.tsv)
    foreach(cases ${KB_CASES})
        get_filename_component(topic ${cases} NAME)
        string(REPLACE "_cases.tsv" "" topic ${topic})
        add_test(NAME knowledge_${topic}_checked
                 COMMAND test_knowledge_checked ${MODELS}/${topic}.utki ${cases})
    endforeach()
    add_test(NAME parity_tiny_v2_checked
             COMMAND utiny-host-checked --model ${FIXTURES}/tiny_v2.utny
                     --facts ${MODELS}/chemie.utki --golden ${FIXTURES}/tiny_v2_golden.json)
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
