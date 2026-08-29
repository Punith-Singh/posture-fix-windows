"""
BLE Service — Bluetooth Low Energy device connection via bleak.

Handles scanning, connecting, and receiving data from a generic BLE IMU sensor.
Also provides a demo mode that simulates realistic pitch data.
"""

import asyncio
import time
import random
import math
from bleak import BleakScanner, BleakClient
from typing import Callable, Optional


class BLEService:
    def __init__(self):
        self.device_name: str = "My IMU Sensor"
        self.char_uuid: str = "00002a37-0000-1000-8000-00805f9b34fb"
        self.demo_mode: bool = True
        self.is_connected: bool = False
        self.status_text: str = "Idle"
        self.on_pitch: Optional[Callable[[float], None]] = None
        self.on_status_change: Optional[Callable[[str], None]] = None

        self._running = False
        self._demo_pitch = 0.0
        self._demo_time = 0.0

    def _set_status(self, text: str):
        self.status_text = text
        if self.on_status_change:
            self.on_status_change(text)

    def start(self):
        self._running = True

    def stop(self):
        self._running = False
        self.is_connected = False
        self._set_status("Stopped")

    async def run_loop(self):
        """Main async loop. Runs forever, handling connect/disconnect/demo."""
        while True:
            if not self._running:
                if self.status_text != "Stopped":
                    self._set_status("Stopped")
                await asyncio.sleep(0.5)
                continue

            if self.demo_mode:
                await self._run_demo()
            else:
                await self._run_real()

    async def _run_demo(self):
        """Simulate realistic head pitch data with clear slouch episodes."""
        self.is_connected = True
        self._set_status("Running (Demo Mode)")
        self._demo_time = time.time()

        while self._running and self.demo_mode:
            t = time.time() - self._demo_time

            # Small baseline wander and sensor noise
            base_wander = 1.5 * math.sin(t * 0.08)
            noise = random.gauss(0, 0.3)

            # Slouch episodes: every 20 seconds, slouch for 10 seconds
            # Peak at 25° which is well above the 15° default threshold
            cycle = t % 20.0
            if 8.0 < cycle < 18.0:
                # Ramp up quickly, hold, ramp down
                phase = (cycle - 8.0) / 10.0  # 0.0 to 1.0
                if phase < 0.15:
                    # Quick ramp up (1.5 seconds)
                    slouch = 25.0 * (phase / 0.15)
                elif phase > 0.85:
                    # Quick ramp down (1.5 seconds)
                    slouch = 25.0 * ((1.0 - phase) / 0.15)
                else:
                    # Sustained slouch with small variation
                    slouch = 25.0 + random.gauss(0, 1.0)
            else:
                slouch = 0.0

            pitch = base_wander + noise + slouch

            if self.on_pitch:
                self.on_pitch(pitch)

            await asyncio.sleep(0.1)  # 10 Hz sample rate

        self.is_connected = False

    async def _run_real(self):
        """Scan for and connect to a real BLE device."""
        try:
            self._set_status(f"Scanning for '{self.device_name}'...")
            devices = await BleakScanner.discover(timeout=5.0)
            target = next(
                (d for d in devices if self.device_name.lower() in (d.name or "").lower()),
                None
            )

            if target is None:
                self._set_status(f"'{self.device_name}' not found. Retrying...")
                await asyncio.sleep(3)
                return

            self._set_status(f"Connecting to {target.name}...")
            async with BleakClient(target) as client:
                self.is_connected = True
                self._set_status(f"Connected: {target.name}")

                def handle_data(sender, data: bytearray):
                    try:
                        # Decode pitch from raw bytes — adjust per your device protocol
                        if len(data) >= 2:
                            raw = int.from_bytes(data[0:2], byteorder='little', signed=True)
                            pitch = raw / 100.0  # e.g. centidegrees
                        else:
                            pitch = float(data[0])
                        if self.on_pitch:
                            self.on_pitch(pitch)
                    except Exception as e:
                        print(f"Data parse error: {e}")

                await client.start_notify(self.char_uuid, handle_data)

                while self._running and client.is_connected:
                    await asyncio.sleep(0.5)

                try:
                    await client.stop_notify(self.char_uuid)
                except Exception:
                    pass

                self.is_connected = False
                self._set_status("Disconnected")

        except Exception as e:
            print(f"BLE Error: {e}")
            self.is_connected = False
            self._set_status(f"BLE Error: {e}")
            await asyncio.sleep(5)
