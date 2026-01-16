/**
 * USBridge Host - Main Entry Point
 */

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "btstack_run_loop.h"
#include "usb_hid.h"

// Declared in usbridge_host.c
int btstack_main(void);

int main() {
    // Initialize system (clocks, timers, etc)
    // This does NOT initialize USB since we disabled pico_enable_stdio_usb
    stdio_init_all();

    // Initialize CYW43 driver for BLE FIRST (before USB)
    if (cyw43_arch_init()) {
        // Failed - hang
        while (1) {
            tight_loop_contents();
        }
    }

    // Now initialize USB HID
    usb_hid_init();

    // Wait for USB enumeration
    sleep_ms(1500);

    // Blink LED 3 times to show we made it here
    for (int i = 0; i < 3; i++) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
        sleep_ms(200);
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        sleep_ms(200);
    }

    // Setup BTstack and start advertising
    btstack_main();

    // Run BTstack event loop
    btstack_run_loop_execute();

    return 0;
}
