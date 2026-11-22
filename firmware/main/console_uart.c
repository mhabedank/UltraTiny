/* UART0 backend for the platform-independent console (115200 8N1, UTF-8) plus the platform
 * values for /stats (specs/002-observability). */
#include "console_uart.h"

#include "driver/uart.h"
#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define CONSOLE_UART UART_NUM_0

static int uart_read(void *user) {
    (void)user;
    uint8_t b;
    return uart_read_bytes(CONSOLE_UART, &b, 1, 0) == 1 ? b : -1; /* non-blocking */
}

static void uart_write(void *user, const char *buf, size_t n) {
    (void)user;
    uart_write_bytes(CONSOLE_UART, buf, n);
}

static uint32_t uart_millis(void *user) {
    (void)user;
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static uint32_t uart_micros(void *user) {
    (void)user;
    return (uint32_t)esp_timer_get_time();
}

static uint32_t free_heap(void *user) {
    (void)user;
    return esp_get_free_heap_size();
}

uint32_t console_clock_us(void) { return (uint32_t)esp_timer_get_time(); }

/* CPU load per core from the idle tasks' run-time counters (FreeRTOS run-time stats),
 * as the share of non-idle time since the previous call. */
static void cpu_load(int32_t load[2]) {
    static uint32_t prev_idle[2];
    static int64_t prev_t;
    int64_t t = esp_timer_get_time();
    uint32_t wall = (uint32_t)(t - prev_t);
    for (int core = 0; core < 2; core++) {
        load[core] = -1;
#if CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS && !CONFIG_FREERTOS_UNICORE
        TaskHandle_t idle = xTaskGetIdleTaskHandleForCore(core);
        TaskStatus_t ts;
        vTaskGetInfo(idle, &ts, pdFALSE, eReady); /* no stack scan, state given */
        uint32_t now_idle = (uint32_t)ts.ulRunTimeCounter;
        uint32_t d_idle = now_idle - prev_idle[core];
        prev_idle[core] = now_idle;
        if (prev_t != 0 && wall > 0) {
            int32_t l = 100 - (int32_t)((uint64_t)d_idle * 100u / wall);
            load[core] = l < 0 ? 0 : (l > 100 ? 100 : l);
        }
#endif
    }
    prev_t = t;
}

static void sys_stats(void *user, ut_sys_stats *s) {
    (void)user;
    s->heap_free = (int32_t)esp_get_free_heap_size();
    s->heap_min = (int32_t)esp_get_minimum_free_heap_size();
    s->heap_largest = (int32_t)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    /* Called from the inference task itself; ESP-IDF reports the high-water mark in bytes. */
    s->stack_free = (int32_t)uxTaskGetStackHighWaterMark(NULL);
    cpu_load(s->cpu_load);
    s->uptime_ms = (int32_t)(esp_timer_get_time() / 1000);
    s->cpu_mhz = (int32_t)esp_rom_get_cpu_ticks_per_us();
}

void console_uart_init(ut_console_io *io) {
    uart_driver_install(CONSOLE_UART, 1024, 2048, 0, NULL, 0);
    io->read_byte = uart_read;
    io->write = uart_write;
    io->millis = uart_millis;
    io->free_heap = free_heap;
    io->user = NULL;
    io->micros = uart_micros;
    io->sys_stats = sys_stats;
    io->board = "ESP32";
    int32_t dummy[2];
    cpu_load(dummy); /* baseline for the first /stats */
}
