# USBridge Python Prototype

This directory contains the Python prototype for testing and development.

## Quick Start

```bash
cd /home/bake/usbridge
source venv/bin/activate

# Test HID input (no BLE needed)
python proto/test_hid.py

# Run terminal (scans for hosts)
python proto/terminal.py -v

# Run terminal in interactive mode
python proto/terminal.py -i -v

# Run mock host (for testing terminal)
# Requires root for BLE advertising
sudo venv/bin/python proto/mock_host.py -v
```

## Files

| File | Description |
|------|-------------|
| `protocol.py` | BLE protocol definitions, UUIDs, data structures |
| `hid_input.py` | USB HID input reader using evdev |
| `ble_central.py` | BLE Central (scanner/connector) using bleak |
| `terminal.py` | Main Terminal application |
| `mock_host.py` | Mock Host for testing (BLE peripheral) |
| `test_hid.py` | Test script for HID input |

## Testing Without Hardware

1. **Test HID Input**: Plug in any USB keyboard and run `test_hid.py`
2. **Test BLE Scanning**: Run `terminal.py -v` - it will scan for hosts
3. **Full Loop Test**: Run `mock_host.py` in one terminal, `terminal.py` in another

## Notes

- The mock_host requires root/sudo for BLE advertising
- If no USB keyboard is connected, the terminal will wait for one
- Use `-v` for verbose output, `-d` for debug output
