#!/usr/bin/env python3
"""
Test script for HID input reader.

Run this to verify keyboard detection and event capture works.
No BLE required - just tests the evdev integration.

Usage:
    cd /home/bake/usbridge
    source venv/bin/activate
    python proto/test_hid.py
"""

import asyncio
import logging
import sys
import os

# Add proto to path
sys.path.insert(0, os.path.dirname(__file__))

from hid_input import HIDInputReader
from protocol import KeyboardReport


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s'
    )

    print("=" * 60)
    print("USBridge HID Input Reader Test")
    print("=" * 60)
    print()
    print("This test will:")
    print("  1. Scan for USB keyboards")
    print("  2. Print any keyboard events detected")
    print("  3. Show the HID report bytes that would be sent over BLE")
    print()
    print("Instructions:")
    print("  - Plug in a USB keyboard")
    print("  - Type on it to see events")
    print("  - Press Ctrl+C to exit")
    print()
    print("-" * 60)

    reader = HIDInputReader()
    report_count = 0

    def on_report(report: KeyboardReport):
        nonlocal report_count
        report_count += 1
        raw = report.to_bytes()
        print(f"[{report_count:4d}] {report}")
        print(f"       Bytes: {raw.hex(' ')}")

    def on_device_added(path: str, name: str):
        print(f"\n[+] Keyboard connected: {name}")
        print(f"    Path: {path}")
        print()

    def on_device_removed(path: str):
        print(f"\n[-] Keyboard removed: {path}")
        print()

    reader.on_report(on_report)
    reader.on_device_added(on_device_added)
    reader.on_device_removed(on_device_removed)

    print("Waiting for keyboards...")
    print()

    try:
        await reader.run()
    except KeyboardInterrupt:
        print("\n\nStopping...")
        reader.stop()
        print(f"\nTotal reports captured: {report_count}")


if __name__ == '__main__':
    asyncio.run(main())
