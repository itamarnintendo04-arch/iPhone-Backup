# IPHONE-BACKUP

A cross-platform desktop utility for **local iPhone / iPad USB backups** built with **Python**, **CustomTkinter**, and **pymobiledevice3**.

## Features

- Device detection, model-friendly identity details, and USB trust guidance
- Real USB device detection and local Finder/iTunes-compatible MobileBackup2 backups\n- Restore downloaded or local backups to a connected iPhone (requires explicit confirmation)\n- Optional S3-compatible encrypted-at-rest cloud backup uploads and verified downloads
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
- Restore is supported but **can replace data on the iPhone**. Make a separate current backup first. Restoring an encrypted backup requires the password.\n- Cloud storage requires a bucket and your own credentials; it is not an Apple iCloud Backup integration.
- A progress percentage is determined by the backup protocol and may not update smoothly.

## Security

Backups stay on your selected local disk. The app makes no cloud uploads and does not collect credentials or bypass device trust. Use it only with your own device or with its owner's permission.

## Cloud backup and restore

1. Connect and unlock the iPhone over USB, approve **Trust**, then use **Detect USB device**.
2. Choose a local backup destination and select **Start backup**. Wait for the backup to finish.
3. To upload, configure an **S3-compatible bucket**, region, HTTPS endpoint (optional for AWS), access key and secret key in the application's Cloud section. The keys are held in memory only, not saved to the repository or app settings.
4. Select **Upload backup to cloud**. The app uploads files to `iphone-backup/<device-id>/`, requests AES-256 server-side encryption, and writes a manifest only after all file uploads finish.
5. On another computer, supply the same cloud credentials, choose an empty local destination, and select **Download cloud backup**. Files are checked against the cloud manifest's SHA-256 digests.
6. Connect the target iPhone, choose **Restore to iPhone**, select the downloaded backup ID, acknowledge that data may be replaced, and supply the encrypted-backup password if prompted.

**Important:** S3 credentials must have appropriate `ListBucket`, `GetObject`, `PutObject` and `HeadObject` access. Some S3-compatible providers have different encryption policies. A private bucket, strong access controls, encryption on the iPhone backup itself and limited credentials are strongly recommended. Unlike end-to-end encryption, server-side S3 encryption does not prevent the storage provider from accessing backup contents. Avoid public buckets.

Cloud uploads are user-triggered; the app does not silently or automatically back up to a provider. No cloud storage is provisioned by the repository. Do not upload secrets or personal backup data to GitHub.
