/**
 * USB HID Device Implementation
 *
 * Handles USB keyboard emulation using TinyUSB.
 */

#include "usb_hid.h"
#include "tusb.h"
#include "pico/stdlib.h"
#include <string.h>
#include <stdio.h>

// HID report state
static uint8_t _last_report[8] = {0};
static bool _report_pending = false;
static uint8_t _pending_report[8] = {0};

//--------------------------------------------------------------------
// TinyUSB Callbacks
//--------------------------------------------------------------------

// Invoked when device is mounted
void tud_mount_cb(void) {
    printf("[USB] Device mounted\n");
}

// Invoked when device is unmounted
void tud_umount_cb(void) {
    printf("[USB] Device unmounted\n");
}

// Invoked when usb bus is suspended
void tud_suspend_cb(bool remote_wakeup_en) {
    (void) remote_wakeup_en;
    printf("[USB] Suspended\n");
}

// Invoked when usb bus is resumed
void tud_resume_cb(void) {
    printf("[USB] Resumed\n");
}

// Invoked when received GET_REPORT control request
uint16_t tud_hid_get_report_cb(uint8_t instance, uint8_t report_id,
                                hid_report_type_t report_type,
                                uint8_t* buffer, uint16_t reqlen) {
    (void) instance;
    (void) report_id;
    (void) report_type;
    (void) reqlen;

    // Return the last sent report
    memcpy(buffer, _last_report, 8);
    return 8;
}

// Invoked when received SET_REPORT control request or
// received data on OUT endpoint (Report ID = 0, Type = 0)
void tud_hid_set_report_cb(uint8_t instance, uint8_t report_id,
                           hid_report_type_t report_type,
                           uint8_t const* buffer, uint16_t bufsize) {
    (void) instance;
    (void) report_id;
    (void) report_type;
    (void) buffer;
    (void) bufsize;

    // This is typically for LED status (Caps Lock, Num Lock, etc.)
    // We can ignore for now
    if (report_type == HID_REPORT_TYPE_OUTPUT && bufsize >= 1) {
        uint8_t leds = buffer[0];
        // LED bits: Num Lock = 0, Caps Lock = 1, Scroll Lock = 2
        printf("[USB] LED status: 0x%02x\n", leds);
    }
}

//--------------------------------------------------------------------
// Public API
//--------------------------------------------------------------------

void usb_hid_init(void) {
    // TinyUSB is initialized by the SDK when we link to tinyusb_device
    // Just make sure it's started
    tusb_init();
    printf("[USB] HID initialized\n");
}

void usb_hid_task(void) {
    // Process USB events
    tud_task();

    // Send pending report if any
    if (_report_pending && tud_hid_ready()) {
        if (tud_hid_keyboard_report(0, _pending_report[0], &_pending_report[2])) {
            memcpy(_last_report, _pending_report, 8);
            _report_pending = false;
        }
    }
}

bool usb_hid_send_keyboard_report(uint8_t modifier, const uint8_t keycodes[6]) {
    if (!tud_hid_ready()) {
        // Queue the report for later
        _pending_report[0] = modifier;
        _pending_report[1] = 0;  // reserved
        memcpy(&_pending_report[2], keycodes, 6);
        _report_pending = true;
        return false;
    }

    bool success = tud_hid_keyboard_report(0, modifier, keycodes);
    if (success) {
        _last_report[0] = modifier;
        _last_report[1] = 0;
        memcpy(&_last_report[2], keycodes, 6);
    }
    return success;
}

bool usb_hid_send_report(const uint8_t report[8]) {
    return usb_hid_send_keyboard_report(report[0], &report[2]);
}

bool usb_hid_ready(void) {
    return tud_hid_ready();
}

bool usb_hid_mounted(void) {
    return tud_mounted();
}
