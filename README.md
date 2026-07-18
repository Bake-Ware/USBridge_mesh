# USBridge

> **Status: abandoned prototype.** This was an early (Jan 2026) experiment in
> bridging USB HID over BLE. Development stopped mid-way — the firmware
> advertises and enumerates but the end-to-end keyboard path was never
> completed. The ideas here grew into
> [geppetto](https://github.com/Bake-Ware/geppetto) (Pico-based HID
> forwarding, actively used) and
> [telesthete-kvm](https://github.com/Bake-Ware/telesthete-kvm) (software KVM).
> Archived for reference.

A hardware KVM experiment: a USB keyboard plugged into a "Terminal" device
(Raspberry Pi 5) is forwarded over BLE to a Pico 2W "Host", which presents
itself as a USB keyboard gadget to the target PC.

```
[USB Keyboard] → [Pi5 Terminal] ══BLE══> [Pico 2W Host] → [PC]
                  evdev capture           BTstack GATT ·
                  bleak central           TinyUSB HID gadget
```

## What's here

- `proto/` — Python prototype of the Terminal side: evdev HID capture, BLE
  central (bleak), protocol definitions, and a mock host for testing without
  hardware. See `proto/README.md`.
- `firmware/pico_host/` — Pico 2W firmware: BTstack BLE peripheral with a
  custom GATT service, TinyUSB HID device, and remote reflashing over USB CDC
  (send `BOOTSEL\n` to the serial port to reboot into the bootloader — see
  `REMOTE_FLASH.md`).
- `PLAN.md` — the original five-phase development plan. Phases 1–2 were
  completed; work stopped during phase 3.

## License

[MIT](LICENSE)
