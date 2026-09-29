"""ADB device wrapper: screencap, tap, swipe — human-like timing included."""
from __future__ import annotations
import logging
import os
import random
import subprocess
import time

log = logging.getLogger("coc.adb")
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class AdbDevice:
    def __init__(self, serial: str = "", adb_bin: str = "adb"):
        self.serial = (serial or "").strip()
        self.adb_bin = adb_bin
        if not self.serial:
            self.serial = self._first_device()

    # ---------- setup ----------
    def _base(self) -> list[str]:
        cmd = [self.adb_bin]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    @classmethod
    def list_devices(cls, adb_bin: str = "adb") -> list[dict[str, str]]:
        """Return list of connected ADB devices: [{'serial': '...', 'state': 'device'}]."""
        try:
            out = subprocess.run(
                [adb_bin, "devices"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=SUBPROCESS_FLAGS,
            )
            devices = []
            for line in out.stdout.splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    devices.append({"serial": parts[0], "state": parts[1]})
            return devices
        except Exception as e:
            log.warning("Failed to list ADB devices: %s", e)
            return []

    @classmethod
    def connect_device(cls, address: str, adb_bin: str = "adb") -> tuple[bool, str]:
        """Connect to network ADB target e.g. 127.0.0.1:5555."""
        if not address:
            return False, "Address cannot be empty"
        try:
            r = subprocess.run(
                [adb_bin, "connect", address],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=SUBPROCESS_FLAGS,
            )
            msg = (r.stdout or r.stderr or "").strip()
            ok = "connected to" in msg.lower() or "already connected" in msg.lower()
            return ok, msg
        except Exception as e:
            return False, str(e)

    @classmethod
    def disconnect_device(cls, address: str = "", adb_bin: str = "adb") -> tuple[bool, str]:
        """Disconnect ADB target."""
        try:
            cmd = [adb_bin, "disconnect"]
            if address:
                cmd.append(address)
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=SUBPROCESS_FLAGS,
            )
            msg = (r.stdout or r.stderr or "").strip()
            return True, msg
        except Exception as e:
            return False, str(e)

    def _first_device(self) -> str:
        devs = self.list_devices(self.adb_bin)
        for d in devs:
            if d.get("state") == "device":
                return d["serial"]
        return ""

    def ensure_connected(self) -> bool:
        """Verify device is truly available and responding in 'device' state."""
        devs = self.list_devices(self.adb_bin)
        online = {d["serial"]: d["state"] for d in devs}
        if self.serial and online.get(self.serial) == "device":
            return True
        # If specified serial is absent or offline, try finding first active device
        active = [s for s, st in online.items() if st == "device"]
        if active:
            self.serial = active[0]
            log.info("Auto-selected ADB device: %s", self.serial)
            return True
        return False

    # ---------- primitives ----------
    def screencap(self) -> bytes:
        """Return PNG bytes of current screen (works for any emulator/phone)."""
        r = subprocess.run(
            self._base() + ["exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=20,
            creationflags=SUBPROCESS_FLAGS,
        )
        data = r.stdout
        if not data or len(data) < 5000:
            raise RuntimeError(
                f"screencap failed (got {len(data) if data else 0} bytes). "
                f"Is emulator/CoC open? serial={self.serial!r}"
            )
        # Normalise potential CRLF line-ending corruption on Windows
        if not data.startswith(b"\x89PNG"):
            idx = data.find(b"\x89PNG")
            if idx != -1:
                data = data[idx:]
            else:
                data = data.replace(b"\r\r\n", b"\n").replace(b"\r\n", b"\n")
        return data

    def tap(self, x: int, y: int, jitter: int = 4):
        if jitter:
            x += random.randint(-jitter, jitter)
            y += random.randint(-jitter, jitter)
        subprocess.run(
            self._base() + ["shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            timeout=10,
            creationflags=SUBPROCESS_FLAGS,
        )

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300):
        subprocess.run(
            self._base() + ["shell", "input", "swipe",
                            str(x1), str(y1), str(x2), str(y2), str(ms)],
            capture_output=True,
            timeout=10,
            creationflags=SUBPROCESS_FLAGS,
        )

    def shell(self, command: str, timeout: int = 15) -> str:
        """Run an arbitrary `adb shell` command. Returns stdout (best effort)."""
        r = subprocess.run(
            self._base() + ["shell", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=SUBPROCESS_FLAGS,
        )
        return (r.stdout or "").strip()

    def keyevent(self, code: int):
        """Send an Android keyevent (4=BACK, 3=HOME)."""
        subprocess.run(
            self._base() + ["shell", "input", "keyevent", str(code)],
            capture_output=True,
            timeout=10,
            creationflags=SUBPROCESS_FLAGS,
        )

    def sleep(self, lo: float, hi: float | None = None):
        time.sleep(random.uniform(lo, hi) if hi else lo)
