# Anvil Legacy Android Maintenance Utility

[![Discord](https://shields.io)](https://discord.gg/htfkspkGM)

**Official Discord:** [Join the Anvil Community](https://discord.gg/htfkspkGM)
Use code with caution.


Production-grade orchestration engine for Android 4.0 (Ice Cream Sandwich) through 7.1 (Nougat).

Designed for retro-emulation decks, offline smart-home controllers, digital dashboards, and remote field telemetry units.

**Keep old Android devices useful instead of throwing them away.**

---

## Architecture

```
anvil_project/
├── app.py                      # Main Window UI & Central Thread Dispatcher
├── core/
│   ├── __init__.py
│   ├── adb_manager.py          # Device tracking & low-level ADB wrapper + Pre-Flight Sentry
│   ├── recovery_script.py      # OpenRecoveryScript + system/systemless root pipelines
│   └── exception_handler.py    # Standardized device fault trapping
├── assets/
│   ├── manifests/
│   │   └── bloat_profiles.json # Manufacturer-keyed non-destructive debloat lists
│   ├── drivers/
│   │   └── usb_install.exe
│   ├── exploits/
│   │   ├── su                  # ARMv7 statically compiled su
│   │   └── dirtycow            # CVE-2016-5195 container
│   └── recoveries/
│       ├── twrp_generic.img
│       └── SuperSU.zip
├── build_anvil.sh              # One-file PyInstaller build
└── requirements.txt
```

---

## Feature Modules

### 1. Diagnostic Pre-Flight Sentry
- Pulls `ro.crypto.state`, `ro.boot.flash.locked`, `ro.build.version.security_patch`
- Stages Dirty COW when patch < Dec 2016
- Dynamically locks Root button if bootloader is locked or FDE is active
- Outputs exact `fastboot oem unlock` guidance

### 2. Hybrid Flash Pipeline
- **≤ Android 5.1** → Direct system injection (`/system/xbin/su`)
- **Android 6.0–7.1** → Systemless ORS + temporary TWRP boot into RAM

### 3. Manifest-Driven Debloater
- Uses `pm uninstall -k --user 0` (non-destructive)
- External JSON profiles for Samsung, Verizon, HTC, LG, generic

### 4. Asynchronous Execution & Safety
- All long operations run in `QThread`
- 1500 ms USB watchdog freezes writes if the cable drops mid-process
- Hard disconnect probe in every worker (getprop check → CRITICAL freeze)
- Prevents false "skipped" spam and false SUCCESS after disconnect

### 5. Assets Needed Bar + Add Exploits
- Live `x / y` progress for required binaries
- **Version-aware**:
  - CHOOSE OS → tracks all 4 (`su`, `dirtycow`, `twrp`, `SuperSU`)
  - Android 4.0–5.1 → tracks `su` + `dirtycow` only
  - Android 6.0–7.1 → tracks `twrp` + `SuperSU` only
- **Add Exploits** button: pick files from disk, auto-detects type, copies into the correct `assets/` folder
- Works from source **and** from the compiled `.exe` (assets live next to the executable)

### 6. Target Version Selector
- CHOOSE OS (default)
- Android 4.0 – 4.4 (KitKat)
- Android 5.0 – 5.1 (Lollipop)
- Android 6.0 – 6.0.1 (Marshmallow)
- Android 7.0 – 7.1 (Nougat)

### 7. Clear Logs
- One-click wipe of the Operation Log

---

## Required Binaries (you supply these)

Anvil ships without proprietary/precompiled exploit payloads. Source and place:

| Component | Suggested source | Destination |
|-----------|------------------|-------------|
| Dirty COW | https://github.com/firefart/dirtycow | `assets/exploits/dirtycow` |
| su binary | https://github.com/chainsdd/su-binary | `assets/exploits/su` |
| TWRP image | device-compatible TWRP | `assets/recoveries/twrp_generic.img` |
| SuperSU.zip | SuperSU flashable zip | `assets/recoveries/SuperSU.zip` |

Or just launch Anvil and use **Add Exploits** — no need to unpack the exe.

---

## Requirements

**Host**
- Windows or Linux
- `adb` and `fastboot` in PATH
- Python 3.8+ (only if building from source)

**Target**
- Android 4.0 – 7.1
- USB debugging enabled
- Unlocked bootloader strongly recommended for the systemless path

---

## Quick start (from source)

```bash
pip install -r requirements.txt
python app.py
```

Then use **Add Exploits** (or manually drop binaries into `assets/`) and run Pre-Flight.

---

## Build the .exe (one-file)

```bash
pip install -r requirements.txt
# optional: put real binaries in assets/ first
./build_anvil.sh
```

Result: `dist/Anvil` (or `.exe` on Windows)

On Windows:

```bash
pyinstaller --noconfirm --onefile --windowed ^
  --add-data "assets/manifests/bloat_profiles.json;assets/manifests" ^
  --add-data "assets/exploits/su;assets/exploits" ^
  --add-data "assets/exploits/dirtycow;assets/exploits" ^
  --add-data "assets/recoveries/twrp_generic.img;assets/recoveries" ^
  --add-data "assets/recoveries/SuperSU.zip;assets/recoveries" ^
  --add-data "assets/drivers/usb_install.exe;assets/drivers" ^
  --name "Anvil" ^
  --hidden-import=PyQt5 ^
  --hidden-import=core ^
  --hidden-import=core.adb_manager ^
  --hidden-import=core.recovery_script ^
  --hidden-import=core.exception_handler ^
  app.py
```

After the first run, users can drop updated exploits next to the exe via **Add Exploits** without rebuilding.

---

## How to use

1. Connect device with USB debugging on.
2. Launch Anvil.
3. Select **Target Version** (or leave CHOOSE OS).
4. Hit **Add Exploits** if the Assets Needed bar is not full.
5. Run **Pre-Flight Sentry**.
6. If safe → **Root Device** (and **Boot Temporary Recovery** on 6.x/7.x).
7. Optionally **Debloat Profile**.
8. Reboot and give the device its second life.

---

## Notes & limitations

- Placeholder files in `assets/` are empty. Real binaries required for root/recovery features.
- Rooting always carries risk. Pre-Flight reduces it; it does not eliminate it.
- This tool targets legacy Android only. Modern devices (8+) should use Magisk / KernelSU / APatch.

---

## License

Released under **The Unlicense** (public domain).

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software for any purpose.

---

Anvil – built to keep legacy silicon alive.
