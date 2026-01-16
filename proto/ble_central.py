"""
BLE Central (Terminal side)

Handles scanning for USBridge Host devices, connecting, and
sending HID reports over BLE.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData as BleakAdvertisementData

try:
    from .protocol import (
        USBRIDGE_SERVICE_UUID,
        USBRIDGE_HID_CHAR_UUID,
        USBRIDGE_STATUS_CHAR_UUID,
        KeyboardReport,
        StatusReport,
        DeviceType,
    )
except ImportError:
    from protocol import (
        USBRIDGE_SERVICE_UUID,
        USBRIDGE_HID_CHAR_UUID,
        USBRIDGE_STATUS_CHAR_UUID,
        KeyboardReport,
        StatusReport,
        DeviceType,
    )

logger = logging.getLogger(__name__)


# ============================================================================
# Connection State
# ============================================================================

class ConnectionState(Enum):
    """BLE connection state machine"""
    IDLE = auto()           # Not doing anything
    SCANNING = auto()       # Scanning for hosts
    CONNECTING = auto()     # Establishing connection
    CONNECTED = auto()      # Connected and ready
    DISCONNECTING = auto()  # Disconnecting
    ERROR = auto()          # Error state


# ============================================================================
# Discovered Host
# ============================================================================

@dataclass
class DiscoveredHost:
    """Information about a discovered USBridge Host"""
    address: str
    name: str
    rssi: int
    device: BLEDevice

    def __repr__(self) -> str:
        return f"Host({self.name}, {self.address}, {self.rssi}dBm)"


# ============================================================================
# BLE Central
# ============================================================================

class BLECentral:
    """
    BLE Central role for Terminal devices.

    Scans for and connects to USBridge Host peripherals,
    then forwards HID reports over BLE.
    """

    def __init__(self, device_name: str = "USBridge-Terminal"):
        self._device_name = device_name
        self._state = ConnectionState.IDLE
        self._client: Optional[BleakClient] = None
        self._connected_host: Optional[DiscoveredHost] = None
        self._discovered_hosts: dict[str, DiscoveredHost] = {}

        # Characteristic handles (discovered after connection)
        self._hid_char_handle: Optional[int] = None
        self._status_char_handle: Optional[int] = None

        # Callbacks
        self._state_callback: Optional[Callable[[ConnectionState], None]] = None
        self._host_found_callback: Optional[Callable[[DiscoveredHost], None]] = None
        self._status_callback: Optional[Callable[[StatusReport], None]] = None
        self._disconnected_callback: Optional[Callable[[], None]] = None

        # Scanning control
        self._scanner: Optional[BleakScanner] = None
        self._scan_task: Optional[asyncio.Task] = None

    # ========================================================================
    # Properties
    # ========================================================================

    @property
    def state(self) -> ConnectionState:
        """Current connection state"""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected to a host"""
        return self._state == ConnectionState.CONNECTED and self._client is not None

    @property
    def connected_host(self) -> Optional[DiscoveredHost]:
        """Get connected host info"""
        return self._connected_host if self.is_connected else None

    @property
    def discovered_hosts(self) -> list[DiscoveredHost]:
        """Get list of discovered hosts"""
        return list(self._discovered_hosts.values())

    # ========================================================================
    # Callbacks
    # ========================================================================

    def on_state_change(self, callback: Callable[[ConnectionState], None]) -> None:
        """Register callback for state changes"""
        self._state_callback = callback

    def on_host_found(self, callback: Callable[[DiscoveredHost], None]) -> None:
        """Register callback for discovered hosts"""
        self._host_found_callback = callback

    def on_status(self, callback: Callable[[StatusReport], None]) -> None:
        """Register callback for status reports from host"""
        self._status_callback = callback

    def on_disconnected(self, callback: Callable[[], None]) -> None:
        """Register callback for disconnection"""
        self._disconnected_callback = callback

    def _set_state(self, state: ConnectionState) -> None:
        """Update state and notify callback"""
        if self._state != state:
            logger.debug(f"State: {self._state.name} -> {state.name}")
            self._state = state
            if self._state_callback:
                self._state_callback(state)

    # ========================================================================
    # Scanning
    # ========================================================================

    def _detection_callback(
        self,
        device: BLEDevice,
        advertisement_data: BleakAdvertisementData
    ) -> None:
        """Called when a BLE device is detected during scanning"""
        # Check if this is a USBridge Host
        service_uuids = advertisement_data.service_uuids or []

        # Normalize UUIDs for comparison (lowercase, no dashes sometimes)
        normalized_uuids = [uuid.lower() for uuid in service_uuids]

        if USBRIDGE_SERVICE_UUID.lower() not in normalized_uuids:
            # Not a USBridge device
            return

        # It's a USBridge device - check if it's a Host
        # For now, accept any USBridge device (we'll refine this later)
        name = device.name or advertisement_data.local_name or "Unknown"
        rssi = advertisement_data.rssi or -100

        host = DiscoveredHost(
            address=device.address,
            name=name,
            rssi=rssi,
            device=device
        )

        # Track this host
        is_new = device.address not in self._discovered_hosts
        self._discovered_hosts[device.address] = host

        if is_new:
            logger.info(f"Discovered host: {host}")
            if self._host_found_callback:
                self._host_found_callback(host)

    async def start_scan(self, duration: float = 10.0) -> list[DiscoveredHost]:
        """
        Scan for USBridge Host devices.

        Args:
            duration: How long to scan in seconds

        Returns:
            List of discovered hosts
        """
        if self._state not in (ConnectionState.IDLE, ConnectionState.ERROR):
            logger.warning(f"Cannot scan in state {self._state.name}")
            return []

        self._set_state(ConnectionState.SCANNING)
        self._discovered_hosts.clear()

        logger.info(f"Starting BLE scan for {duration}s...")

        try:
            self._scanner = BleakScanner(
                detection_callback=self._detection_callback,
                service_uuids=[USBRIDGE_SERVICE_UUID]
            )

            await self._scanner.start()
            await asyncio.sleep(duration)
            await self._scanner.stop()

            logger.info(f"Scan complete. Found {len(self._discovered_hosts)} host(s)")
            return self.discovered_hosts

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            self._set_state(ConnectionState.ERROR)
            return []

        finally:
            self._scanner = None
            if self._state == ConnectionState.SCANNING:
                self._set_state(ConnectionState.IDLE)

    async def stop_scan(self) -> None:
        """Stop an ongoing scan"""
        if self._scanner:
            await self._scanner.stop()
            self._scanner = None
        if self._state == ConnectionState.SCANNING:
            self._set_state(ConnectionState.IDLE)

    # ========================================================================
    # Connection
    # ========================================================================

    def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle unexpected disconnection"""
        logger.warning("Disconnected from host")
        self._client = None
        self._connected_host = None
        self._hid_char_handle = None
        self._status_char_handle = None
        self._set_state(ConnectionState.IDLE)

        if self._disconnected_callback:
            self._disconnected_callback()

    def _handle_status_notification(
        self,
        sender: int,
        data: bytearray
    ) -> None:
        """Handle status notification from host"""
        try:
            status = StatusReport.from_bytes(bytes(data))
            logger.debug(f"Status from host: {status}")
            if self._status_callback:
                self._status_callback(status)
        except Exception as e:
            logger.error(f"Failed to parse status: {e}")

    async def connect(self, host: DiscoveredHost) -> bool:
        """
        Connect to a USBridge Host.

        Args:
            host: The host to connect to

        Returns:
            True if connection succeeded
        """
        if self._state == ConnectionState.CONNECTED:
            logger.warning("Already connected")
            return False

        if self._state not in (ConnectionState.IDLE, ConnectionState.ERROR):
            logger.warning(f"Cannot connect in state {self._state.name}")
            return False

        self._set_state(ConnectionState.CONNECTING)
        logger.info(f"Connecting to {host}...")

        try:
            self._client = BleakClient(
                host.device,
                disconnected_callback=self._handle_disconnect
            )

            # Connect with timeout
            await asyncio.wait_for(
                self._client.connect(),
                timeout=10.0
            )

            if not self._client.is_connected:
                raise Exception("Connection failed")

            logger.info("Connected! Discovering services...")

            # Discover services
            services = self._client.services

            # Find our characteristics
            for service in services:
                if service.uuid.lower() == USBRIDGE_SERVICE_UUID.lower():
                    logger.debug(f"Found USBridge service: {service.uuid}")
                    for char in service.characteristics:
                        if char.uuid.lower() == USBRIDGE_HID_CHAR_UUID.lower():
                            self._hid_char_handle = char.handle
                            logger.debug(f"Found HID characteristic: {char.uuid}")
                        elif char.uuid.lower() == USBRIDGE_STATUS_CHAR_UUID.lower():
                            self._status_char_handle = char.handle
                            logger.debug(f"Found Status characteristic: {char.uuid}")

            if not self._hid_char_handle:
                raise Exception("HID characteristic not found")

            # Subscribe to status notifications if available
            if self._status_char_handle:
                try:
                    await self._client.start_notify(
                        USBRIDGE_STATUS_CHAR_UUID,
                        self._handle_status_notification
                    )
                    logger.debug("Subscribed to status notifications")
                except Exception as e:
                    logger.warning(f"Could not subscribe to status: {e}")

            self._connected_host = host
            self._set_state(ConnectionState.CONNECTED)
            logger.info(f"Connected to {host.name}")
            return True

        except asyncio.TimeoutError:
            logger.error("Connection timed out")
            self._set_state(ConnectionState.ERROR)
            return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._set_state(ConnectionState.ERROR)
            if self._client:
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
                self._client = None
            return False

    async def connect_by_address(self, address: str) -> bool:
        """
        Connect to a host by MAC address.

        Will scan briefly if the host isn't already discovered.
        """
        # Check if already discovered
        if address in self._discovered_hosts:
            return await self.connect(self._discovered_hosts[address])

        # Quick scan to find the device
        logger.info(f"Scanning for {address}...")
        await self.start_scan(duration=5.0)

        if address in self._discovered_hosts:
            return await self.connect(self._discovered_hosts[address])

        logger.error(f"Host {address} not found")
        return False

    async def disconnect(self) -> None:
        """Disconnect from the current host"""
        if self._client and self._client.is_connected:
            self._set_state(ConnectionState.DISCONNECTING)
            logger.info("Disconnecting...")

            try:
                await self._client.disconnect()
            except Exception as e:
                logger.error(f"Disconnect error: {e}")

            self._client = None
            self._connected_host = None
            self._hid_char_handle = None
            self._status_char_handle = None

        self._set_state(ConnectionState.IDLE)

    # ========================================================================
    # HID Operations
    # ========================================================================

    async def send_hid_report(self, report: KeyboardReport) -> bool:
        """
        Send a keyboard HID report to the connected host.

        Args:
            report: The keyboard report to send

        Returns:
            True if sent successfully
        """
        if not self.is_connected or not self._client:
            logger.warning("Not connected, cannot send HID report")
            return False

        if not self._hid_char_handle:
            logger.error("HID characteristic not discovered")
            return False

        try:
            data = report.to_bytes()
            # Use write without response for lower latency
            await self._client.write_gatt_char(
                USBRIDGE_HID_CHAR_UUID,
                data,
                response=False
            )
            logger.debug(f"Sent HID report: {report}")
            return True

        except Exception as e:
            logger.error(f"Failed to send HID report: {e}")
            return False

    async def send_hid_bytes(self, data: bytes) -> bool:
        """
        Send raw HID report bytes to the connected host.

        Args:
            data: Raw 8-byte HID report

        Returns:
            True if sent successfully
        """
        if not self.is_connected or not self._client:
            return False

        try:
            await self._client.write_gatt_char(
                USBRIDGE_HID_CHAR_UUID,
                data,
                response=False
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send HID bytes: {e}")
            return False


# ============================================================================
# Testing / CLI
# ============================================================================

async def main():
    """Test the BLE Central"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )

    central = BLECentral()

    def on_state(state: ConnectionState):
        print(f"State: {state.name}")

    def on_host_found(host: DiscoveredHost):
        print(f"Found: {host}")

    def on_status(status: StatusReport):
        print(f"Status: {status}")

    central.on_state_change(on_state)
    central.on_host_found(on_host_found)
    central.on_status(on_status)

    print("BLE Central Test")
    print("Scanning for USBridge hosts...")
    print()

    hosts = await central.start_scan(duration=10.0)

    if not hosts:
        print("No hosts found.")
        print()
        print("To test, you'll need a USBridge Host device advertising")
        print(f"the service UUID: {USBRIDGE_SERVICE_UUID}")
        return

    print(f"\nFound {len(hosts)} host(s):")
    for i, host in enumerate(hosts):
        print(f"  [{i}] {host}")

    print("\nConnecting to first host...")
    if await central.connect(hosts[0]):
        print("Connected! Press Ctrl+C to disconnect.")

        # Send a test report
        report = KeyboardReport(modifier=0, keycodes=(0x04, 0, 0, 0, 0, 0))  # 'a'
        await central.send_hid_report(report)
        print(f"Sent test report: {report}")

        # Release
        report = KeyboardReport()
        await central.send_hid_report(report)
        print("Sent release report")

        try:
            while central.is_connected:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

        await central.disconnect()
    else:
        print("Connection failed!")


if __name__ == '__main__':
    asyncio.run(main())
