"""
Anvil Exception Handler
Standardizes and traps device faults into UI-safe strings.
Never lets raw exceptions reach the interface layer.
"""

from typing import Optional, Dict, Any
import traceback


class DeviceFault(Exception):
    """Base exception for all Anvil device-related failures."""
    def __init__(self, message: str, code: str = "DEVICE_FAULT", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class AnvilExceptionHandler:
    """
    Centralized fault trap. Converts any exception or device state
    into a clean, human-readable string safe for the UI log window.
    """

    FAULT_MAP = {
        "DEVICE_NOT_FOUND": "No Android device detected on ADB. Check USB cable and authorization.",
        "UNAUTHORIZED": "Device is unauthorized. Accept the RSA fingerprint prompt on the phone.",
        "CRYPTO_ACTIVE": "Full-disk encryption is active. Custom recovery boot will fail without pass-through.",
        "BOOTLOADER_LOCKED": "Bootloader is locked (ro.boot.flash.locked=1). Physical unlock required.",
        "DIRTYCOW_UNAVAILABLE": "Security patch level too recent for Dirty COW. Falling back to alternative.",
        "SYSTEMLESS_REQUIRED": "Android 6.0+ detected. System partition modification blocked. Using ORS path.",
        "RECOVERY_TIMEOUT": "Custom recovery failed to boot within timeout window.",
        "USB_DROPPED": "USB connection lost mid-operation. All write processes frozen for safety.",
        "PARTITION_MOUNT_FAIL": "Failed to remount /system as read-write. Aborting injection.",
        "SU_PUSH_FAIL": "Failed to push su binary to /data/local/tmp.",
        "ORS_WRITE_FAIL": "Failed to write OpenRecoveryScript control file.",
        "FASTBOOT_NOT_READY": "Device not in fastboot mode or fastboot binary missing.",
        "UNKNOWN_PROP": "Unable to read critical system property. Device state unknown.",
    }

    @classmethod
    def trap(cls, exc: Exception, context: str = "") -> str:
        """Convert any exception into a UI-safe log string."""
        if isinstance(exc, DeviceFault):
            base = cls.FAULT_MAP.get(exc.code, exc.message)
            if exc.details:
                detail_str = " | ".join(f"{k}={v}" for k, v in exc.details.items())
                return f"[{exc.code}] {base} :: {detail_str}"
            return f"[{exc.code}] {base}"

        # Generic trap
        tb = traceback.format_exc(limit=3)
        return f"[UNHANDLED] {context}: {str(exc)}\n{tb}"

    @classmethod
    def from_prop(cls, prop_name: str, value: str) -> Optional[DeviceFault]:
        """Create a DeviceFault from a known dangerous property value."""
        if prop_name == "ro.crypto.state" and value in ("encrypted", "unsupported"):
            return DeviceFault(
                "Full-disk encryption active",
                code="CRYPTO_ACTIVE",
                details={"ro.crypto.state": value}
            )
        if prop_name == "ro.boot.flash.locked" and value == "1":
            return DeviceFault(
                "Bootloader locked",
                code="BOOTLOADER_LOCKED",
                details={"ro.boot.flash.locked": value}
            )
        return None

    @classmethod
    def log_safe(cls, message: str, level: str = "INFO") -> str:
        """Return a standardized log line."""
        return f"[{level}] {message}"
