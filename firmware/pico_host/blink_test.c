/**
 * Simple blink test for Pico 2W
 *
 * Tests that the toolchain works and we can flash the device.
 * On Pico W/2W, the LED is controlled via the CYW43 WiFi chip.
 */

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

int main() {
    stdio_init_all();

    // Initialize the CYW43 chip (required for LED on Pico W/2W)
    if (cyw43_arch_init()) {
        printf("CYW43 init failed\n");
        return -1;
    }

    printf("USBridge Host - Blink Test\n");

    while (true) {
        // Turn LED on
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
        sleep_ms(250);

        // Turn LED off
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        sleep_ms(250);
    }

    return 0;
}
