/*
 * UltraTiny firmware: thin ESP-IDF platform layer around the portable runtime.
 *
 * - Wi-Fi and Bluetooth are never initialized (FR-001); BT is compiled out in sdkconfig.
 * - The model is memory-mapped from the "model" flash partition and read in place.
 * - All inference memory is one static arena (constitution II: no heap at inference).
 * - On an invalid model the console enters HALT_ERROR: /hilfe and /info stay available,
 *   no panic and no reboot loop (User Story 3).
 * - Observability (specs/002-observability): stage profiling via esp_timer, /stats values
 *   from console_uart.c.
 */
#include <stdint.h>

#include "console_uart.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "model_partition.h"
#include "utiny.h"
#include "utiny_console.h"

#define UT_ARENA_MAX (96 * 1024) /* keep in sync with tools/budget_report.py FIRMWARE_ARENA */

static uint8_t arena[UT_ARENA_MAX] __attribute__((aligned(16)));
static ut_model model;
static ut_ctx ctx;
static ut_console console;

static void model_task(void *arg) {
    (void)arg;
    ut_console_io io;
    console_uart_init(&io);

    const void *data = NULL;
    size_t size = 0;
    ut_status st = UT_ERR_SIZE;
    if (model_partition_map(&data, &size) == 0) st = ut_model_open(&model, data, size);
    size_t need = st == UT_OK ? ut_arena_size(&model) : 0;
    if (st == UT_OK && need > sizeof arena) st = UT_ERR_ARENA;
    if (st == UT_OK) st = ut_ctx_init(&ctx, &model, arena, sizeof arena);
    if (st == UT_OK) ctx.clock_us = console_clock_us; /* profiling only reads the clock */

    ut_console_init(&console, st == UT_OK ? &ctx : NULL, st == UT_OK ? &model : NULL, need, &io,
                    st);
    console.arena_cap = sizeof arena;
    ut_console_banner(&console);

    for (;;) {
        ut_console_poll(&console);
        /* Yield while idle; while generating run flat out (task is pinned to core 1,
         * whose idle task is not watched by the task watchdog). */
        if (console.state != UT_ST_GENERATING) vTaskDelay(1);
    }
}

void app_main(void) {
    esp_log_level_set("*", ESP_LOG_WARN); /* keep the console clean */
    xTaskCreatePinnedToCore(model_task, "ultratiny", 8192, NULL, 5, NULL, 1);
}
