# USBridge MVP Development Plan

## Goal
Build working Terminal (Pi5) ↔ Host (Pico 2W) communication where:
- Terminal reads USB keyboard, sends HID over BLE
- Host receives BLE HID, injects to PC via USB gadget

## Current State
- [x] Python Terminal prototype exists
- [x] Pico 2W detected at `/media/bake/RP2350`
- [x] Keyboard detected (Telink Wireless Receiver, event8)

---

## Phase 1: Pico SDK Setup
**Milestone**: Can compile and flash a blink program to Pico 2W

### Tasks
1. Install Pico SDK and dependencies
2. Create test blink program
3. Compile and flash to verify toolchain works

### Completion Criteria
- LED blinks on Pico 2W

---

## Phase 2: Pico Host - BLE Peripheral
**Milestone**: Pico advertises USBridge service, Terminal can discover it

### Tasks
1. Set up BTstack for Pico W
2. Implement BLE advertising with USBridge service UUID
3. Implement GATT service with HID characteristic
4. Test: Terminal scans and finds Pico Host

### Completion Criteria
- `python proto/terminal.py -i` → `scan` → shows Pico Host

---

## Phase 3: Pico Host - USB HID Device
**Milestone**: Pico appears as USB keyboard to connected PC

### Tasks
1. Configure TinyUSB device mode
2. Implement HID keyboard descriptor
3. Test: PC recognizes Pico as keyboard

### Completion Criteria
- PC shows Pico as USB keyboard device

---

## Phase 4: Pico Host - BLE to USB Bridge
**Milestone**: HID reports received via BLE are injected to PC

### Tasks
1. Connect BLE GATT writes to USB HID output
2. Implement HID report forwarding
3. LED status indicators

### Completion Criteria
- Write to BLE characteristic → PC receives keystroke

---

## Phase 5: End-to-End Integration
**Milestone**: Type on Pi5 keyboard → characters appear on PC

### Tasks
1. Terminal connects to Pico Host
2. Terminal forwards keyboard HID over BLE
3. Pico injects to PC
4. Full typing test

### Completion Criteria
- Type "Hello World" on Pi5 keyboard
- "Hello World" appears on PC connected to Pico

---

## Testing Strategy

### Unit Tests
- BLE advertising visible
- USB device enumeration
- HID report parsing

### Integration Tests
- Terminal discovers Host
- Terminal connects to Host
- HID forwarding works

### End-to-End Test
- Full typing test across devices

---

## Hardware Setup
```
[USB Keyboard] → [Pi5 Terminal] ══BLE══> [Pico 2W Host] → [PC]
     ↑                                         ↑
  Telink                                  USB gadget
  event8                                  mode
```

---

## Files to Create

### Pico Host Firmware
```
/home/bake/usbridge/firmware/pico_host/
├── CMakeLists.txt
├── main.c
├── ble_host.c / .h      # BLE peripheral implementation
├── usb_hid.c / .h       # USB HID device
├── led_status.c / .h    # LED indicators
└── usbridge_config.h    # Configuration
```

---

## Progress Tracking
- [ ] Phase 1: Pico SDK Setup
- [ ] Phase 2: BLE Peripheral
- [ ] Phase 3: USB HID Device
- [ ] Phase 4: BLE to USB Bridge
- [ ] Phase 5: End-to-End Integration
