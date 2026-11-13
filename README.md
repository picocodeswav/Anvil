# Anvil

**Keep old Android devices useful instead of throwing them away.**

Anvil is a desktop tool for Android 4.0 (Ice Cream Sandwich) through 7.1 (Nougat).  
It gives working hardware a second life — old tablets, phones, digital signage panels, car head units, and offline controllers that still run fine but were abandoned by software updates and bloat.

Instead of sending another device to landfill, Anvil lets you:

- safely root it when needed
- strip manufacturer and carrier bloat without breaking the system
- prepare it for dedicated use (media player, kiosk, dashboard, offline machine, etc.)

---

## What it actually does

| Module | Purpose |
|--------|---------|
| **Pre-Flight Sentry** | Reads crypto state, bootloader lock, security patch level. Stages Dirty COW when the patch is older than Dec 2016. Blocks root attempts that would brick locked or fully encrypted devices and shows the exact unlock command when needed. |
| **Hybrid Root** | ≤ Android 5.1 → direct system `su` injection<br>Android 6.0–7.1 → systemless path + temporary TWRP in RAM + SuperSU |
| **Debloat** | Non-destructive (`pm uninstall -k --user 0`). Uses manufacturer profiles (Samsung, Verizon, HTC, LG, generic) so you can remove the junk without wiping user data. |
| **Safety** | All long operations run in background threads. 1.5 s USB watchdog freezes writes if the cable drops mid-process. |

The goal is simple: make the device usable again with the least risk and the least waste.

---

## Required Repositories & Binaries

Because Anvil ships without proprietary or precompiled exploit payloads, you will need to source and compile the following binaries from their official repositories before running root operations:

| Component | Repository | Destination Path in Project |
|-----------|------------|-----------------------------|
| **Dirty COW Exploit** | [github.com/firefart/dirtycow](https://github.com/firefart/dirtycow) | `assets/exploits/dirtycow` |
| **Superuser (`su`) Binary** | [github.com/chainsdd/su-binary](https://github.com/chainsdd/su-binary) | `assets/exploits/su` |

*(Optional for Android 6.0–7.1 systemless root: place a device-compatible `twrp_generic.img` and `SuperSU.zip` into `assets/recoveries/`.)*

---

## Requirements

**Host machine**
- Windows or Linux
- `adb` and `fastboot` in PATH
- Python 3.8+ (only needed if you build from source)

**Target device**
- Android 4.0 – 7.1
- USB debugging enabled
- For the systemless path: unlocked bootloader is strongly recommended

---

## Quick start (from source)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download/compile and drop the binaries into the assets folders:
#    - Dirty COW source: https://github.com/firefart/dirtycow
#      Place compiled binary at: assets/exploits/dirtycow
#    - su binary source: https://github.com/chainsdd/su-binary
#      Place compiled binary at: assets/exploits/su
#    - Custom recovery & root package (Android 6.0+):
#      Place at: assets/recoveries/twrp_generic.img
#      Place at: assets/recoveries/SuperSU.zip
#    - (optional) USB drivers at: assets/drivers/usb_install.exe

# 3. Run
py app.py
```

Or build a single binary:

```bash
./build_anvil.sh
# Result: dist/Anvil_Android_Utility
```

---

## How to use it

1. Connect the device with USB debugging on.
2. Launch Anvil.
3. Hit **Pre-Flight**.  
   It will tell you the Android version, whether the bootloader is locked, whether full-disk encryption is active, and whether Dirty COW is available.
4. If the device is safe to root:
   - Choose the root path (system or systemless — Anvil picks the right one automatically based on version).
   - Confirm and let it run. The USB watchdog will stop everything if the cable is unplugged.
5. After root (or even without it) use the debloat section.  
   Pick the manufacturer profile or the generic list and remove the packages you don’t need.  
   The uninstalls are non-destructive — apps can be restored later if you change your mind.
6. Reboot and use the device for whatever second life you had in mind.

---

## Project layout

```
anvil_project/
├── app.py                      # Main window + thread dispatcher
├── core/
│   ├── adb_manager.py          # ADB wrapper + Pre-Flight Sentry
│   ├── recovery_script.py      # OpenRecoveryScript + root pipelines
│   └── exception_handler.py    # Fault trapping
├── assets/
│   ├── manifests/
│   │   └── bloat_profiles.json # Manufacturer debloat lists
│   ├── exploits/               # su + dirtycow (place compiled binaries here)
│   ├── recoveries/             # TWRP + SuperSU (place real files here)
│   └── drivers/
└── build_anvil.sh              # One-file PyInstaller build
```

---

## Why this exists

Millions of Android devices from 2012–2017 still have working screens, storage, and batteries.  
They were discarded because the software side gave up on them, not because the hardware failed.

Anvil is a practical tool for people who want to keep those devices alive — as offline media players, dedicated home dashboards, digital signage, privacy-focused secondary phones, or simple internet-free machines.

Less e-waste. More useful silicon.

---

## Notes & limitations

- The included asset files are placeholders. You must download/compile the `su` ([chainsdd/su-binary](https://github.com/chainsdd/su-binary)) and Dirty COW ([firefart/dirtycow](https://github.com/firefart/dirtycow)) binaries, as well as supply TWRP and SuperSU files before the root features will work.
- Rooting always carries risk. Pre-Flight is there to reduce that risk, not eliminate it.
- This tool targets legacy Android only. Modern devices (8+) should use Magisk / KernelSU / APatch instead.

---

## License

This project is released under **The Unlicense** (public domain / no license).

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software, either in source code form or as a compiled binary, for any purpose, commercial or non-commercial, and by any means.

See [LICENSE](LICENSE) for full details.

---

Built to keep legacy silicon alive.