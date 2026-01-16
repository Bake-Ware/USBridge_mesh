/**
 * USB CDC Remote Reset Handler
 *
 * Allows remote rebooting into BOOTSEL mode via CDC serial command.
 * Send "BOOTSEL\n" over the serial port to trigger BOOTSEL mode.
 */

#include <string.h>
#include "tusb.h"
#include "pico/bootrom.h"
#include "hardware/watchdog.h"

#define RESET_CMD "BOOTSEL\n"
#define RESET_CMD_LEN 8

static char cmd_buffer[16];
static int cmd_pos = 0;

/**
 * Check for reset command from CDC serial port
 * Call this regularly from the main loop or USB task
 */
void usb_reset_task(void) {
    if (!tud_cdc_connected()) {
        cmd_pos = 0;
        return;
    }

    // Read available characters
    while (tud_cdc_available()) {
        char c = tud_cdc_read_char();

        // Add to buffer
        if (cmd_pos < sizeof(cmd_buffer) - 1) {
            cmd_buffer[cmd_pos++] = c;
            cmd_buffer[cmd_pos] = '\0';
        } else {
            // Buffer overflow, reset
            cmd_pos = 0;
        }

        // Check for newline
        if (c == '\n') {
            // Check if it matches our reset command
            if (cmd_pos >= RESET_CMD_LEN &&
                memcmp(cmd_buffer + cmd_pos - RESET_CMD_LEN, RESET_CMD, RESET_CMD_LEN) == 0) {

                // Send acknowledgment
                const char *msg = "\n\n*** Rebooting to BOOTSEL mode... ***\n\n";
                tud_cdc_write_str(msg);
                tud_cdc_write_flush();

                // Wait a moment for message to send
                sleep_ms(100);

                // Reset into BOOTSEL mode
                reset_usb_boot(0, 0);

                // Never reached
                while (1);
            }

            // Reset buffer after newline
            cmd_pos = 0;
        }
    }
}
