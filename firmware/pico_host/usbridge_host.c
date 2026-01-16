/**
 * USBridge Host Firmware
 *
 * BLE Peripheral that receives HID reports from Terminal devices
 * and injects them to the connected PC via USB HID.
 *
 * Phase 2: BLE Advertising and GATT Service
 * Phase 3: USB HID Device (to be added)
 * Phase 4: BLE to USB forwarding (to be added)
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include "btstack.h"
#include "usbridge_host.h"  // Generated from .gatt file
#include "usb_hid.h"
#include "usb_reset.h"

// ============================================================================
// Configuration
// ============================================================================

#define DEVICE_NAME "USBridge-Host"

// USBridge Service UUID: 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
static const uint8_t usbridge_service_uuid[] = {
    0x9e, 0xca, 0xdc, 0x24, 0x0e, 0xe5, 0xa9, 0xe0,
    0x93, 0xf3, 0xa3, 0xb5, 0x01, 0x00, 0x40, 0x6e
};

// ============================================================================
// State
// ============================================================================

static btstack_packet_callback_registration_t hci_event_callback_registration;
static hci_con_handle_t connection_handle = HCI_CON_HANDLE_INVALID;
static bool connected = false;
static bool notifications_enabled = false;

// Status data
static uint8_t status_data[4] = {1, 100, 0, 0};  // connected, battery%, latency_ms (16-bit)

// Statistics
static uint32_t hid_reports_received = 0;

// ============================================================================
// Advertisement Data
// ============================================================================

// Advertisement data: Flags + Name + Service UUID
static uint8_t adv_data[] = {
    // Flags: General Discoverable, BR/EDR not supported
    0x02, BLUETOOTH_DATA_TYPE_FLAGS, 0x06,
    // Complete Local Name
    0x0e, BLUETOOTH_DATA_TYPE_COMPLETE_LOCAL_NAME,
    'U', 'S', 'B', 'r', 'i', 'd', 'g', 'e', '-', 'H', 'o', 's', 't',
    // Complete List of 128-bit Service UUIDs
    0x11, BLUETOOTH_DATA_TYPE_COMPLETE_LIST_OF_128_BIT_SERVICE_CLASS_UUIDS,
    0x9e, 0xca, 0xdc, 0x24, 0x0e, 0xe5, 0xa9, 0xe0,
    0x93, 0xf3, 0xa3, 0xb5, 0x01, 0x00, 0x40, 0x6e
};
static const uint8_t adv_data_len = sizeof(adv_data);

// Scan response data (optional, contains full name)
static uint8_t scan_resp_data[] = {
    0x0e, BLUETOOTH_DATA_TYPE_COMPLETE_LOCAL_NAME,
    'U', 'S', 'B', 'r', 'i', 'd', 'g', 'e', '-', 'H', 'o', 's', 't',
};
static const uint8_t scan_resp_data_len = sizeof(scan_resp_data);

// ============================================================================
// LED Status
// ============================================================================

static btstack_timer_source_t led_timer;
static btstack_timer_source_t usb_timer;
static bool led_state = false;

static void led_update(void) {
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, led_state ? 1 : 0);
}

static void led_timer_handler(btstack_timer_source_t *ts) {
    if (connected) {
        // Solid on when connected
        led_state = true;
    } else {
        // Slow blink when idle
        led_state = !led_state;
    }
    led_update();

    // Restart timer
    btstack_run_loop_set_timer(ts, connected ? 1000 : 500);
    btstack_run_loop_add_timer(ts);
}

// USB task timer - runs TinyUSB task periodically
static void usb_timer_handler(btstack_timer_source_t *ts) {
    // Process USB HID events
    usb_hid_task();

    // Check for remote BOOTSEL command
    usb_reset_task();

    // Run again in 1ms for responsive USB
    btstack_run_loop_set_timer(ts, 1);
    btstack_run_loop_add_timer(ts);
}

// ============================================================================
// HID Report Handling
// ============================================================================

static void handle_hid_report(const uint8_t *report, uint16_t len) {
    hid_reports_received++;

    // Print the report for debugging
    printf("[HID] Report #%lu: ", hid_reports_received);
    for (int i = 0; i < len && i < 8; i++) {
        printf("%02x ", report[i]);
    }

    // Forward to USB HID
    if (len >= 8) {
        bool sent = usb_hid_send_report(report);
        printf(" -> USB: %s\n", sent ? "OK" : "BUSY");
    } else {
        printf(" (invalid length)\n");
    }
}

// ============================================================================
// ATT Callbacks
// ============================================================================

// ATT Read Callback
static uint16_t att_read_callback(
    hci_con_handle_t con_handle,
    uint16_t att_handle,
    uint16_t offset,
    uint8_t *buffer,
    uint16_t buffer_size
) {
    UNUSED(con_handle);

    // Status characteristic read
    if (att_handle == ATT_CHARACTERISTIC_6E400003_B5A3_F393_E0A9_E50E24DCCA9E_01_VALUE_HANDLE) {
        return att_read_callback_handle_blob(status_data, sizeof(status_data), offset, buffer, buffer_size);
    }

    return 0;
}

// ATT Write Callback
static int att_write_callback(
    hci_con_handle_t con_handle,
    uint16_t att_handle,
    uint16_t transaction_mode,
    uint16_t offset,
    uint8_t *buffer,
    uint16_t buffer_size
) {
    UNUSED(transaction_mode);
    UNUSED(offset);

    // HID characteristic write
    if (att_handle == ATT_CHARACTERISTIC_6E400002_B5A3_F393_E0A9_E50E24DCCA9E_01_VALUE_HANDLE) {
        handle_hid_report(buffer, buffer_size);
        return 0;
    }

    // Status notification configuration
    if (att_handle == ATT_CHARACTERISTIC_6E400003_B5A3_F393_E0A9_E50E24DCCA9E_01_CLIENT_CONFIGURATION_HANDLE) {
        notifications_enabled = little_endian_read_16(buffer, 0) == GATT_CLIENT_CHARACTERISTICS_CONFIGURATION_NOTIFICATION;
        connection_handle = con_handle;
        printf("[BLE] Notifications %s\n", notifications_enabled ? "enabled" : "disabled");
        return 0;
    }

    return 0;
}

// ============================================================================
// HCI Event Handler
// ============================================================================

static void packet_handler(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    UNUSED(channel);
    UNUSED(size);

    if (packet_type != HCI_EVENT_PACKET) return;

    uint8_t event_type = hci_event_packet_get_type(packet);

    switch (event_type) {
        case BTSTACK_EVENT_STATE:
            if (btstack_event_state_get_state(packet) == HCI_STATE_WORKING) {
                bd_addr_t local_addr;
                gap_local_bd_addr(local_addr);
                printf("[BLE] BTstack up and running at %s\n", bd_addr_to_str(local_addr));
                printf("[BLE] Advertising as '%s'\n", DEVICE_NAME);
            }
            break;

        case HCI_EVENT_LE_META:
            switch (hci_event_le_meta_get_subevent_code(packet)) {
                case HCI_SUBEVENT_LE_CONNECTION_COMPLETE:
                    connection_handle = hci_subevent_le_connection_complete_get_connection_handle(packet);
                    connected = true;
                    printf("[BLE] Connected! Handle: %d\n", connection_handle);
                    break;
                default:
                    break;
            }
            break;

        case HCI_EVENT_DISCONNECTION_COMPLETE:
            printf("[BLE] Disconnected\n");
            connection_handle = HCI_CON_HANDLE_INVALID;
            connected = false;
            notifications_enabled = false;

            // Restart advertising
            gap_advertisements_enable(1);
            printf("[BLE] Advertising restarted\n");
            break;

        case ATT_EVENT_CAN_SEND_NOW:
            // Could send status notification here if needed
            break;

        default:
            break;
    }
}

// ============================================================================
// Setup
// ============================================================================

static void usbridge_host_setup(void) {
    printf("\n");
    printf("========================================\n");
    printf("USBridge Host - BLE Peripheral\n");
    printf("========================================\n");
    printf("\n");
    printf("Remote update: Send 'BOOTSEL\\n' via CDC serial\n");
    printf("\n");

    // Initialize L2CAP
    l2cap_init();

    // Initialize Security Manager (no authentication for MVP)
    sm_init();
    sm_set_io_capabilities(IO_CAPABILITY_NO_INPUT_NO_OUTPUT);
    sm_set_authentication_requirements(0);  // No authentication

    // Initialize ATT Server with our GATT database
    att_server_init(profile_data, att_read_callback, att_write_callback);

    // Register for HCI events
    hci_event_callback_registration.callback = &packet_handler;
    hci_add_event_handler(&hci_event_callback_registration);

    // Register for ATT events
    att_server_register_packet_handler(packet_handler);

    // Setup advertisements
    uint16_t adv_int_min = 0x0030;  // 30ms
    uint16_t adv_int_max = 0x0060;  // 60ms
    uint8_t adv_type = 0;  // ADV_IND - connectable undirected
    bd_addr_t null_addr;
    memset(null_addr, 0, 6);

    gap_advertisements_set_params(adv_int_min, adv_int_max, adv_type, 0, null_addr, 0x07, 0x00);
    gap_advertisements_set_data(adv_data_len, adv_data);
    gap_scan_response_set_data(scan_resp_data_len, scan_resp_data);
    gap_advertisements_enable(1);

    printf("[BLE] Service UUID: 6E400001-B5A3-F393-E0A9-E50E24DCCA9E\n");
    printf("[BLE] HID Char UUID: 6E400002-B5A3-F393-E0A9-E50E24DCCA9E\n");
    printf("[BLE] Status Char UUID: 6E400003-B5A3-F393-E0A9-E50E24DCCA9E\n");
    printf("\n");

    // Initialize USB HID
    usb_hid_init();

    // Setup LED timer
    led_timer.process = &led_timer_handler;
    btstack_run_loop_set_timer(&led_timer, 500);
    btstack_run_loop_add_timer(&led_timer);

    // Setup USB timer (runs TinyUSB task)
    usb_timer.process = &usb_timer_handler;
    btstack_run_loop_set_timer(&usb_timer, 1);
    btstack_run_loop_add_timer(&usb_timer);
}

// ============================================================================
// Main Entry Point (called by BTstack)
// ============================================================================

int btstack_main(void);
int btstack_main(void) {
    usbridge_host_setup();

    // Power on Bluetooth
    hci_power_control(HCI_POWER_ON);

    return 0;
}
