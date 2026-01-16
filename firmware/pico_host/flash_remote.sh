#!/bin/bash
# Remote firmware flash script for USBridge Host (Pico 2W)
#
# Usage: ./flash_remote.sh [uf2_file]
#
# This script triggers BOOTSEL mode via CDC serial, then flashes new firmware.

UF2_FILE="${1:-build/usbridge_host.uf2}"
CDC_PORT="/dev/ttyACM0"
BOOTSEL_MOUNT1="/media/bake/RP2350"
BOOTSEL_MOUNT2="/media/bake/RPI-RP2"

echo "========================================"
echo "USBridge Remote Firmware Update"
echo "========================================"
echo ""

# Check if UF2 file exists
if [ ! -f "$UF2_FILE" ]; then
    echo "ERROR: Firmware file not found: $UF2_FILE"
    exit 1
fi

echo "Firmware: $UF2_FILE"
echo "Size: $(ls -lh "$UF2_FILE" | awk '{print $5}')"
echo ""

# Check if CDC port exists
if [ ! -e "$CDC_PORT" ]; then
    echo "ERROR: CDC serial port not found: $CDC_PORT"
    echo "Is the Pico connected?"
    exit 1
fi

# Send BOOTSEL command
echo "Sending BOOTSEL command to $CDC_PORT..."
echo "BOOTSEL" > "$CDC_PORT"

# Wait for BOOTSEL mount
echo "Waiting for BOOTSEL mode..."
timeout=10
while [ $timeout -gt 0 ]; do
    if [ -d "$BOOTSEL_MOUNT1" ] || [ -d "$BOOTSEL_MOUNT2" ]; then
        break
    fi
    sleep 1
    timeout=$((timeout - 1))
done

if [ $timeout -eq 0 ]; then
    echo "ERROR: Pico did not enter BOOTSEL mode"
    exit 1
fi

# Determine which mount point
if [ -d "$BOOTSEL_MOUNT1" ]; then
    MOUNT="$BOOTSEL_MOUNT1"
else
    MOUNT="$BOOTSEL_MOUNT2"
fi

echo "BOOTSEL mounted at: $MOUNT"

# Copy firmware
echo "Flashing firmware..."
cp "$UF2_FILE" "$MOUNT/"

# Wait for unmount (indicates flash complete)
echo "Waiting for flash to complete..."
timeout=10
while [ $timeout -gt 0 ]; do
    if [ ! -d "$MOUNT" ]; then
        break
    fi
    sleep 1
    timeout=$((timeout - 1))
done

if [ -d "$MOUNT" ]; then
    echo "WARNING: BOOTSEL mount still present, but flash may have completed"
fi

# Wait for device to reboot and enumerate
echo "Waiting for device to reboot..."
sleep 3

# Check if device is back
if lsusb | grep -q "2e8a:000a"; then
    echo ""
    echo "========================================"
    echo "Firmware flash successful!"
    echo "========================================"
    echo ""
    echo "Device is online. Check serial output:"
    echo "  cat $CDC_PORT"
    exit 0
else
    echo ""
    echo "WARNING: Device not detected after flash"
    echo "It may still be booting..."
    exit 1
fi
