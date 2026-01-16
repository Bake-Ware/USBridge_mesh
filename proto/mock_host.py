#!/usr/bin/env python3
"""
Mock USBridge Host (BLE Peripheral)

A test peripheral that advertises as a USBridge Host and receives
HID reports. Used for testing the Terminal without real hardware.

This uses the BlueZ D-Bus API to create a GATT server.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method, dbus_property
from dbus_fast import Variant, DBusError

try:
    from .protocol import (
        USBRIDGE_SERVICE_UUID,
        USBRIDGE_HID_CHAR_UUID,
        USBRIDGE_STATUS_CHAR_UUID,
        KeyboardReport,
    )
except ImportError:
    from protocol import (
        USBRIDGE_SERVICE_UUID,
        USBRIDGE_HID_CHAR_UUID,
        USBRIDGE_STATUS_CHAR_UUID,
        KeyboardReport,
    )

logger = logging.getLogger(__name__)

# BlueZ D-Bus constants
BLUEZ_SERVICE = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
ADAPTER_IFACE = 'org.bluez.Adapter1'


# ============================================================================
# GATT Application
# ============================================================================

class GattCharacteristic(ServiceInterface):
    """Base class for GATT characteristics"""

    def __init__(self, uuid: str, flags: list[str], service_path: str, index: int):
        self._uuid = uuid
        self._flags = flags
        self._service_path = service_path
        self._path = f"{service_path}/char{index}"
        self._value = bytes()
        super().__init__('org.bluez.GattCharacteristic1')

    @property
    def path(self) -> str:
        return self._path

    @dbus_property()
    def UUID(self) -> 's':
        return self._uuid

    @dbus_property()
    def Service(self) -> 'o':
        return self._service_path

    @dbus_property()
    def Flags(self) -> 'as':
        return self._flags

    @method()
    def ReadValue(self, options: 'a{sv}') -> 'ay':
        return list(self._value)

    @method()
    def WriteValue(self, value: 'ay', options: 'a{sv}') -> None:
        self._value = bytes(value)


class HIDCharacteristic(GattCharacteristic):
    """HID Report Characteristic - receives keyboard reports from Terminal"""

    def __init__(self, service_path: str, index: int, callback=None):
        super().__init__(
            USBRIDGE_HID_CHAR_UUID,
            ['write-without-response', 'write'],
            service_path,
            index
        )
        self._callback = callback

    @method()
    def WriteValue(self, value: 'ay', options: 'a{sv}') -> None:
        self._value = bytes(value)
        logger.debug(f"Received HID: {self._value.hex()}")

        if self._callback:
            try:
                report = KeyboardReport.from_bytes(self._value)
                self._callback(report)
            except Exception as e:
                logger.error(f"Failed to parse HID report: {e}")


class StatusCharacteristic(GattCharacteristic):
    """Status Characteristic - sends status updates to Terminal"""

    def __init__(self, service_path: str, index: int):
        super().__init__(
            USBRIDGE_STATUS_CHAR_UUID,
            ['read', 'notify'],
            service_path,
            index
        )
        # Default status: connected
        self._value = bytes([1, 100, 0, 0])  # connected, 100%, 0ms latency


class GattService(ServiceInterface):
    """USBridge GATT Service"""

    def __init__(self, path: str, uuid: str, primary: bool = True):
        self._path = path
        self._uuid = uuid
        self._primary = primary
        self._characteristics: list[GattCharacteristic] = []
        super().__init__('org.bluez.GattService1')

    @property
    def path(self) -> str:
        return self._path

    def add_characteristic(self, char: GattCharacteristic) -> None:
        self._characteristics.append(char)

    @dbus_property()
    def UUID(self) -> 's':
        return self._uuid

    @dbus_property()
    def Primary(self) -> 'b':
        return self._primary


class GattApplication(ServiceInterface):
    """GATT Application containing services"""

    def __init__(self, path: str):
        self._path = path
        self._services: list[GattService] = []
        super().__init__('org.freedesktop.DBus.ObjectManager')

    @property
    def path(self) -> str:
        return self._path

    def add_service(self, service: GattService) -> None:
        self._services.append(service)

    @method()
    def GetManagedObjects(self) -> 'a{oa{sa{sv}}}':
        """Return all managed objects for BlueZ"""
        objects = {}

        for service in self._services:
            objects[service.path] = {
                'org.bluez.GattService1': {
                    'UUID': Variant('s', service._uuid),
                    'Primary': Variant('b', service._primary),
                }
            }

            for char in service._characteristics:
                objects[char.path] = {
                    'org.bluez.GattCharacteristic1': {
                        'UUID': Variant('s', char._uuid),
                        'Service': Variant('o', char._service_path),
                        'Flags': Variant('as', char._flags),
                    }
                }

        return objects


# ============================================================================
# BLE Advertisement
# ============================================================================

class Advertisement(ServiceInterface):
    """BLE Advertisement"""

    def __init__(self, path: str, ad_type: str, local_name: str):
        self._path = path
        self._type = ad_type
        self._local_name = local_name
        self._service_uuids = [USBRIDGE_SERVICE_UUID]
        self._manufacturer_data = {}
        self._service_data = {}
        self._include_tx_power = True
        super().__init__('org.bluez.LEAdvertisement1')

    @property
    def path(self) -> str:
        return self._path

    @dbus_property()
    def Type(self) -> 's':
        return self._type

    @dbus_property()
    def ServiceUUIDs(self) -> 'as':
        return self._service_uuids

    @dbus_property()
    def LocalName(self) -> 's':
        return self._local_name

    @dbus_property()
    def IncludeTxPower(self) -> 'b':
        return self._include_tx_power

    @method()
    def Release(self) -> None:
        logger.info("Advertisement released")


# ============================================================================
# Mock Host Application
# ============================================================================

class MockHost:
    """
    Mock USBridge Host

    Creates a BLE peripheral that advertises and accepts HID reports.
    """

    def __init__(self, device_name: str = "USBridge-Host"):
        self._device_name = device_name
        self._bus: Optional[MessageBus] = None
        self._adapter_path: Optional[str] = None

        # GATT objects
        self._app: Optional[GattApplication] = None
        self._service: Optional[GattService] = None
        self._hid_char: Optional[HIDCharacteristic] = None
        self._status_char: Optional[StatusCharacteristic] = None
        self._advertisement: Optional[Advertisement] = None

        # Callbacks
        self._hid_callback = None

    def on_hid_report(self, callback) -> None:
        """Register callback for received HID reports"""
        self._hid_callback = callback

    async def _find_adapter(self) -> str:
        """Find the Bluetooth adapter"""
        introspection = await self._bus.introspect(BLUEZ_SERVICE, '/')
        obj = self._bus.get_proxy_object(BLUEZ_SERVICE, '/', introspection)

        # Get ObjectManager interface
        om = obj.get_interface('org.freedesktop.DBus.ObjectManager')
        objects = await om.call_get_managed_objects()

        for path, interfaces in objects.items():
            if GATT_MANAGER_IFACE in interfaces:
                logger.info(f"Found adapter: {path}")
                return path

        raise Exception("No Bluetooth adapter found")

    async def _setup_gatt(self) -> None:
        """Set up GATT services"""
        app_path = '/org/usbridge/host'
        service_path = f'{app_path}/service0'

        # Create application
        self._app = GattApplication(app_path)

        # Create service
        self._service = GattService(service_path, USBRIDGE_SERVICE_UUID)
        self._app.add_service(self._service)

        # Create characteristics
        self._hid_char = HIDCharacteristic(
            service_path, 0,
            callback=self._hid_callback
        )
        self._service.add_characteristic(self._hid_char)

        self._status_char = StatusCharacteristic(service_path, 1)
        self._service.add_characteristic(self._status_char)

        # Export objects to D-Bus
        self._bus.export(app_path, self._app)
        self._bus.export(service_path, self._service)
        self._bus.export(self._hid_char.path, self._hid_char)
        self._bus.export(self._status_char.path, self._status_char)

        # Register with BlueZ
        introspection = await self._bus.introspect(BLUEZ_SERVICE, self._adapter_path)
        adapter_obj = self._bus.get_proxy_object(
            BLUEZ_SERVICE, self._adapter_path, introspection
        )
        gatt_manager = adapter_obj.get_interface(GATT_MANAGER_IFACE)

        await gatt_manager.call_register_application(app_path, {})
        logger.info("GATT application registered")

    async def _setup_advertisement(self) -> None:
        """Set up BLE advertisement"""
        ad_path = '/org/usbridge/host/advertisement0'

        self._advertisement = Advertisement(
            ad_path, 'peripheral', self._device_name
        )

        # Export to D-Bus
        self._bus.export(ad_path, self._advertisement)

        # Register with BlueZ
        introspection = await self._bus.introspect(BLUEZ_SERVICE, self._adapter_path)
        adapter_obj = self._bus.get_proxy_object(
            BLUEZ_SERVICE, self._adapter_path, introspection
        )
        ad_manager = adapter_obj.get_interface(LE_ADVERTISING_MANAGER_IFACE)

        await ad_manager.call_register_advertisement(ad_path, {})
        logger.info("Advertisement registered")

    async def start(self) -> None:
        """Start the mock host"""
        print(f"Starting Mock Host: {self._device_name}")
        print("=" * 50)

        # Connect to D-Bus
        self._bus = await MessageBus(bus_type=2).connect()  # System bus
        logger.info("Connected to D-Bus")

        # Find adapter
        self._adapter_path = await self._find_adapter()

        # Set up GATT
        await self._setup_gatt()

        # Set up advertisement
        await self._setup_advertisement()

        print(f"\nMock Host is advertising as '{self._device_name}'")
        print(f"Service UUID: {USBRIDGE_SERVICE_UUID}")
        print("\nWaiting for connections...")
        print("Press Ctrl+C to stop.\n")

    async def stop(self) -> None:
        """Stop the mock host"""
        if self._bus:
            try:
                # Unregister advertisement
                if self._advertisement and self._adapter_path:
                    introspection = await self._bus.introspect(
                        BLUEZ_SERVICE, self._adapter_path
                    )
                    adapter_obj = self._bus.get_proxy_object(
                        BLUEZ_SERVICE, self._adapter_path, introspection
                    )
                    ad_manager = adapter_obj.get_interface(LE_ADVERTISING_MANAGER_IFACE)
                    await ad_manager.call_unregister_advertisement(
                        self._advertisement.path
                    )

                # Unregister GATT application
                if self._app and self._adapter_path:
                    gatt_manager = adapter_obj.get_interface(GATT_MANAGER_IFACE)
                    await gatt_manager.call_unregister_application(self._app.path)

            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

            self._bus.disconnect()
            self._bus = None

    async def run(self) -> None:
        """Run the mock host forever"""
        await self.start()

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()


# ============================================================================
# Main
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Mock USBridge Host - BLE peripheral for testing"
    )
    parser.add_argument(
        '-n', '--name',
        default='USBridge-Host',
        help='Device name (default: USBridge-Host)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Setup logging
    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )

    # Create mock host
    host = MockHost(device_name=args.name)

    # HID report callback
    def on_hid(report: KeyboardReport):
        print(f"Received: {report}")

    host.on_hid_report(on_hid)

    # Handle signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def shutdown():
        print("\nShutting down...")
        await host.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    try:
        loop.run_until_complete(host.run())
    except KeyboardInterrupt:
        loop.run_until_complete(shutdown())
    finally:
        loop.close()


if __name__ == '__main__':
    main()
