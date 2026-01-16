#!/usr/bin/env python3
"""
USBridge Terminal - CLI Implementation

A terminal device that reads HID input from USB keyboards and
forwards it to connected USBridge Host devices over BLE.
"""

import asyncio
import argparse
import logging
import sys
from typing import Optional

try:
    from .protocol import KeyboardReport, DeviceType
    from .hid_input import HIDInputReader
    from .ble_central import BLECentral, ConnectionState, DiscoveredHost
except ImportError:
    from protocol import KeyboardReport, DeviceType
    from hid_input import HIDInputReader
    from ble_central import BLECentral, ConnectionState, DiscoveredHost

logger = logging.getLogger(__name__)


# ============================================================================
# Terminal Application
# ============================================================================

class Terminal:
    """
    USBridge Terminal Application

    Coordinates HID input reading and BLE communication to forward
    keyboard input to remote hosts.
    """

    def __init__(
        self,
        device_name: str = "USBridge-Terminal",
        auto_connect: bool = True,
        auto_scan: bool = True,
    ):
        self._device_name = device_name
        self._auto_connect = auto_connect
        self._auto_scan = auto_scan

        # Components
        self._hid_reader = HIDInputReader()
        self._ble_central = BLECentral(device_name)

        # Statistics
        self._reports_sent = 0
        self._reports_failed = 0

        # Setup callbacks
        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        """Wire up component callbacks"""
        # HID reader callbacks
        self._hid_reader.on_report(self._on_hid_report)
        self._hid_reader.on_device_added(self._on_device_added)
        self._hid_reader.on_device_removed(self._on_device_removed)

        # BLE central callbacks
        self._ble_central.on_state_change(self._on_state_change)
        self._ble_central.on_host_found(self._on_host_found)
        self._ble_central.on_disconnected(self._on_disconnected)

    # ========================================================================
    # HID Callbacks
    # ========================================================================

    def _on_hid_report(self, report: KeyboardReport) -> None:
        """Handle HID report from keyboard"""
        if not self._ble_central.is_connected:
            return

        # Queue the report for sending (we're in sync callback, need async)
        asyncio.create_task(self._send_report(report))

    async def _send_report(self, report: KeyboardReport) -> None:
        """Send HID report over BLE"""
        success = await self._ble_central.send_hid_report(report)
        if success:
            self._reports_sent += 1
        else:
            self._reports_failed += 1

    def _on_device_added(self, path: str, name: str) -> None:
        """Handle keyboard connected"""
        print(f"[+] Keyboard connected: {name}")

    def _on_device_removed(self, path: str) -> None:
        """Handle keyboard disconnected"""
        print(f"[-] Keyboard disconnected: {path}")

    # ========================================================================
    # BLE Callbacks
    # ========================================================================

    def _on_state_change(self, state: ConnectionState) -> None:
        """Handle BLE state change"""
        state_symbols = {
            ConnectionState.IDLE: "○",
            ConnectionState.SCANNING: "◌",
            ConnectionState.CONNECTING: "◐",
            ConnectionState.CONNECTED: "●",
            ConnectionState.DISCONNECTING: "◑",
            ConnectionState.ERROR: "✗",
        }
        symbol = state_symbols.get(state, "?")
        print(f"[{symbol}] State: {state.name}")

    def _on_host_found(self, host: DiscoveredHost) -> None:
        """Handle discovered host"""
        print(f"    Found host: {host.name} ({host.address}) [{host.rssi}dBm]")

    def _on_disconnected(self) -> None:
        """Handle disconnection from host"""
        print("[!] Disconnected from host")

        # Auto-reconnect if enabled
        if self._auto_scan:
            print("    Will auto-scan for hosts...")
            asyncio.create_task(self._auto_scan_and_connect())

    async def _auto_scan_and_connect(self) -> None:
        """Scan and connect to first available host"""
        await asyncio.sleep(2.0)  # Brief delay before reconnect

        hosts = await self._ble_central.start_scan(duration=5.0)
        if hosts and self._auto_connect:
            # Connect to host with best signal
            best_host = max(hosts, key=lambda h: h.rssi)
            print(f"    Auto-connecting to {best_host.name}...")
            await self._ble_central.connect(best_host)

    # ========================================================================
    # Public API
    # ========================================================================

    async def scan(self, duration: float = 10.0) -> list[DiscoveredHost]:
        """Scan for available hosts"""
        return await self._ble_central.start_scan(duration)

    async def connect(self, host: DiscoveredHost) -> bool:
        """Connect to a specific host"""
        return await self._ble_central.connect(host)

    async def connect_by_address(self, address: str) -> bool:
        """Connect to a host by address"""
        return await self._ble_central.connect_by_address(address)

    async def disconnect(self) -> None:
        """Disconnect from current host"""
        await self._ble_central.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if connected to a host"""
        return self._ble_central.is_connected

    @property
    def connected_host(self) -> Optional[DiscoveredHost]:
        """Get connected host info"""
        return self._ble_central.connected_host

    @property
    def discovered_hosts(self) -> list[DiscoveredHost]:
        """Get discovered hosts"""
        return self._ble_central.discovered_hosts

    def get_keyboards(self) -> list[tuple[str, str]]:
        """Get connected keyboards"""
        return self._hid_reader.get_devices()

    def get_stats(self) -> dict:
        """Get statistics"""
        return {
            "reports_sent": self._reports_sent,
            "reports_failed": self._reports_failed,
            "keyboards": len(self._hid_reader.get_devices()),
            "connected": self.is_connected,
            "host": self.connected_host.name if self.connected_host else None,
        }

    # ========================================================================
    # Main Loop
    # ========================================================================

    async def run(self) -> None:
        """Run the terminal"""
        print(f"USBridge Terminal: {self._device_name}")
        print("=" * 50)

        # Start HID reader in background
        hid_task = asyncio.create_task(self._hid_reader.run())

        # Initial scan if enabled
        if self._auto_scan:
            print("\nScanning for hosts...")
            hosts = await self._ble_central.start_scan(duration=5.0)

            if hosts and self._auto_connect:
                best_host = max(hosts, key=lambda h: h.rssi)
                print(f"\nAuto-connecting to {best_host.name}...")
                await self._ble_central.connect(best_host)
            elif not hosts:
                print("\nNo hosts found. Waiting for hosts...")

        print("\nTerminal running. Press Ctrl+C to exit.")
        print("Plug in a USB keyboard to forward input.\n")

        try:
            # Main loop - just keep running
            while True:
                await asyncio.sleep(1.0)

                # Periodic status (every 10 seconds if connected)
                # Could add more status reporting here

        except asyncio.CancelledError:
            pass

        finally:
            print("\nShutting down...")
            self._hid_reader.stop()
            await self._ble_central.disconnect()
            hid_task.cancel()
            try:
                await hid_task
            except asyncio.CancelledError:
                pass


# ============================================================================
# Interactive CLI
# ============================================================================

class InteractiveCLI:
    """
    Interactive command-line interface for the Terminal.

    Provides commands for scanning, connecting, and monitoring.
    """

    def __init__(self, terminal: Terminal):
        self._terminal = terminal
        self._running = False

    def _print_help(self) -> None:
        """Print available commands"""
        print("""
