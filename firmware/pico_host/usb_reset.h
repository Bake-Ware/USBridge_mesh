/**
 * USB CDC Remote Reset Handler
 */

#ifndef USB_RESET_H
#define USB_RESET_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Check for reset command from CDC serial port
 * Call this regularly from the main loop or USB task
 */
void usb_reset_task(void);

#ifdef __cplusplus
}
#endif

#endif // USB_RESET_H
