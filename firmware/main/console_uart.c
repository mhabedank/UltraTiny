/* UART0 backend for the platform-independent console (115200 8N1, UTF-8). */
#include "console_uart.h"

#include "driver/uart.h"
#include "esp_system.h"
#include "esp_timer.h"

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

static uint32_t free_heap(void *user) {
    (void)user;
    return esp_get_free_heap_size();
}

void console_uart_init(ut_console_io *io) {
    uart_driver_install(CONSOLE_UART, 1024, 2048, 0, NULL, 0);
    io->read_byte = uart_read;
    io->write = uart_write;
    io->millis = uart_millis;
    io->free_heap = free_heap;
    io->user = NULL;
}
