/*
 * UltraTiny firmware for the NodeMCU (ESP8266): thin Arduino platform layer around the portable
 * runtime (specs/005-nodemcu-port, plan.md).
 *
 * - Wi-Fi is switched off at boot; the model runs fully offline (FR-001).
 * - The model is read in place from the memory-mapped model area (0x40258000). The ESP8266 only
 *   allows aligned 32-bit loads there; the runtime guarantees that (contracts/runtime-image-access.md).
 * - All inference memory is one static arena (constitution II: no heap at inference).
 * - An invalid or too large model puts the console into HALT_ERROR: no panic, no reboot loop.
 * - loop() performs one console step (at most one generated token) and returns, so the SDK and
 *   the watchdogs get the CPU between tokens (research.md R8).
 * - Hybrid models (UTNY v2, specs/006-hybrid-chemielehrer) answer factual questions from the fact
 *   table at flash 0x100000 (outside the mapped megabyte), read with ESP.flashRead. A missing or
 *   corrupt table only disables factual answers; model-written answers keep working (FR-013).
 */
#include <Arduino.h>
#include <ESP8266WiFi.h>

extern "C" {
#include "utiny.h"
#include "utiny_console.h"
#include "utiny_knowledge.h"
}

#include "layout.h"

static uint8_t arena[UT_ARENA_MAX] __attribute__((aligned(16)));
static ut_model model;
static ut_ctx ctx;
static ut_console console;
static ut_kb kb; /* knowledge image (specs/008 UTKI v1) */

/* Knowledge image reads: aligned offset, length and buffer, as ESP.flashRead requires. Yields every
 * 4 KB so the boot-time CRC over the whole table does not starve the watchdog. */
static uint32_t facts_bytes_read = 0;
static int facts_read(void *, uint32_t off, void *buf, uint32_t n) {
    if (off > UT_FACTS_AREA_SIZE || n > UT_FACTS_AREA_SIZE - off) return -1;
    if (!ESP.flashRead(UT_FACTS_FLASH_OFFSET + off, (uint32_t *)buf, n)) return -1;
    facts_bytes_read += n;
    if (facts_bytes_read >= 4096) {
        facts_bytes_read = 0;
        yield();
    }
    return 0;
}

/* At most one input byte per loop(): every typed character is fed to the model (~0.1 s), so a
 * pasted prompt processed in one go would starve the software watchdog (~3.2 s). The rest waits
 * in the UART RX buffer until the next loop() (research.md R8). */
static int bytes_this_loop = 0;
static int io_read(void *) {
    if (bytes_this_loop >= 1) return -1;
    int b = Serial.read(); /* -1 when nothing is available */
    if (b >= 0) bytes_this_loop++;
    return b;
}
static void io_write(void *, const char *buf, size_t n) { Serial.write((const uint8_t *)buf, n); }
static uint32_t io_millis(void *) { return millis(); }
static uint32_t io_micros(void *) { return micros(); }
static uint32_t io_free_heap(void *) { return ESP.getFreeHeap(); }
static uint32_t clock_us(void) { return micros(); }

/* /stats values (data-model.md "Device status"); unknown values stay -1. */
static void io_sys_stats(void *, ut_sys_stats *s) {
    uint32_t free_heap = 0, max_block = 0;
    uint8_t frag = 0;
    ESP.getHeapStats(&free_heap, &max_block, &frag);
    s->heap_free = (int32_t)free_heap;
    s->heap_largest = (int32_t)max_block;
    s->stack_free = (int32_t)ESP.getFreeContStack(); /* loop() stack, 4 KB in total */
    s->uptime_ms = (int32_t)millis();
    s->cpu_mhz = (int32_t)ESP.getCpuFreqMHz();
    s->cores = 1; /* single core; its load is not measured (shown as "?") */
}

void setup() {
    WiFi.mode(WIFI_OFF); /* radio off: no RAM for Wi-Fi buffers, fully offline */
    WiFi.forceSleepBegin();
    Serial.setRxBufferSize(512); /* holds a pasted prompt while it is fed char by char */
    Serial.begin(115200);
    delay(50);

    static ut_console_io io;
    io.read_byte = io_read;
    io.write = io_write;
    io.millis = io_millis;
    io.free_heap = io_free_heap;
    io.user = nullptr;
    io.micros = io_micros;
    io.sys_stats = io_sys_stats;
    io.board = "NodeMCU (ESP8266)";
    io.kb = &kb;
    /* Open the knowledge image before the console, so the console can compare the model's topic
     * with the image (specs/008 research R11) and print the "Wissen:" line in the banner. */
    ut_kb_open(&kb, facts_read, nullptr, UT_FACTS_AREA_SIZE);

    ut_status st = ut_model_open(&model, (const void *)UT_MODEL_ADDR, UT_MODEL_AREA_SIZE);
    size_t need = st == UT_OK ? ut_arena_size(&model) : 0;
    if (st == UT_OK && need > sizeof arena) st = UT_ERR_ARENA; /* model too big for this board */
    if (st == UT_OK) st = ut_ctx_init(&ctx, &model, arena, sizeof arena);
    if (st == UT_OK) ctx.clock_us = clock_us; /* profiling only reads the clock */

    ut_console_init(&console, st == UT_OK ? &ctx : nullptr, st == UT_OK ? &model : nullptr, need,
                    &io, st);
    console.arena_cap = sizeof arena;
    /* Reset reason first, so the banner still ends with the prompt (tools/devlib.py reset()). */
    Serial.printf("\r\nLetzter Reset: %s", ESP.getResetReason().c_str());
    ut_console_banner(&console);
}

void loop() {
    bytes_this_loop = 0;
    ut_console_poll(&console);
    yield();
}
