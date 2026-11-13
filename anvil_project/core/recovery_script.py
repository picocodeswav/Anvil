"""
Anvil Recovery Script Engine
Automates OpenRecoveryScript payload generation and systemless root orchestration.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, List
from .exception_handler import DeviceFault, AnvilExceptionHandler
from .adb_manager import ADBManager


class RecoveryScriptEngine:
    """
    Handles the bifurcated root pipeline:
    - Android 4.x–5.x : Direct system injection
    - Android 6.x–7.x : Systemless ORS + temporary TWRP boot
    """

    def __init__(self, adb: ADBManager, assets_root: Path):
        self.adb = adb
        self.assets = assets_root
        self.su_bin = assets_root / "exploits" / "su"
        self.dirtycow = assets_root / "exploits" / "dirtycow"
        self.twrp_img = assets_root / "recoveries" / "twrp_generic.img"
        self.supersu_zip = assets_root / "recoveries" / "SuperSU.zip"

    def _write_ors(self, commands: List[str], serial: Optional[str] = None) -> bool:
        """
        Write OpenRecoveryScript control file to /cache/recovery/openrecoveryscript
        """
        content = "\n".join(commands) + "\n"
        # Cross-platform temp file (fixes Windows FileNotFoundError on /tmp)
        fd, tmp_name = tempfile.mkstemp(prefix="anvil_ors_", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            local_ors = Path(tmp_name)

            # Ensure directory exists on device
            self.adb.shell("mkdir -p /cache/recovery", serial=serial)
            # Push
            if not self.adb.push(str(local_ors), "/cache/recovery/openrecoveryscript", serial=serial):
                raise DeviceFault("Failed to write ORS control file", code="ORS_WRITE_FAIL")
            return True
        finally:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except Exception:
                pass

    def prepare_systemless_root(self, serial: Optional[str] = None) -> bool:
        """
        Full systemless path for Android 6.0–7.1
        1. Push SuperSU.zip to /sdcard/Download/
        2. Generate ORS commands
        3. Device must later be rebooted into temporary TWRP via fastboot boot
        """
        if not self.supersu_zip.exists():
            raise DeviceFault("SuperSU.zip asset missing", code="ORS_WRITE_FAIL")

        # Push zip
        remote_zip = "/sdcard/Download/SuperSU.zip"
        if not self.adb.push(str(self.supersu_zip), remote_zip, serial=serial):
            raise DeviceFault("Failed to push SuperSU.zip", code="ORS_WRITE_FAIL")

        # ORS commands: install the zip then reboot
        commands = [
            "install /sdcard/Download/SuperSU.zip",
            "reboot"
        ]
        self._write_ors(commands, serial=serial)
        return True

    def execute_system_injection(self, serial: Optional[str] = None, use_dirtycow: bool = True) -> bool:
        """
        Direct system partition root for Android 4.x–5.x
        """
        if not self.su_bin.exists():
            raise DeviceFault("su binary asset missing", code="SU_PUSH_FAIL")

        # 1. Push su to tmp
        if not self.adb.push(str(self.su_bin), "/data/local/tmp/su", serial=serial):
            raise DeviceFault("Failed to push su binary", code="SU_PUSH_FAIL")

        # 2. Make executable
        self.adb.shell("chmod 755 /data/local/tmp/su", serial=serial)

        # 3. Optional Dirty COW privilege escalation staging
        if use_dirtycow and self.dirtycow.exists():
            self.adb.push(str(self.dirtycow), "/data/local/tmp/dirtycow", serial=serial)
            self.adb.shell("chmod 755 /data/local/tmp/dirtycow", serial=serial)
            # Note: actual dirtycow execution is device-specific and left as staged payload.
            # The binary is placed and ready; higher-level logic can trigger it.

        # 4. Remount system RW
        rc, out, err = self.adb.shell("mount -o remount,rw /system", serial=serial)
        if rc != 0:
            # Try alternative
            rc, out, err = self.adb.shell("mount -o rw,remount /system", serial=serial)
            if rc != 0:
                raise DeviceFault("Failed to remount /system", code="PARTITION_MOUNT_FAIL", details={"stderr": err})

        # 5. Install su
        self.adb.shell("cp /data/local/tmp/su /system/xbin/su", serial=serial)
        self.adb.shell("chmod 06755 /system/xbin/su", serial=serial)
        self.adb.shell("chown root:root /system/xbin/su", serial=serial)

        # 6. Verify
        rc, out, _ = self.adb.shell("/system/xbin/su -v", serial=serial)
        return rc == 0 or "su" in out.lower()

    def boot_temporary_recovery(self, serial: Optional[str] = None) -> bool:
        """
        Reboot device into bootloader then fastboot boot the TWRP image into RAM.
        """
        if not self.twrp_img.exists():
            raise DeviceFault("TWRP image asset missing", code="RECOVERY_TIMEOUT")

        # First reboot to bootloader
        self.adb.reboot("bootloader", serial=serial)
        # Give it a moment
        import time
        time.sleep(4)

        # Fastboot boot
        return self.adb.fastboot_boot(str(self.twrp_img), serial=serial)

    def run_root_pipeline(self, report: dict, serial: Optional[str] = None) -> str:
        """
        High-level entry point that chooses the correct path based on pre-flight report.
        Returns a status string for the UI log.
        """
        method = report.get("root_method")
        if method == "blocked" or "root" in report.get("locks", []):
            return AnvilExceptionHandler.log_safe(
                "Root operation locked by pre-flight sentry. Resolve bootloader / crypto warnings first.",
                "ERROR"
            )

        try:
            if method == "system":
                use_dc = report.get("exploit_candidate") == "dirtycow"
                success = self.execute_system_injection(serial=serial, use_dirtycow=use_dc)
                if success:
                    return AnvilExceptionHandler.log_safe(
                        "System injection complete. su installed to /system/xbin/su",
                        "SUCCESS"
                    )
                return AnvilExceptionHandler.log_safe("System injection failed.", "ERROR")

            elif method == "systemless":
                self.prepare_systemless_root(serial=serial)
                # User must now trigger the temporary recovery boot
                return AnvilExceptionHandler.log_safe(
                    "ORS payload written. Device is ready for temporary TWRP boot. "
                    "Click 'Boot Recovery' to continue.",
                    "SUCCESS"
                )
            else:
                return AnvilExceptionHandler.log_safe("Unknown root method.", "ERROR")

        except DeviceFault as df:
            return AnvilExceptionHandler.trap(df)
        except Exception as e:
            return AnvilExceptionHandler.trap(e, context="root_pipeline")
