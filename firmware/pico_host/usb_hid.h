/**
 * USB HID Device Interface
 *
 * Provides USB keyboard emulation for injecting HID reports to the host PC.
 */

#ifndef USB_HID_H
#define USB_HID_H

#include <stdint.h>
#include <stdbool.h>

/**
 * Initialize USB HID device
 *
 * Must be called before any other USB HID functions.
 */
void usb_hid_init(void);

/**
 * Process USB HID tasks
 *
 * Should be called periodically from the main loop.
 */
void usb_hid_task(void);

/**
 * Send a keyboard HID report
 *
 * @param modifier  Modifier keys bitmask (Ctrl, Shift, Alt, GUI)
 * @param keycodes  Array of 6 key codes (0 = no key)
 * @return true if report was sent successfully
 */
bool usb_hid_send_keyboard_report(uint8_t modifier, const uint8_t keycodes[6]);

/**
 * Send a raw 8-byte HID report
 *
 * @param report  8-byte keyboard report (modifier, reserved, 6 keycodes)
 * @return true if report was sent successfully
 */
bool usb_hid_send_report(const uint8_t report[8]);

/**
 * Check if USB HID is ready to send reports
 *
 * @return true if USB is connected and ready
 */
bool usb_hid_ready(void);

/**
 * Check if USB is mounted (connected to host)
 *
 * @return true if USB is mounted
 */
bool usb_hid_mounted(void);

#endif // USB_HID_H
