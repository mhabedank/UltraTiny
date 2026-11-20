idf_component_register(SRCS "main.c" "model_partition.c" "console_uart.c"
                       INCLUDE_DIRS "."
                       REQUIRES runtime esp_partition driver esp_timer)
target_compile_options(${COMPONENT_LIB} PRIVATE -ffp-contract=off)
