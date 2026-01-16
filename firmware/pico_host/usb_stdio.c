/**
 * USB CDC stdio support
 * Provides printf output over USB CDC interface
 */

#include <stdio.h>
#include <string.h>
#include "tusb.h"
#include "pico/time.h"

// Newlib I/O functions for CDC
int _write(int fd, const char *buf, int count) {
    if (fd != 1 && fd != 2) {  // stdout or stderr
        return -1;
    }

    // Wait for CDC to be ready (with timeout)
    absolute_time_t timeout = make_timeout_time_ms(100);
    while (!tud_cdc_connected() && !time_reached(timeout)) {
        tud_task();
    }

    if (!tud_cdc_connected()) {
        return count;  // Pretend we wrote it
    }

    int written = 0;
    while (written < count) {
        int n = tud_cdc_write(buf + written, count - written);
        if (n > 0) {
            written += n;
            tud_cdc_write_flush();
        } else {
            tud_task();
        }
    }

    return written;
}

int _read(int fd, char *buf, int count) {
    if (fd != 0) {  // stdin only
        return -1;
    }

    if (!tud_cdc_connected() || !tud_cdc_available()) {
        return 0;
    }

    return tud_cdc_read(buf, count);
}
