/**
 * TinyUSB Configuration for USBridge Host
 *
 * Configures USB as a HID keyboard device.
 */

#ifndef _TUSB_CONFIG_H_
#define _TUSB_CONFIG_H_

#ifdef __cplusplus
extern "C" {
#endif

//--------------------------------------------------------------------
// COMMON CONFIGURATION
//--------------------------------------------------------------------

// Defined by board (pico)
#ifndef CFG_TUSB_MCU
#define CFG_TUSB_MCU OPT_MCU_RP2040
#endif

// RHPort number used for device is 0
#define BOARD_TUD_RHPORT 0

// RHPort mode - device mode on port 0
#define CFG_TUSB_RHPORT0_MODE OPT_MODE_DEVICE

// Device mode
#define CFG_TUD_ENABLED 1

// Full speed
#define CFG_TUD_MAX_SPEED OPT_MODE_FULL_SPEED

//--------------------------------------------------------------------
// DEVICE CONFIGURATION
//--------------------------------------------------------------------

// USB device endpoint 0 size
#define CFG_TUD_ENDPOINT0_SIZE 64

//--------------------------------------------------------------------
// CLASS CONFIGURATION
//--------------------------------------------------------------------

// HID - Enable keyboard
#define CFG_TUD_HID 1

// HID buffer size
#define CFG_TUD_HID_EP_BUFSIZE 16

// CDC - Enable for debug serial (composite device)
#define CFG_TUD_CDC 1
#define CFG_TUD_CDC_RX_BUFSIZE 256
#define CFG_TUD_CDC_TX_BUFSIZE 256

// Disable unused classes
#define CFG_TUD_MSC 0
#define CFG_TUD_MIDI 0
#define CFG_TUD_VENDOR 0

#ifdef __cplusplus
}
#endif

#endif /* _TUSB_CONFIG_H_ */
