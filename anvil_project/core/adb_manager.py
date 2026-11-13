"""
Anvil ADB Manager
Device tracking, low-level ADB wrapper, property extraction,
and diagnostic pre-flight sentry.
"""

import subprocess
import re
import time
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from datetime import datetime

from .exception_handler import DeviceFault, AnvilExceptionHandler


class ADBManager:
    """
    Strict ADB process isolation.
    All calls are non-blocking where possible and return clean data structures.
    """

    def __init__(self, adb_path: str = "adb", fastboot_path: str = "fastboot"):
        self.adb = adb_path
        self.fastboot = fastboot_path
        self._last_device: Optional[str] = None
        self._device_props: Dict[str, str] = {}

    def _run(self, args: List[str], timeout: int = 15, use_fastboot: bool = False) -> Tuple[int, str, str]:
        """Internal runner. Never raises; returns (rc, stdout, stderr)."""
        binary = self.fastboot if use_fastboot else self.adb
        cmd = [binary] + args
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "TIMEOUT"
        except FileNotFoundError:
            return -2, "", f"{binary} binary not found in PATH"

    def list_devices(self) -> List[Dict[str, str]]:
        """Return list of connected devices with state."""
        rc, out, err = self._run(["devices", "-l"])
        if rc != 0:
            return []
        devices = []
        for line in out.splitlines()[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
                devices.append({"serial": serial, "state": state})
        return devices

    def wait_for_device(self, timeout: int = 30) -> bool:
        """Block until a device is online or timeout."""
        rc, _, _ = self._run(["wait-for-device"], timeout=timeout)
        return rc == 0

    def get_prop(self, prop: str, serial: Optional[str] = None) -> Optional[str]:
        """Fetch a single getprop value."""
        args = ["shell", "getprop", prop]
        if serial:
            args = ["-s", serial] + args
        rc, out, _ = self._run(args)
        if rc != 0 or not out:
            return None
        return out.strip()

    def get_all_critical_props(self, serial: Optional[str] = None) -> Dict[str, str]:
        """Pull the full diagnostic property set required by Pre-Flight Sentry."""
        critical = [
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.build.version.security_patch",
            "ro.crypto.state",
            "ro.boot.flash.locked",
            "ro.product.manufacturer",
            "ro.product.model",
            "ro.product.device",
            "ro.build.fingerprint",
            "ro.secure",
            "ro.debuggable",
        ]
        props = {}
        for p in critical:
            val = self.get_prop(p, serial)
            if val is not None:
                props[p] = val
        self._device_props = props
        return props

    def is_device_ready(self) -> bool:
        devices = self.list_devices()
        return any(d["state"] == "device" for d in devices)

    def shell(self, command: str, serial: Optional[str] = None, timeout: int = 20) -> Tuple[int, str, str]:
        """Execute an adb shell command."""
        args = ["shell", command]
        if serial:
            args = ["-s", serial] + args
        return self._run(args, timeout=timeout)

    def push(self, local: str, remote: str, serial: Optional[str] = None) -> bool:
        """Push a file to the device."""
        args = ["push", local, remote]
        if serial:
            args = ["-s", serial] + args
        rc, _, _ = self._run(args, timeout=60)
        return rc == 0

    def pull(self, remote: str, local: str, serial: Optional[str] = None) -> bool:
        args = ["pull", remote, local]
        if serial:
            args = ["-s", serial] + args
        rc, _, _ = self._run(args, timeout=60)
        return rc == 0

    def reboot(self, mode: str = "", serial: Optional[str] = None) -> bool:
        """Reboot device. mode can be '', 'bootloader', 'recovery'."""
        args = ["reboot"]
        if mode:
            args.append(mode)
        if serial:
            args = ["-s", serial] + args
        rc, _, _ = self._run(args, timeout=10)
        return rc == 0

    def fastboot_devices(self) -> List[str]:
        rc, out, _ = self._run(["devices"], use_fastboot=True)
        if rc != 0:
            return []
        serials = []
        for line in out.splitlines()[1:]:
            if line.strip() and "fastboot" in line:
                serials.append(line.split()[0])
        return serials

    def fastboot_boot(self, image_path: str, serial: Optional[str] = None) -> bool:
        """Temporarily boot a recovery image into RAM."""
        args = ["boot", image_path]
        if serial:
            args = ["-s", serial] + args
        rc, _, _ = self._run(args, timeout=45, use_fastboot=True)
        return rc == 0

    def fastboot_oem_unlock(self, serial: Optional[str] = None) -> Tuple[int, str, str]:
        args = ["oem", "unlock"]
        if serial:
            args = ["-s", serial] + args
        return self._run(args, timeout=30, use_fastboot=True)

    # ------------------------------------------------------------------
    # Diagnostic Pre-Flight Sentry
    # ------------------------------------------------------------------

    def run_preflight(self, serial: Optional[str] = None) -> Dict[str, any]:
        """
        Full diagnostic sentry.
        Returns a structured report the UI can act on immediately.
        """
        report = {
            "ready": False,
            "android_version": None,
            "sdk": None,
            "security_patch": None,
            "crypto_state": None,
            "bootloader_locked": None,
            "manufacturer": None,
            "model": None,
            "root_method": None,          # "system" | "systemless" | "blocked"
            "exploit_candidate": None,    # "dirtycow" | "towelroot" | None
            "warnings": [],
            "locks": [],                  # UI elements that must be disabled
            "props": {},
        }

        if not self.is_device_ready():
            report["warnings"].append(AnvilExceptionHandler.FAULT_MAP["DEVICE_NOT_FOUND"])
            return report

        props = self.get_all_critical_props(serial)
        report["props"] = props

        # Version parsing
        release = props.get("ro.build.version.release", "0")
        sdk = props.get("ro.build.version.sdk", "0")
        report["android_version"] = release
        report["sdk"] = int(sdk) if sdk.isdigit() else 0
        report["manufacturer"] = props.get("ro.product.manufacturer", "unknown").lower()
        report["model"] = props.get("ro.product.model", "unknown")

        # Crypto state
        crypto = props.get("ro.crypto.state", "unknown")
        report["crypto_state"] = crypto
        if crypto in ("encrypted", "unsupported"):
            report["warnings"].append(AnvilExceptionHandler.FAULT_MAP["CRYPTO_ACTIVE"])
            report["locks"].append("root")

        # Bootloader lock
        locked = props.get("ro.boot.flash.locked", "0")
        report["bootloader_locked"] = locked == "1"
        if locked == "1":
            report["warnings"].append(AnvilExceptionHandler.FAULT_MAP["BOOTLOADER_LOCKED"])
            report["locks"].append("root")
            report["locks"].append("flash")

        # Security patch → exploit matrix
        patch = props.get("ro.build.version.security_patch", "2015-01-01")
        report["security_patch"] = patch
        try:
            patch_date = datetime.strptime(patch, "%Y-%m-%d")
        except ValueError:
            patch_date = datetime(2015, 1, 1)

        dirtycow_cutoff = datetime(2016, 12, 1)
        towelroot_cutoff = datetime(2015, 6, 1)

        if patch_date < dirtycow_cutoff:
            report["exploit_candidate"] = "dirtycow"
        elif patch_date < towelroot_cutoff:
            report["exploit_candidate"] = "towelroot"
        else:
            report["exploit_candidate"] = None
            report["warnings"].append("Security patch too recent for known local privilege escalation vectors.")

        # Root method decision
        major = 0
        try:
            major = int(release.split(".")[0])
        except (ValueError, IndexError):
            pass

        if major <= 5:
            report["root_method"] = "system"
        elif major >= 6:
            report["root_method"] = "systemless"
            report["warnings"].append(AnvilExceptionHandler.FAULT_MAP["SYSTEMLESS_REQUIRED"])
        else:
            report["root_method"] = "blocked"
            report["locks"].append("root")

        report["ready"] = True
        return report

    def check_usb_alive(self) -> bool:
        """Watchdog helper – returns False if device vanished."""
        return self.is_device_ready()
