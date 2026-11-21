#pragma once

#include "utiny_console.h"

/* Installs the UART0 driver and fills `io` with non-blocking UART callbacks. */
void console_uart_init(ut_console_io *io);

/* Microsecond clock for the runtime's stage profiling (ut_ctx.clock_us). */
uint32_t console_clock_us(void);
