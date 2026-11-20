#pragma once

#include "utiny_console.h"

/* Installs the UART0 driver and fills `io` with non-blocking UART callbacks. */
void console_uart_init(ut_console_io *io);
