# IPHONE-BACKUP

A cross-platform desktop utility for **local iPhone / iPad USB backups** built with **Python**, **CustomTkinter**, and **pymobiledevice3**.

## Features

- Device detection, model-friendly identity details, and USB trust guidance
- Local Finder/iTunes-compatible MobileBackup2 backups
- Incremental backups by default; optional forced full backups
- Background-threaded asyncio operations and responsive GUI
- Live progress indicator, event log, and actionable driver / pairing / filesystem errors
- Windows and macOS one-file/windowed PyInstaller builds via GitHub Actions

## Run from source

Install Python 3.12, then:

```bash
python -m pip install -r requirements.txt
python app.py
```

Connect your iPhone or iPad using a **data-capable USB cable**. Unlock it, tap **Trust This Computer** if asked, then select **Detect USB device**. Choose a local folder and select **Start backup**.

The backup is written to `<selected folder>/<device UDID>/`. Allow plenty of disk space; backups can be large.

### Windows driver troubleshooting

Install or repair **Apple Devices** or **iTunes with Apple Mobile Device Support**. Make sure **Apple Mobile Device Service** is running; reconnect the cable and trust the computer on the phone. A charge-only cable is insufficient.

### macOS troubleshooting

Verify the device appears in **Finder**, approve **Trust** on the iPhone, and use a functioning USB data cable. Apple device services are part of macOS.

### Encryption note

The app does not change your device's backup-encryption settings or store passwords. Existing encrypted-backup configurations remain controlled by iOS/Finder. Store backups in a private folder: unencrypted backups can contain sensitive personal data. **Never commit a backup folder to GitHub.**

## Build binaries

Pushes to `main` run `.github/workflows/build.yml` on separate Windows and macOS runners. Download platform archives under **Actions → Build desktop apps → Artifacts**. GitHub's macOS runner produces unsigned output; macOS Gatekeeper may require locally signing/notarizing before wider distribution.

Local build:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
pyinstaller --noconfirm --clean --onefile --windowed --name IPHONE-BACKUP --collect-all customtkinter --collect-all pymobiledevice3 app.py
```

## Limitations

- USB access requires a correctly installed and functioning Apple device connection service, plus the device's trust approval.
- Actual USB backup behavior must be tested on physical hardware; CI tests and packaging do not emulate an iPhone.
- The desktop utility currently supports **creating backups**, not restoring them.
- A progress percentage is determined by the backup protocol and may not update smoothly.

## Security

Backups stay on your selected local disk. The app makes no cloud uploads and does not collect credentials or bypass device trust. Use it only with your own device or with its owner's permission.
