"""
USB HID Input Reader using evdev

Reads keyboard events from Linux input devices and converts them
to USB HID reports for forwarding to hosts.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, AsyncIterator

import evdev
from evdev import ecodes, InputDevice, categorize, KeyEvent

try:
    from .protocol import KeyboardReport
except ImportError:
    from protocol import KeyboardReport

logger = logging.getLogger(__name__)


# ============================================================================
# Linux evdev keycode to USB HID keycode mapping
# ============================================================================

# Map Linux KEY_* codes to USB HID usage codes
EVDEV_TO_HID: dict[int, int] = {
    # Letters
    ecodes.KEY_A: 0x04,
    ecodes.KEY_B: 0x05,
    ecodes.KEY_C: 0x06,
    ecodes.KEY_D: 0x07,
    ecodes.KEY_E: 0x08,
    ecodes.KEY_F: 0x09,
    ecodes.KEY_G: 0x0A,
    ecodes.KEY_H: 0x0B,
    ecodes.KEY_I: 0x0C,
    ecodes.KEY_J: 0x0D,
    ecodes.KEY_K: 0x0E,
    ecodes.KEY_L: 0x0F,
    ecodes.KEY_M: 0x10,
    ecodes.KEY_N: 0x11,
    ecodes.KEY_O: 0x12,
    ecodes.KEY_P: 0x13,
    ecodes.KEY_Q: 0x14,
    ecodes.KEY_R: 0x15,
    ecodes.KEY_S: 0x16,
    ecodes.KEY_T: 0x17,
    ecodes.KEY_U: 0x18,
    ecodes.KEY_V: 0x19,
    ecodes.KEY_W: 0x1A,
    ecodes.KEY_X: 0x1B,
    ecodes.KEY_Y: 0x1C,
    ecodes.KEY_Z: 0x1D,

    # Numbers
    ecodes.KEY_1: 0x1E,
    ecodes.KEY_2: 0x1F,
    ecodes.KEY_3: 0x20,
    ecodes.KEY_4: 0x21,
    ecodes.KEY_5: 0x22,
    ecodes.KEY_6: 0x23,
    ecodes.KEY_7: 0x24,
    ecodes.KEY_8: 0x25,
    ecodes.KEY_9: 0x26,
    ecodes.KEY_0: 0x27,

    # Special keys
    ecodes.KEY_ENTER: 0x28,
    ecodes.KEY_ESC: 0x29,
    ecodes.KEY_BACKSPACE: 0x2A,
    ecodes.KEY_TAB: 0x2B,
    ecodes.KEY_SPACE: 0x2C,
    ecodes.KEY_MINUS: 0x2D,
    ecodes.KEY_EQUAL: 0x2E,
    ecodes.KEY_LEFTBRACE: 0x2F,
    ecodes.KEY_RIGHTBRACE: 0x30,
    ecodes.KEY_BACKSLASH: 0x31,
    ecodes.KEY_SEMICOLON: 0x33,
    ecodes.KEY_APOSTROPHE: 0x34,
    ecodes.KEY_GRAVE: 0x35,
    ecodes.KEY_COMMA: 0x36,
    ecodes.KEY_DOT: 0x37,
    ecodes.KEY_SLASH: 0x38,
    ecodes.KEY_CAPSLOCK: 0x39,

    # Function keys
    ecodes.KEY_F1: 0x3A,
    ecodes.KEY_F2: 0x3B,
    ecodes.KEY_F3: 0x3C,
    ecodes.KEY_F4: 0x3D,
    ecodes.KEY_F5: 0x3E,
    ecodes.KEY_F6: 0x3F,
    ecodes.KEY_F7: 0x40,
    ecodes.KEY_F8: 0x41,
    ecodes.KEY_F9: 0x42,
    ecodes.KEY_F10: 0x43,
    ecodes.KEY_F11: 0x44,
    ecodes.KEY_F12: 0x45,

    # Print screen, scroll lock, pause
    ecodes.KEY_SYSRQ: 0x46,
    ecodes.KEY_SCROLLLOCK: 0x47,
    ecodes.KEY_PAUSE: 0x48,

    # Navigation
    ecodes.KEY_INSERT: 0x49,
    ecodes.KEY_HOME: 0x4A,
    ecodes.KEY_PAGEUP: 0x4B,
    ecodes.KEY_DELETE: 0x4C,
    ecodes.KEY_END: 0x4D,
    ecodes.KEY_PAGEDOWN: 0x4E,
    ecodes.KEY_RIGHT: 0x4F,
    ecodes.KEY_LEFT: 0x50,
    ecodes.KEY_DOWN: 0x51,
    ecodes.KEY_UP: 0x52,

    # Keypad
    ecodes.KEY_NUMLOCK: 0x53,
    ecodes.KEY_KPSLASH: 0x54,
    ecodes.KEY_KPASTERISK: 0x55,
    ecodes.KEY_KPMINUS: 0x56,
    ecodes.KEY_KPPLUS: 0x57,
    ecodes.KEY_KPENTER: 0x58,
    ecodes.KEY_KP1: 0x59,
    ecodes.KEY_KP2: 0x5A,
    ecodes.KEY_KP3: 0x5B,
    ecodes.KEY_KP4: 0x5C,
    ecodes.KEY_KP5: 0x5D,
    ecodes.KEY_KP6: 0x5E,
    ecodes.KEY_KP7: 0x5F,
    ecodes.KEY_KP8: 0x60,
    ecodes.KEY_KP9: 0x61,
    ecodes.KEY_KP0: 0x62,
    ecodes.KEY_KPDOT: 0x63,
}

# Modifier key mapping (evdev code -> modifier bit)
MODIFIER_KEYS: dict[int, int] = {
    ecodes.KEY_LEFTCTRL: 0x01,
    ecodes.KEY_LEFTSHIFT: 0x02,
    ecodes.KEY_LEFTALT: 0x04,
    ecodes.KEY_LEFTMETA: 0x08,
    ecodes.KEY_RIGHTCTRL: 0x10,
    ecodes.KEY_RIGHTSHIFT: 0x20,
    ecodes.KEY_RIGHTALT: 0x40,
    ecodes.KEY_RIGHTMETA: 0x80,
}


# ============================================================================
# Keyboard State Tracker
# ============================================================================

@dataclass
class KeyboardState:
    """
    Tracks the current state of a keyboard.

    Maintains pressed keys and modifiers to generate accurate HID reports.
    """
    modifier: int = 0
    pressed_keys: set = field(default_factory=set)

    def key_down(self, evdev_code: int) -> None:
        """Handle key press"""
        if evdev_code in MODIFIER_KEYS:
            self.modifier |= MODIFIER_KEYS[evdev_code]
        elif evdev_code in EVDEV_TO_HID:
            self.pressed_keys.add(EVDEV_TO_HID[evdev_code])

    def key_up(self, evdev_code: int) -> None:
        """Handle key release"""
        if evdev_code in MODIFIER_KEYS:
            self.modifier &= ~MODIFIER_KEYS[evdev_code]
        elif evdev_code in EVDEV_TO_HID:
            hid_code = EVDEV_TO_HID[evdev_code]
            self.pressed_keys.discard(hid_code)

    def to_report(self) -> KeyboardReport:
        """Generate HID report from current state"""
        # Take up to 6 keys (USB HID limit)
        keys = list(self.pressed_keys)[:6]
        # Pad to 6 elements
        while len(keys) < 6:
            keys.append(0)

        return KeyboardReport(
            modifier=self.modifier,
            reserved=0,
            keycodes=tuple(keys)
        )

    def clear(self) -> None:
        """Reset state (used when device disconnects)"""
        self.modifier = 0
        self.pressed_keys.clear()


# ============================================================================
# HID Input Reader
# ============================================================================

class HIDInputReader:
    """
    Reads HID input from all connected USB keyboards.

    Monitors /dev/input for keyboard devices and converts their
    events to USB HID reports.
    """

    def __init__(self):
        self._devices: dict[str, InputDevice] = {}
        self._states: dict[str, KeyboardState] = {}
        self._running = False
        self._report_callback: Optional[Callable[[KeyboardReport], None]] = None
        self._device_added_callback: Optional[Callable[[str, str], None]] = None
        self._device_removed_callback: Optional[Callable[[str], None]] = None

    def on_report(self, callback: Callable[[KeyboardReport], None]) -> None:
        """Register callback for HID reports"""
        self._report_callback = callback

    def on_device_added(self, callback: Callable[[str, str], None]) -> None:
        """Register callback for device additions (path, name)"""
        self._device_added_callback = callback

    def on_device_removed(self, callback: Callable[[str], None]) -> None:
        """Register callback for device removals (path)"""
        self._device_removed_callback = callback

    def _is_keyboard(self, device: InputDevice) -> bool:
        """Check if device is a keyboard"""
        caps = device.capabilities()
        # Must have EV_KEY capability
        if ecodes.EV_KEY not in caps:
            return False

        # Check for letter keys (A-Z) - a good indicator of keyboard
        keys = caps.get(ecodes.EV_KEY, [])
        has_letters = any(ecodes.KEY_A <= k <= ecodes.KEY_Z for k in keys)

        # Exclude mice and other pointing devices
        has_buttons_only = all(k < ecodes.KEY_A or k > ecodes.KEY_Z for k in keys)
        is_mouse = ecodes.EV_REL in caps and has_buttons_only

        return has_letters and not is_mouse

    def _scan_devices(self) -> list[str]:
        """Scan for keyboard devices"""
        keyboards = []
        input_dir = Path('/dev/input')

        for event_path in input_dir.glob('event*'):
            path_str = str(event_path)
            if path_str in self._devices:
                continue  # Already tracking

            try:
                device = InputDevice(path_str)
                if self._is_keyboard(device):
                    keyboards.append(path_str)
                    logger.info(f"Found keyboard: {device.name} at {path_str}")
                else:
                    device.close()
            except (PermissionError, OSError) as e:
                logger.debug(f"Cannot access {path_str}: {e}")

        return keyboards

    def _add_device(self, path: str) -> bool:
        """Add a device to tracking"""
        if path in self._devices:
            return False

        try:
            device = InputDevice(path)
            if not self._is_keyboard(device):
                device.close()
                return False

            # Grab exclusive access so keys don't go to local system
            # Comment this out during development if you need local keyboard
            # device.grab()

            self._devices[path] = device
            self._states[path] = KeyboardState()

            logger.info(f"Added keyboard: {device.name}")
            if self._device_added_callback:
                self._device_added_callback(path, device.name)

            return True

        except (PermissionError, OSError) as e:
            logger.error(f"Failed to add device {path}: {e}")
            return False

    def _remove_device(self, path: str) -> None:
        """Remove a device from tracking"""
        if path not in self._devices:
            return

        device = self._devices.pop(path)
        self._states.pop(path, None)

        try:
            device.close()
        except Exception:
            pass

        logger.info(f"Removed keyboard: {path}")
        if self._device_removed_callback:
            self._device_removed_callback(path)

    async def _read_device(self, path: str) -> AsyncIterator[KeyboardReport]:
        """Read events from a single device"""
        device = self._devices.get(path)
        state = self._states.get(path)

        if not device or not state:
            return

        try:
            async for event in device.async_read_loop():
                if event.type != ecodes.EV_KEY:
                    continue

                key_event = categorize(event)
                if not isinstance(key_event, KeyEvent):
                    continue

                # Handle key state change
                if key_event.keystate == KeyEvent.key_down:
                    state.key_down(event.code)
                elif key_event.keystate == KeyEvent.key_up:
                    state.key_up(event.code)
                elif key_event.keystate == KeyEvent.key_hold:
                    # Repeat events - we don't need to update state
                    # but we should send the report again
                    pass
                else:
                    continue

                # Generate and yield report
                report = state.to_report()
                yield report

        except OSError as e:
            logger.warning(f"Device {path} disconnected: {e}")
            self._remove_device(path)

    async def run(self) -> None:
        """Main loop - scan for devices and read events"""
        self._running = True
        logger.info("HID Input Reader started")

        # Track active reader tasks
        tasks: dict[str, asyncio.Task] = {}

        async def device_reader(path: str):
            """Task to read from a single device"""
            async for report in self._read_device(path):
                if self._report_callback:
                    self._report_callback(report)

        try:
            while self._running:
                # Scan for new devices
                new_devices = self._scan_devices()
                for path in new_devices:
                    if self._add_device(path):
                        # Start reader task for this device
                        task = asyncio.create_task(device_reader(path))
                        tasks[path] = task

                # Clean up finished tasks (disconnected devices)
                done_paths = [p for p, t in tasks.items() if t.done()]
                for path in done_paths:
                    tasks.pop(path)
                    self._remove_device(path)

                # Small delay before next scan
                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            logger.info("HID Input Reader stopping")
        finally:
            self._running = False
            # Cancel all reader tasks
            for task in tasks.values():
                task.cancel()
            # Close all devices
            for path in list(self._devices.keys()):
                self._remove_device(path)

    def stop(self) -> None:
        """Stop the reader"""
        self._running = False

    def get_devices(self) -> list[tuple[str, str]]:
        """Get list of tracked devices (path, name)"""
        return [(p, d.name) for p, d in self._devices.items()]


# ============================================================================
# Testing / CLI
# ============================================================================

async def main():
    """Test the HID input reader"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )

    reader = HIDInputReader()

    def on_report(report: KeyboardReport):
        print(f"Report: {report}")
        print(f"  Bytes: {report.to_bytes().hex()}")

    def on_device_added(path: str, name: str):
        print(f"[+] Keyboard added: {name} ({path})")

    def on_device_removed(path: str):
        print(f"[-] Keyboard removed: {path}")

    reader.on_report(on_report)
    reader.on_device_added(on_device_added)
    reader.on_device_removed(on_device_removed)

    print("HID Input Reader Test")
    print("Plug in a USB keyboard to see events...")
    print("Press Ctrl+C to exit")
    print()

    try:
        await reader.run()
    except KeyboardInterrupt:
        print("\nStopping...")
        reader.stop()


if __name__ == '__main__':
    asyncio.run(main())