Commands:
  scan [duration]  - Scan for hosts (default 10s)
  list             - List discovered hosts
  connect <n>      - Connect to host by index
  connect <addr>   - Connect to host by MAC address
  disconnect       - Disconnect from current host
  status           - Show current status
  keyboards        - List connected keyboards
  quit / exit      - Exit the terminal
  help             - Show this help
""")

    def _print_status(self) -> None:
        """Print current status"""
        stats = self._terminal.get_stats()
        host = self._terminal.connected_host

        print(f"\nStatus:")
        print(f"  Connected: {'Yes' if stats['connected'] else 'No'}")
        if host:
            print(f"  Host: {host.name} ({host.address})")
        print(f"  Keyboards: {stats['keyboards']}")
        print(f"  Reports sent: {stats['reports_sent']}")
        print(f"  Reports failed: {stats['reports_failed']}")

    def _print_keyboards(self) -> None:
        """Print connected keyboards"""
        keyboards = self._terminal.get_keyboards()
        if not keyboards:
            print("\nNo keyboards connected.")
            print("Plug in a USB keyboard to start forwarding.")
        else:
            print(f"\nConnected keyboards ({len(keyboards)}):")
            for path, name in keyboards:
                print(f"  {name} ({path})")

    def _print_hosts(self) -> None:
        """Print discovered hosts"""
        hosts = self._terminal.discovered_hosts
        if not hosts:
            print("\nNo hosts discovered. Run 'scan' to find hosts.")
        else:
            print(f"\nDiscovered hosts ({len(hosts)}):")
            for i, host in enumerate(hosts):
                marker = "●" if host == self._terminal.connected_host else "○"
                print(f"  [{i}] {marker} {host.name} ({host.address}) [{host.rssi}dBm]")

    async def _handle_command(self, line: str) -> bool:
        """Handle a command. Returns False to exit."""
        parts = line.strip().split()
        if not parts:
            return True

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ('quit', 'exit', 'q'):
            return False

        elif cmd == 'help':
            self._print_help()

        elif cmd == 'scan':
            duration = float(args[0]) if args else 10.0
            print(f"Scanning for {duration} seconds...")
            await self._terminal.scan(duration)
            self._print_hosts()

        elif cmd == 'list':
            self._print_hosts()

        elif cmd == 'connect':
            if not args:
                print("Usage: connect <index> or connect <mac_address>")
                return True

            arg = args[0]

            # Try as index first
            try:
                idx = int(arg)
                hosts = self._terminal.discovered_hosts
                if 0 <= idx < len(hosts):
                    print(f"Connecting to {hosts[idx].name}...")
                    success = await self._terminal.connect(hosts[idx])
                    if success:
                        print("Connected!")
                    else:
                        print("Connection failed.")
                else:
                    print(f"Invalid index. Run 'list' to see available hosts.")
                return True
            except ValueError:
                pass

            # Try as MAC address
            if ':' in arg:
                print(f"Connecting to {arg}...")
                success = await self._terminal.connect_by_address(arg)
                if success:
                    print("Connected!")
                else:
                    print("Connection failed.")
            else:
                print("Invalid argument. Use index number or MAC address.")

        elif cmd == 'disconnect':
            if self._terminal.is_connected:
                await self._terminal.disconnect()
                print("Disconnected.")
            else:
                print("Not connected.")

        elif cmd == 'status':
            self._print_status()

        elif cmd == 'keyboards':
            self._print_keyboards()

        else:
            print(f"Unknown command: {cmd}")
            print("Type 'help' for available commands.")

        return True

    async def run(self) -> None:
        """Run the interactive CLI"""
        self._running = True

        # Start terminal in background
        terminal_task = asyncio.create_task(self._terminal.run())

        print("\nInteractive mode. Type 'help' for commands.\n")

        try:
            while self._running:
                try:
                    # Read input (this is blocking, but we're in async context)
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("usbridge> ")
                    )
                    if not await self._handle_command(line):
                        break
                except EOFError:
                    break

        except asyncio.CancelledError:
            pass

        finally:
            self._running = False
            terminal_task.cancel()
            try:
                await terminal_task
            except asyncio.CancelledError:
                pass


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="USBridge Terminal - Forward HID input over BLE"
    )
    parser.add_argument(
        '-n', '--name',
        default='USBridge-Terminal',
        help='Device name (default: USBridge-Terminal)'
    )
    parser.add_argument(
        '-a', '--address',
        help='Connect to specific host MAC address'
    )
    parser.add_argument(
        '--no-auto-connect',
        action='store_true',
        help='Disable auto-connect to first host'
    )
    parser.add_argument(
        '--no-auto-scan',
        action='store_true',
        help='Disable auto-scan on startup'
    )
    parser.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='Run in interactive mode'
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

    # Create terminal
    terminal = Terminal(
        device_name=args.name,
        auto_connect=not args.no_auto_connect,
        auto_scan=not args.no_auto_scan,
    )

    # Run
    try:
        if args.interactive:
            cli = InteractiveCLI(terminal)
            asyncio.run(cli.run())
        elif args.address:
            # Connect to specific address
            async def connect_and_run():
                print(f"Connecting to {args.address}...")
                if await terminal.connect_by_address(args.address):
                    await terminal.run()
                else:
                    print("Failed to connect.")
            asyncio.run(connect_and_run())
        else:
            # Default: auto-scan and run
            asyncio.run(terminal.run())

    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == '__main__':
    main()
