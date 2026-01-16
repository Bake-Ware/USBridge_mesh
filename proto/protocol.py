"""
USBridge Protocol Definitions

This module defines the BLE protocol constants, UUIDs, and data structures
used for communication between Terminal and Host devices.
"""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

# ============================================================================
# BLE Service and Characteristic UUIDs
# ============================================================================

# USBridge Service UUID: 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
# (Based on Nordic UART Service format for compatibility)
USBRIDGE_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"

# HID Report Characteristic (Write Without Response, Terminal -> Host)
USBRIDGE_HID_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Status Characteristic (Notify, Host -> Terminal)
USBRIDGE_STATUS_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Config Characteristic (Read/Write, for future use)
USBRIDGE_CONFIG_CHAR_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"


# ============================================================================
# Device Types and Capabilities
# ============================================================================

class DeviceType(IntEnum):
    """Device operating mode"""
    PEER = 0        # Idle/unconfigured
    TERMINAL = 1    # Has HID devices, connects to hosts
    HOST = 2        # Dongle mode, receives HID, injects to PC


class Capability(IntEnum):
    """Device capability flags (bitmask)"""
    KEYBOARD = 1 << 0   # Supports keyboard HID
    MOUSE = 1 << 1      # Supports mouse HID (future)
    BLE = 1 << 2        # BLE transport available
    WIFI = 1 << 3       # WiFi transport available (future)


# ============================================================================
# HID Report Structures
# ============================================================================

@dataclass
class KeyboardReport:
    """
    Standard USB HID Keyboard Report (8 bytes)

    Format:
    - modifier: Ctrl/Shift/Alt/GUI modifier keys (bitmask)
    - reserved: Always 0
    - keycodes: Up to 6 simultaneous key codes
    """
    modifier: int = 0
    reserved: int = 0
    keycodes: tuple = (0, 0, 0, 0, 0, 0)

    def to_bytes(self) -> bytes:
        """Serialize to 8-byte HID report"""
        return struct.pack('BB6B',
                          self.modifier,
                          self.reserved,
                          *self.keycodes)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'KeyboardReport':
        """Deserialize from 8-byte HID report"""
        if len(data) < 8:
            data = data + bytes(8 - len(data))
        unpacked = struct.unpack('BB6B', data[:8])
        return cls(
            modifier=unpacked[0],
            reserved=unpacked[1],
            keycodes=unpacked[2:8]
        )

    def __repr__(self) -> str:
        mod_str = []
        if self.modifier & 0x01: mod_str.append('L-Ctrl')
        if self.modifier & 0x02: mod_str.append('L-Shift')
        if self.modifier & 0x04: mod_str.append('L-Alt')
        if self.modifier & 0x08: mod_str.append('L-GUI')
        if self.modifier & 0x10: mod_str.append('R-Ctrl')
        if self.modifier & 0x20: mod_str.append('R-Shift')
        if self.modifier & 0x40: mod_str.append('R-Alt')
        if self.modifier & 0x80: mod_str.append('R-GUI')

        keys = [k for k in self.keycodes if k != 0]
        return f"KeyboardReport(mod=[{'+'.join(mod_str) or 'none'}], keys={keys})"


# ============================================================================
# BLE Protocol Messages
# ============================================================================

class MessageType(IntEnum):
    """Protocol message types"""
    HID_KEYBOARD = 0x01     # Keyboard HID report
    HID_MOUSE = 0x02        # Mouse HID report (future)
    STATUS = 0x10           # Status update
    CONFIG = 0x20           # Configuration
    PING = 0x30             # Keep-alive ping
    PONG = 0x31             # Keep-alive response


@dataclass
class StatusReport:
    """
    Status report from Host to Terminal

    Sent periodically to indicate connection health.
    """
    connected: bool = False
    battery_percent: int = 100
    latency_ms: int = 0

    def to_bytes(self) -> bytes:
        """Serialize to bytes"""
        return struct.pack('<BBH',
                          1 if self.connected else 0,
                          self.battery_percent,
                          self.latency_ms)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'StatusReport':
        """Deserialize from bytes"""
        if len(data) < 4:
            data = data + bytes(4 - len(data))
        connected, battery, latency = struct.unpack('<BBH', data[:4])
        return cls(
            connected=bool(connected),
            battery_percent=battery,
            latency_ms=latency
        )


# ============================================================================
# Advertisement Data
# ============================================================================

@dataclass
class AdvertisementData:
    """
    Data included in BLE advertisement packets.

    Used by Terminals to identify Hosts during scanning.
    """
    device_type: DeviceType
    capabilities: int
    device_name: str

    def matches_host(self) -> bool:
        """Check if this is a USBridge Host"""
        return self.device_type == DeviceType.HOST


# ============================================================================
# HID Key Codes (subset of USB HID usage codes)
# ============================================================================

class HIDKeyCode(IntEnum):
    """Common USB HID keyboard usage codes"""
    NONE = 0x00

    # Letters
    A = 0x04
    B = 0x05
    C = 0x06
    D = 0x07
    E = 0x08
    F = 0x09
    G = 0x0A
    H = 0x0B
    I = 0x0C
    J = 0x0D
    K = 0x0E
    L = 0x0F
    M = 0x10
    N = 0x11
    O = 0x12
    P = 0x13
    Q = 0x14
    R = 0x15
    S = 0x16
    T = 0x17
    U = 0x18
    V = 0x19
    W = 0x1A
    X = 0x1B
    Y = 0x1C
    Z = 0x1D

    # Numbers
    KEY_1 = 0x1E
    KEY_2 = 0x1F
    KEY_3 = 0x20
    KEY_4 = 0x21
    KEY_5 = 0x22
    KEY_6 = 0x23
    KEY_7 = 0x24
    KEY_8 = 0x25
    KEY_9 = 0x26
    KEY_0 = 0x27

    # Special keys
    ENTER = 0x28
    ESCAPE = 0x29
    BACKSPACE = 0x2A
    TAB = 0x2B
    SPACE = 0x2C

    # Function keys
    F1 = 0x3A
    F2 = 0x3B
    F3 = 0x3C
    F4 = 0x3D
    F5 = 0x3E
    F6 = 0x3F
    F7 = 0x40
    F8 = 0x41
    F9 = 0x42
    F10 = 0x43
    F11 = 0x44
    F12 = 0x45

    # Modifiers (not used in keycode array, but useful reference)
    SCROLL_LOCK = 0x47


# ============================================================================
# Modifier Key Masks
# ============================================================================

class ModifierMask(IntEnum):
    """Modifier key bitmasks for keyboard report"""
    LEFT_CTRL = 0x01
    LEFT_SHIFT = 0x02
    LEFT_ALT = 0x04
    LEFT_GUI = 0x08
    RIGHT_CTRL = 0x10
    RIGHT_SHIFT = 0x20
    RIGHT_ALT = 0x40
    RIGHT_GUI = 0x80
