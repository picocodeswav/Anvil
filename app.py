#!/usr/bin/env python3
"""
Anvil Legacy Android Maintenance Utility
Main Window UI & Central Thread Dispatcher
Production-grade orchestration for Android 4.0 – 7.1
"""

import sys
import json
import time
import shutil
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QGroupBox, QComboBox,
    QProgressBar, QMessageBox, QSplitter, QFrame, QFileDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QPalette

# Local core
from core.adb_manager import ADBManager
from core.recovery_script import RecoveryScriptEngine
from core.exception_handler import AnvilExceptionHandler, DeviceFault


# ---------------------------------------------------------------------------
# Worker Threads
# ---------------------------------------------------------------------------

class PreFlightWorker(QThread):
    finished = pyqtSignal(dict)
    log = pyqtSignal(str)

    def __init__(self, adb: ADBManager):
        super().__init__()
        self.adb = adb

    def run(self):
        self.log.emit(AnvilExceptionHandler.log_safe("Starting Pre-Flight Sentry...", "INFO"))
        try:
            report = self.adb.run_preflight()
            self.finished.emit(report)
        except Exception as e:
            self.log.emit(AnvilExceptionHandler.trap(e, "preflight"))
            self.finished.emit({})


class RootWorker(QThread):
    finished = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, engine: RecoveryScriptEngine, report: dict, adb: ADBManager):
        super().__init__()
        self.engine = engine
        self.report = report
        self.adb = adb
        self._abort = False

    def abort(self):
        self._abort = True

    def _device_lost(self) -> bool:
        """Hard disconnect check – stops the thread instantly if USB is gone."""
        if self._abort:
            return True
        # Recommended connection probe (gooCode style)
        rc, out, err = self.adb.shell("getprop ro.build.version.release")
        device_check = f"{out or ''} {err or ''}".strip()
        if "device not found" in device_check.lower() or "no devices" in device_check.lower() or not device_check.strip() or rc != 0:
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            return True
        if not self.adb.check_usb_alive():
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            return True
        return False

    def run(self):
        self.log.emit(AnvilExceptionHandler.log_safe("Root pipeline engaged...", "INFO"))
        # Check connection before executing operations
        if self._device_lost():
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            self.finished.emit(AnvilExceptionHandler.log_safe(
                "Aborted: Device Disconnected", "ERROR"
            ))
            return
        result = self.engine.run_root_pipeline(self.report)
        # Final safety check after pipeline
        if self._device_lost():
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            self.finished.emit(AnvilExceptionHandler.log_safe(
                "Aborted: Device Disconnected", "ERROR"
            ))
            return
        self.finished.emit(result)


class DebloatWorker(QThread):
    finished = pyqtSignal(str)
    log = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, adb: ADBManager, packages: list):
        super().__init__()
        self.adb = adb
        self.packages = packages
        self._abort = False

    def abort(self):
        self._abort = True

    def _device_lost(self) -> bool:
        """Hard disconnect check – stops the thread instantly if USB is gone."""
        if self._abort:
            return True
        # Recommended connection probe (gooCode style)
        rc, out, err = self.adb.shell("getprop ro.build.version.release")
        device_check = f"{out or ''} {err or ''}".strip()
        if "device not found" in device_check.lower() or "no devices" in device_check.lower() or not device_check.strip() or rc != 0:
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            return True
        if not self.adb.check_usb_alive():
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            return True
        return False

    def run(self):
        # Check connection before executing operations
        if self._device_lost():
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            self.finished.emit(AnvilExceptionHandler.log_safe(
                "Aborted: Device Disconnected", "ERROR"
            ))
            return

        total = len(self.packages)
        success = 0
        for i, pkg in enumerate(self.packages):
            # Check connection before executing operations
            if self._device_lost():
                self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
                self.finished.emit(AnvilExceptionHandler.log_safe(
                    "Aborted: Device Disconnected", "ERROR"
                ))
                return  # Safely breaks the thread loop instantly

            self.log.emit(f"Uninstalling (user 0): {pkg}")
            rc, out, err = self.adb.shell(f"pm uninstall -k --user 0 {pkg}")
            if rc == 0 or "Success" in (out or ""):
                success += 1
            else:
                # Only report skip if device is still alive
                if self._device_lost():
                    self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
                    self.finished.emit(AnvilExceptionHandler.log_safe(
                        "Aborted: Device Disconnected", "ERROR"
                    ))
                    return
                self.log.emit(f"  → skipped / not present: {pkg}")
            self.progress.emit(int((i + 1) / total * 100))
            time.sleep(0.12)

        # Only reach SUCCESS if we never hit a disconnect
        self.finished.emit(AnvilExceptionHandler.log_safe(
            f"Debloat complete. {success}/{total} packages removed from user space.",
            "SUCCESS"
        ))


