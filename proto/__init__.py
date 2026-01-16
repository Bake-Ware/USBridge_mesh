"""
USBridge Protocol Prototype

Python prototype implementation for testing and development.
"""

from .protocol import (
    USBRIDGE_SERVICE_UUID,
    USBRIDGE_HID_CHAR_UUID,
    USBRIDGE_STATUS_CHAR_UUID,
    DeviceType,
    Capability,
    KeyboardReport,
    StatusReport,
    MessageType,
)

from .hid_input import HIDInputReader, KeyboardState
from .ble_central import BLECentral, ConnectionState, DiscoveredHost
from .terminal import Terminal

__all__ = [
    # Protocol
    'USBRIDGE_SERVICE_UUID',
    'USBRIDGE_HID_CHAR_UUID',
    'USBRIDGE_STATUS_CHAR_UUID',
    'DeviceType',
    'Capability',
    'KeyboardReport',
    'StatusReport',
    'MessageType',
    # HID
    'HIDInputReader',
    'KeyboardState',
    # BLE
    'BLECentral',
    'ConnectionState',
    'DiscoveredHost',
    # Terminal
    'Terminal',
]
