#!/usr/bin/env bash
# Anvil Legacy Android Maintenance Utility - Production Build Script
set -e

echo "[*] Cleaning previous builds..."
rm -rf build dist __pycache__ *.spec

# Linux/macOS use : as --add-data separator; Windows uses ;
SEP=":"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
  SEP=";"
fi

echo "[*] Building Anvil with PyInstaller (onefile, windowed, all assets embedded)..."

pyinstaller --noconfirm --onefile --windowed \
  --add-data "assets/manifests/bloat_profiles.json${SEP}assets/manifests" \
  --add-data "assets/exploits/su${SEP}assets/exploits" \
  --add-data "assets/exploits/dirtycow${SEP}assets/exploits" \
  --add-data "assets/recoveries/twrp_generic.img${SEP}assets/recoveries" \
  --add-data "assets/recoveries/SuperSU.zip${SEP}assets/recoveries" \
  --add-data "assets/drivers/usb_install.exe${SEP}assets/drivers" \
  --name "Anvil" \
  --hidden-import=PyQt5 \
  --hidden-import=core \
  --hidden-import=core.adb_manager \
  --hidden-import=core.recovery_script \
  --hidden-import=core.exception_handler \
  app.py

echo ""
echo "[+] Build complete."
echo "    Binary: dist/Anvil"
echo "    Users can add exploits later via the Add Exploits button."
