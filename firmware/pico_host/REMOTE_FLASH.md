# Remote Firmware Flashing for USBridge Host

After the initial manual flash, you can update firmware remotely without physical access to the BOOTSEL button.

## How It Works

The firmware includes a CDC serial command handler that listens for the magic string `BOOTSEL\n`. When received, it triggers a watchdog reset into BOOTSEL mode.

## Manual Method

1. Send the BOOTSEL command via serial:
   ```bash
   echo "BOOTSEL" > /dev/ttyACM0
   ```

2. Wait for BOOTSEL mode (device mounts as RP2350 or RPI-RP2)

3. Copy the firmware:
   ```bash
   cp build/usbridge_host.uf2 /media/bake/RP2350/
   ```

4. Device will automatically reboot with new firmware

## Automated Method

Use the provided script:
```bash
cd /home/bake/usbridge/firmware/pico_host
./flash_remote.sh
```

Or specify a custom firmware file:
```bash
./flash_remote.sh path/to/custom.uf2
```

## Troubleshooting

**Device doesn't enter BOOTSEL mode:**
- Ensure CDC port is /dev/ttyACM0 (check with `ls /dev/ttyACM*`)
- Check if device is running the firmware with reset support
- Fall back to physical BOOTSEL button

**Permission denied:**
- Add your user to the dialout group: `sudo usermod -a -G dialout $USER`
- Or run with sudo: `sudo ./flash_remote.sh`

**Mount point different:**
- Edit flash_remote.sh and update BOOTSEL_MOUNT1 and BOOTSEL_MOUNT2 variables
- Check actual mount with: `ls /media/$USER/`

## Initial Flash (Physical BOOTSEL Required)

This is the ONE TIME you need physical access:

1. Unplug the Pico 2W from USB
2. Hold the BOOTSEL button on the Pico
3. Plug the USB cable back in while holding the button
4. Release the button
5. Device mounts as RP2350 or RPI-RP2
6. Copy firmware: `cp build/usbridge_host.uf2 /media/bake/RP2350/`
7. Device reboots - all future updates can now be done remotely!

## Verifying Remote Reset Works

After flashing, check the serial output:
```bash
cat /dev/ttyACM0
```

You should see:
```
========================================
USBridge Host - BLE Peripheral
========================================

Remote update: Send 'BOOTSEL\n' via CDC serial
```

## Build New Firmware

```bash
cd /home/bake/usbridge/firmware/pico_host/build
export PICO_SDK_PATH=/home/bake/pico-sdk
make -j4
```

Then flash with:
```bash
cd ..
./flash_remote.sh
```
