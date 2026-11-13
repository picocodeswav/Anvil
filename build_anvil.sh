#!/usr/bin/env bash
# Anvil Legacy Android Maintenance Utility - Production Build Script
# Matches the exact packing architecture specified for single-click distribution

set -e

echo "[*] Cleaning previous builds..."
rm -rf build dist __pycache__ *.spec

echo "[*] Building Anvil with PyInstaller (onefile, windowed, all assets embedded)..."

pyinstaller --noconfirm --onefile --windowed \
  --add-data "assets/manifests/bloat_profiles.json;assets/manifests" \
  --add-data "assets/exploits/su;assets/exploits" \
  --add-data "assets/exploits/dirtycow;assets/exploits" \
  --add-data "assets/recoveries/twrp_generic.img;assets/recoveries" \
  --add-data "assets/recoveries/SuperSU.zip;assets/recoveries" \
  --add-data "assets/drivers/usb_install.exe;assets/drivers" \
  --name "Anvil_Android_Utility" \
  --hidden-import=PyQt5 \
  --hidden-import=core \
  --hidden-import=core.adb_manager \
  --hidden-import=core.recovery_script \
  --hidden-import=core.exception_handler \
  app.py

echo ""
echo "[+] Build complete."
echo "    Binary: dist/Anvil_Android_Utility"
echo "    Drop real ARMv7 su + dirtycow + TWRP + SuperSU into assets/ before shipping."