class RecoveryBootWorker(QThread):
    finished = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, engine: RecoveryScriptEngine, adb: ADBManager):
        super().__init__()
        self.engine = engine
        self.adb = adb
        self._abort = False

    def abort(self):
        self._abort = True

    def _device_lost(self) -> bool:
        if self._abort:
            return True
        # Recommended connection probe (gooCode style)
        rc, out, err = self.adb.shell("getprop ro.build.version.release")
        device_check = f"{out or ''} {err or ''}".strip()
        if "device not found" in device_check.lower() or "no devices" in device_check.lower() or not device_check.strip() or rc != 0:
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            return True
        if not self.adb.check_usb_alive():
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            return True
        return False

    def run(self):
        self.log.emit(AnvilExceptionHandler.log_safe("Rebooting into temporary TWRP...", "INFO"))
        # Check connection before executing operations
        if self._device_lost():
            self.log.emit("[CRITICAL] USB connection lost! Freezing processes to prevent brick risk.")
            self.finished.emit(AnvilExceptionHandler.log_safe(
                "Aborted: Device Disconnected", "ERROR"
            ))
            return
        try:
            ok = self.engine.boot_temporary_recovery()
            if ok:
                self.finished.emit(AnvilExceptionHandler.log_safe(
                    "Temporary recovery boot command issued. Device should enter TWRP shortly.",
                    "SUCCESS"
                ))
            else:
                self.finished.emit(AnvilExceptionHandler.log_safe(
                    "fastboot boot failed. Ensure device is in fastboot mode.",
                    "ERROR"
                ))
        except Exception as e:
            self.finished.emit(AnvilExceptionHandler.trap(e, "recovery_boot"))


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class AnvilMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anvil Legacy Android Maintenance Utility")
        self.setMinimumSize(960, 680)
        self.resize(1100, 760)

        # Paths – work both from source and from PyInstaller --onefile
        if getattr(sys, "frozen", False):
            # Running as compiled exe: assets live next to the exe (user-writable)
            self.base_dir = Path(sys.executable).parent.resolve()
        else:
            self.base_dir = Path(__file__).parent.resolve()
        self.assets = self.base_dir / "assets"
        # Ensure asset folders exist so Add Exploits can write into them
        for sub in ("exploits", "recoveries", "manifests", "drivers"):
            (self.assets / sub).mkdir(parents=True, exist_ok=True)

        # Core engines
        self.adb = ADBManager()
        self.engine = RecoveryScriptEngine(self.adb, self.assets)

        # State
        self.current_report: dict = {}
        self.bloat_profiles = self._load_bloat_profiles()

        # Build UI
        self._build_ui()
        self._apply_dark_theme()

        # Watchdog timer – 1500 ms
        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self._watchdog_tick)
        self.watchdog.start(1500)

        # Initial asset scan
        self.refresh_assets_status()

        self._log("Anvil ready. Connect a legacy Android device (4.0 – 7.1) and run Pre-Flight.")

    def _load_bloat_profiles(self) -> dict:
        path = self.assets / "manifests" / "bloat_profiles.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header - classic XP title style
        header = QLabel("Anvil Legacy Android Maintenance Utility")
        header.setFont(QFont("Tahoma", 14, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #003399; padding: 4px;")
        main_layout.addWidget(header)

        sub = QLabel("Android 4.0 Ice Cream Sandwich  →  7.1 Nougat   |   System + Systemless Root   |   Non-destructive Debloat")
        sub.setFont(QFont("Tahoma", 9))
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #333333; padding-bottom: 4px;")
        main_layout.addWidget(sub)

        # Status bar
        self.status_label = QLabel("●  No device connected")
        self.status_label.setFont(QFont("Tahoma", 9, QFont.Bold))
        self.status_label.setStyleSheet("color: #CC0000; padding: 2px 0;")
        main_layout.addWidget(self.status_label)

        # Assets Needed bar + Version selector
        assets_row = QHBoxLayout()
        assets_row.setSpacing(8)

        self.assets_label = QLabel("Assets Needed:")
        self.assets_label.setFont(QFont("Tahoma", 9))
        assets_row.addWidget(self.assets_label)

        self.assets_bar = QProgressBar()
        self.assets_bar.setMinimum(0)
        self.assets_bar.setMaximum(4)
        self.assets_bar.setValue(0)
        self.assets_bar.setTextVisible(True)
        self.assets_bar.setFormat("%v / 4")
        self.assets_bar.setFont(QFont("Tahoma", 8))
        self.assets_bar.setFixedHeight(18)
        self.assets_bar.setMinimumWidth(140)
        assets_row.addWidget(self.assets_bar)

        self.assets_detail = QLabel("su · dirtycow · twrp · SuperSU")
        self.assets_detail.setFont(QFont("Tahoma", 8))
        self.assets_detail.setStyleSheet("color: #555555;")
        assets_row.addWidget(self.assets_detail)

        self.btn_add_exploits = QPushButton("Add Exploits")
        self.btn_add_exploits.setFont(QFont("Tahoma", 8))
        self.btn_add_exploits.setFixedHeight(24)
        self.btn_add_exploits.setStyleSheet(
            "QPushButton { padding: 2px 10px; min-width: 90px; }"
        )
        self.btn_add_exploits.clicked.connect(self.add_exploits)
        assets_row.addWidget(self.btn_add_exploits)

        assets_row.addStretch()

        ver_label = QLabel("Target Version:")
        ver_label.setFont(QFont("Tahoma", 9))
        assets_row.addWidget(ver_label)

        self.version_combo = QComboBox()
        self.version_combo.setFont(QFont("Tahoma", 9))
        self.version_combo.addItems([
            "CHOOSE OS",
            "Android 4.0 – 4.4 (KitKat)",
            "Android 5.0 – 5.1 (Lollipop)",
            "Android 6.0 – 6.0.1 (Marshmallow)",
            "Android 7.0 – 7.1 (Nougat)"
        ])
        self.version_combo.setMinimumWidth(200)
        self.version_combo.currentIndexChanged.connect(self.refresh_assets_status)
        assets_row.addWidget(self.version_combo)

        main_layout.addLayout(assets_row)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_preflight = QPushButton("Run Pre-Flight Sentry")
        self.btn_preflight.setFont(QFont("Tahoma", 9))
        self.btn_preflight.clicked.connect(self.start_preflight)
        btn_layout.addWidget(self.btn_preflight)

        self.btn_root = QPushButton("Root Device")
        self.btn_root.setFont(QFont("Tahoma", 9))
        self.btn_root.setEnabled(False)
        self.btn_root.clicked.connect(self.start_root)
        btn_layout.addWidget(self.btn_root)

        self.btn_recovery = QPushButton("Boot Temporary Recovery")
        self.btn_recovery.setFont(QFont("Tahoma", 9))
        self.btn_recovery.setEnabled(False)
        self.btn_recovery.clicked.connect(self.start_recovery_boot)
        btn_layout.addWidget(self.btn_recovery)

        self.btn_debloat = QPushButton("Debloat Profile")
        self.btn_debloat.setFont(QFont("Tahoma", 9))
        self.btn_debloat.setEnabled(False)
        self.btn_debloat.clicked.connect(self.start_debloat)
        btn_layout.addWidget(self.btn_debloat)

        main_layout.addLayout(btn_layout)

        # Profile selector + Clear Logs
        profile_row = QHBoxLayout()
        profile_label = QLabel("Debloat Profile:")
        profile_label.setFont(QFont("Tahoma", 9))
        profile_row.addWidget(profile_label)
        self.profile_combo = QComboBox()
        self.profile_combo.setFont(QFont("Tahoma", 9))
        self.profile_combo.addItems(["samsung", "verizon", "htc", "lg", "generic"])
        profile_row.addWidget(self.profile_combo)
        profile_row.addStretch()

        self.btn_clear_logs = QPushButton("Clear Logs")
        self.btn_clear_logs.setFont(QFont("Tahoma", 9))
        self.btn_clear_logs.setMinimumWidth(110)
        self.btn_clear_logs.setFixedHeight(26)
        self.btn_clear_logs.clicked.connect(self.clear_logs)
        profile_row.addWidget(self.btn_clear_logs)

        main_layout.addLayout(profile_row)

        # Progress
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFont(QFont("Tahoma", 8))
        main_layout.addWidget(self.progress)

        # Log window
        log_group = QGroupBox("Operation Log")
        log_group.setFont(QFont("Tahoma", 9, QFont.Bold))
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(8, 12, 8, 8)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Lucida Console", 9))
        log_layout.addWidget(self.log_view)
        main_layout.addWidget(log_group, stretch=1)

        # Info strip
        self.info_label = QLabel("Waiting for device...")
        self.info_label.setFont(QFont("Tahoma", 8))
        self.info_label.setStyleSheet("color: #333333; padding-top: 2px;")
        main_layout.addWidget(self.info_label)

    def _apply_dark_theme(self):
        # Windows XP Luna-inspired theme
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #ECE9D8;
                color: #000000;
                font-family: Tahoma;
            }

            QGroupBox {
                background-color: #ECE9D8;
                border: 1px solid #919B9C;
                border-radius: 3px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: bold;
                color: #003399;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0 5px;
                color: #003399;
            }

            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.45 #F0F0E8, stop:0.46 #E8E4D0, stop:1 #D8D0B8);
                border: 1px solid #003C74;
                border-radius: 3px;
                padding: 5px 16px;
                color: #000000;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFF8E8, stop:0.45 #FFE8C0, stop:0.46 #FFD898, stop:1 #F0C070);
                border: 1px solid #000080;
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #D8D0B8, stop:0.5 #C8C0A8, stop:1 #B8B098);
                border: 1px solid #003C74;
                padding-top: 6px;
                padding-bottom: 4px;
            }
            QPushButton:disabled {
                background-color: #ECE9D8;
                border: 1px solid #C0C0C0;
                color: #A0A0A0;
            }

            QTextEdit {
                background-color: #FFFFFF;
                border: 1px solid #7A9BC5;
                border-radius: 2px;
                color: #000000;
                selection-background-color: #316AC5;
                selection-color: #FFFFFF;
            }

            QProgressBar {
                border: 1px solid #7A9BC5;
                border-radius: 2px;
                text-align: center;
                background-color: #FFFFFF;
                color: #000000;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #A4C8F0, stop:0.5 #4A8AD0, stop:1 #2A6AB0);
                border-radius: 1px;
                margin: 1px;
            }

            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #7A9BC5;
                border-radius: 2px;
                padding: 2px 6px;
                color: #000000;
                min-height: 18px;
            }
            QComboBox:hover {
                border: 1px solid #000080;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                border: 1px solid #7A9BC5;
                selection-background-color: #316AC5;
                selection-color: #FFFFFF;
            }

            QLabel {
                color: #000000;
            }

            QScrollBar:vertical {
                background: #ECE9D8;
                width: 16px;
                margin: 0;
                border: 1px solid #919B9C;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #E8E4D0, stop:1 #C8C0A8);
                border: 1px solid #919B9C;
                border-radius: 2px;
                min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def _log(self, msg: str):
        self.log_view.append(msg)
        # Auto scroll
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_logs(self):
        self.log_view.clear()
        self._log("Logs cleared.")

    def add_exploits(self):
        """Let the user pick su / dirtycow / TWRP / SuperSU and install them into assets/."""
        # Map friendly names → destination relative paths
        targets = {
            "su binary (ARMv7)": ("exploits", "su"),
            "Dirty COW (dirtycow)": ("exploits", "dirtycow"),
            "TWRP image (twrp_generic.img)": ("recoveries", "twrp_generic.img"),
            "SuperSU.zip": ("recoveries", "SuperSU.zip"),
        }

        self._log("Select the exploit / recovery files to add...")
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Exploits / Recovery Assets",
            str(Path.home()),
            "All files (*.*);;Binaries (su dirtycow);;Images (*.img);;Zips (*.zip)"
        )
        if not files:
            self._log("Add Exploits cancelled.")
            return

        added = 0
        for src in files:
            src_path = Path(src)
            name_lower = src_path.name.lower()

            # Heuristic match by filename
            dest_rel = None
            if name_lower == "su" or name_lower.endswith("/su") or "su-binary" in name_lower:
                dest_rel = ("exploits", "su")
            elif "dirtycow" in name_lower or name_lower == "dcow":
                dest_rel = ("exploits", "dirtycow")
            elif name_lower.endswith(".img") or "twrp" in name_lower:
                dest_rel = ("recoveries", "twrp_generic.img")
            elif name_lower.endswith(".zip") and ("supersu" in name_lower or "su" in name_lower):
                dest_rel = ("recoveries", "SuperSU.zip")
            else:
                # Ask user which slot this file is for
                from PyQt5.QtWidgets import QInputDialog
                choice, ok = QInputDialog.getItem(
                    self,
                    "What is this file?",
                    f"Assign '{src_path.name}' to:",
                    list(targets.keys()),
                    0,
                    False
                )
                if not ok:
                    continue
                dest_rel = targets[choice]

            dest_dir = self.assets / dest_rel[0]
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / dest_rel[1]

            try:
                shutil.copy2(str(src_path), str(dest_path))
                size_kb = dest_path.stat().st_size // 1024
                self._log(f"Added: {dest_rel[1]}  ({size_kb} KB) ← {src_path.name}")
                added += 1
            except Exception as e:
                self._log(AnvilExceptionHandler.log_safe(
                    f"Failed to copy {src_path.name}: {e}", "ERROR"
                ))

        self.refresh_assets_status()
        if added:
            self._log(AnvilExceptionHandler.log_safe(
                f"Added {added} asset(s). Assets bar updated.", "SUCCESS"
            ))
            # Point the engine at the (possibly updated) assets path
            self.engine = RecoveryScriptEngine(self.adb, self.assets)
        else:
            self._log("No assets were added.")

    def refresh_assets_status(self):
        """Scan assets and update the bar based on selected Target Version."""
        # What each version actually needs
        # 4.x / 5.x = system injection → su required, dirtycow optional-but-tracked
        # 6.x / 7.x = systemless → twrp + SuperSU required
        # Auto = show all four until device tells us
        ver = self.version_combo.currentText() if hasattr(self, "version_combo") else "CHOOSE OS"

        if "4.0" in ver or "5.0" in ver:
            needed = {
                "su": self.assets / "exploits" / "su",
                "dirtycow": self.assets / "exploits" / "dirtycow",
            }
        elif "6.0" in ver or "7.0" in ver:
            needed = {
                "twrp": self.assets / "recoveries" / "twrp_generic.img",
                "SuperSU": self.assets / "recoveries" / "SuperSU.zip",
            }
        else:
            # CHOOSE OS – show full set until user picks a version
            needed = {
                "su": self.assets / "exploits" / "su",
                "dirtycow": self.assets / "exploits" / "dirtycow",
                "twrp": self.assets / "recoveries" / "twrp_generic.img",
                "SuperSU": self.assets / "recoveries" / "SuperSU.zip",
            }

        present = []
        missing = []
        for name, path in needed.items():
            if path.exists() and path.stat().st_size > 0:
                present.append(name)
            else:
                missing.append(name)

        total = len(needed)
        count = len(present)
        self.assets_bar.setMaximum(total)
        self.assets_bar.setValue(count)
        self.assets_bar.setFormat(f"{count} / {total}")

        if count == total and total > 0:
            self.assets_detail.setText("All assets ready")
            self.assets_detail.setStyleSheet("color: #008000;")
            self.assets_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #7A9BC5;
                    border-radius: 2px;
                    text-align: center;
                    background-color: #FFFFFF;
                    color: #000000;
                }
                QProgressBar::chunk {
                    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #90EE90, stop:0.5 #32CD32, stop:1 #228B22);
                    margin: 1px;
                }
            """)
        else:
            missing_str = " · ".join(missing) if missing else ""
            self.assets_detail.setText(f"Missing: {missing_str}" if missing else "—")
            self.assets_detail.setStyleSheet("color: #CC0000;" if missing else "color: #555555;")
            self.assets_bar.setStyleSheet("")

    def _set_buttons_enabled(self, enabled: bool):
        self.btn_preflight.setEnabled(enabled)
        device_alive = self.adb.check_usb_alive()
        report_ok = bool(self.current_report and self.current_report.get("ready"))

        if enabled and report_ok and device_alive:
            locks = self.current_report.get("locks", [])
            self.btn_root.setEnabled("root" not in locks)
            self.btn_recovery.setEnabled(self.current_report.get("root_method") == "systemless")
            self.btn_debloat.setEnabled(True)
        else:
            self.btn_root.setEnabled(False)
            self.btn_recovery.setEnabled(False)
            self.btn_debloat.setEnabled(False)

    # ------------------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------------------
    def _watchdog_tick(self):
        alive = self.adb.check_usb_alive()
        if alive:
            self.status_label.setText("●  Device connected")
            self.status_label.setStyleSheet("color: #008000; font-weight: bold; padding: 2px 0;")
        else:
            self.status_label.setText("●  No device / USB dropped")
            self.status_label.setStyleSheet("color: #CC0000; font-weight: bold; padding: 2px 0;")
            # Abort any running worker immediately
            if hasattr(self, "_active_worker") and self._active_worker and self._active_worker.isRunning():
                if hasattr(self._active_worker, "abort"):
                    self._active_worker.abort()
                self._log(AnvilExceptionHandler.log_safe(
                    "USB connection lost. Freezing active processes to prevent brick risk.",
                    "WARN"
                ))
                self._set_buttons_enabled(False)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def start_preflight(self):
        self._set_buttons_enabled(False)
        self.progress.setValue(0)
        self.worker = PreFlightWorker(self.adb)
        self.worker.log.connect(self._log)
        self.worker.finished.connect(self._on_preflight_done)
        self.worker.start()
        self._active_worker = self.worker

    def _on_preflight_done(self, report: dict):
        self.current_report = report
        self._active_worker = None

        if not report.get("ready"):
            self._log(AnvilExceptionHandler.log_safe("Pre-flight failed. No usable device.", "ERROR"))
            self.progress.setValue(0)
            self.info_label.setText("Waiting for device...")
            self._set_buttons_enabled(True)
            return

        # Log summary
        self._log("─" * 50)
        self._log(f"Device      : {report.get('manufacturer', '?').title()} {report.get('model', '?')}")
        self._log(f"Android     : {report.get('android_version')} (SDK {report.get('sdk')})")
        self._log(f"Patch Level : {report.get('security_patch')}")
        self._log(f"Crypto      : {report.get('crypto_state')}")
        self._log(f"Bootloader  : {'LOCKED' if report.get('bootloader_locked') else 'Unlocked'}")
        self._log(f"Root Method : {report.get('root_method', 'unknown').upper()}")
        self._log(f"Exploit     : {report.get('exploit_candidate') or 'None staged'}")
        for w in report.get("warnings", []):
            self._log(AnvilExceptionHandler.log_safe(w, "WARN"))
        self._log("─" * 50)

        # UI locks
        locks = report.get("locks", [])
        if "root" in locks:
            self._log(AnvilExceptionHandler.log_safe(
                "Root button locked. Resolve bootloader lock or crypto state first.",
                "WARN"
            ))
            if report.get("bootloader_locked"):
                self._log("→ Physical unlock required: reboot to bootloader then run:")
                self._log("   fastboot oem unlock")

        self.info_label.setText(
            f"{report.get('manufacturer', '').title()} {report.get('model')} · "
            f"Android {report.get('android_version')} · Method: {report.get('root_method')}"
        )
        self._set_buttons_enabled(True)
        self.progress.setValue(100)

    def start_root(self):
        if not self.current_report:
            return
        if not self.adb.check_usb_alive():
            self._log(AnvilExceptionHandler.log_safe(
                "No device connected. Root aborted.", "ERROR"
            ))
            return
        self.refresh_assets_status()
        # Warn if critical assets are missing (still allow attempt)
        missing = []
        for name, rel in [("su", "exploits/su"), ("dirtycow", "exploits/dirtycow")]:
            p = self.assets / rel
            if not (p.exists() and p.stat().st_size > 0):
                missing.append(name)
        if missing:
            self._log(AnvilExceptionHandler.log_safe(
                f"Missing assets for root: {', '.join(missing)}. Place real binaries in assets/ first.",
                "WARN"
            ))
        self._set_buttons_enabled(False)
        self.worker = RootWorker(self.engine, self.current_report, self.adb)
        self.worker.log.connect(self._log)
        self.worker.finished.connect(self._on_root_done)
        self.worker.start()
        self._active_worker = self.worker

    def _on_root_done(self, result: str):
        self._log(result)
        self._active_worker = None
        # If systemless, enable recovery boot button
        if self.current_report.get("root_method") == "systemless":
            self.btn_recovery.setEnabled(True)
        self._set_buttons_enabled(True)

    def start_recovery_boot(self):
        if not self.adb.check_usb_alive():
            self._log(AnvilExceptionHandler.log_safe(
                "No device connected. Recovery boot aborted.", "ERROR"
            ))
            return
        self.refresh_assets_status()
        missing = []
        for name, rel in [("twrp", "recoveries/twrp_generic.img"), ("SuperSU", "recoveries/SuperSU.zip")]:
            p = self.assets / rel
            if not (p.exists() and p.stat().st_size > 0):
                missing.append(name)
        if missing:
            self._log(AnvilExceptionHandler.log_safe(
                f"Missing assets for recovery: {', '.join(missing)}. Place real files in assets/recoveries/ first.",
                "WARN"
            ))
        self._set_buttons_enabled(False)
        self.worker = RecoveryBootWorker(self.engine, self.adb)
        self.worker.log.connect(self._log)
        self.worker.finished.connect(self._on_recovery_done)
        self.worker.start()
        self._active_worker = self.worker

    def _on_recovery_done(self, result: str):
        self._log(result)
        self._active_worker = None
        self._set_buttons_enabled(True)

    def start_debloat(self):
        if not self.adb.check_usb_alive():
            self._log(AnvilExceptionHandler.log_safe(
                "No device connected. Connect a device and run Pre-Flight first.", "ERROR"
            ))
            return
        if not (self.current_report and self.current_report.get("ready")):
            self._log(AnvilExceptionHandler.log_safe(
                "Run Pre-Flight Sentry successfully before debloating.", "ERROR"
            ))
            return

        profile = self.profile_combo.currentText()
        packages = self.bloat_profiles.get(profile, [])
        if not packages:
            self._log(AnvilExceptionHandler.log_safe(f"No packages defined for profile '{profile}'", "WARN"))
            return

        self._set_buttons_enabled(False)
        self.progress.setValue(0)
        self.worker = DebloatWorker(self.adb, packages)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self._on_debloat_done)
        self.worker.start()
        self._active_worker = self.worker

    def _on_debloat_done(self, result: str):
        self._log(result)
        self._active_worker = None
        if "interrupted" in result.lower() or "aborted" in result.lower() or "ERROR" in result:
            self.progress.setValue(0)
        self._set_buttons_enabled(True)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Anvil Legacy Android Utility")
    app.setOrganizationName("Anvil")
    window = AnvilMainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
