"""USB device discovery and local MobileBackup2 operations.

Use pymobiledevice3's public asynchronous API rather than spawning an external
CLI; this also works when packaged as a PyInstaller one-file executable.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import sys


class BackupError(RuntimeError):
    """User-facing, actionable connection/backup failure."""


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    version: str
    udid: str


def explain_error(exc: Exception) -> BackupError:
    text = str(exc).strip() or type(exc).__name__
    low = f"{type(exc).__name__} {text}".lower()
    if any(token in low for token in (
        "usbmux", "connection refused", "no such file or directory",
        "apple mobile device", "service not found", "winerror 10061"
    )):
        if sys.platform == "win32":
            return BackupError(
                "Cannot contact Apple Mobile Device Service / USB multiplexing. "
                "Install or repair Apple Devices (or iTunes and Apple Mobile Device Support), "
                "restart the Apple Mobile Device Service, and reconnect the USB cable. "
                f"Details: {text}"
            )
        return BackupError(
            "Cannot contact Apple's USB device service. Unlock and reconnect your device, "
            "check Finder can see it, and confirm the Apple USB services are running. "
            f"Details: {text}"
        )
    if any(token in low for token in ("pair", "trust", "password protected", "invalid host id")):
        return BackupError(
            "This computer is not trusted by the iPhone. Unlock the device, "
            "approve 'Trust This Computer', and try again. "
            f"Details: {text}"
        )
    if any(token in low for token in ("not connected", "no device", "no usb device", "no such device")):
        return BackupError(
            "No iPhone or iPad detected over USB. Check the cable, unlock the device, "
            "and approve the Trust prompt. " + text
        )
    if isinstance(exc, PermissionError):
        return BackupError(
            "Permission denied writing the backup. Choose a writable folder. " + text
        )
    if isinstance(exc, OSError):
        return BackupError(
            "Backup I/O failed. Verify free disk space, cable connection and destination. " + text
        )
    return BackupError(
        "Backup operation failed. Keep the device connected and unlocked, "
        "then retry. Details: " + text
    )


def get_device_info(lockdown) -> DeviceInfo:
    values = lockdown.all_values or {}
    return DeviceInfo(
        name=str(values.get("DeviceName") or "iPhone / iPad"),
        version=str(values.get("ProductVersion") or "Unknown iOS"),
        udid=str(lockdown.udid or "Unknown UDID"),
    )


async def probe_device() -> DeviceInfo:
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
        async with await create_using_usbmux(connection_type="USB") as lockdown:
            return get_device_info(lockdown)
    except Exception as exc:
        raise explain_error(exc) from exc


async def backup_device(
    directory: Path,
    *,
    full: bool = False,
    progress: Callable[[float], None] | None = None,
) -> DeviceInfo:
    directory = Path(directory).expanduser()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise NotADirectoryError(str(directory))
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service

        async with await create_using_usbmux() as lockdown:
            device = get_device_info(lockdown)
            async with Mobilebackup2Service(lockdown) as service:
                await service.backup(
                    backup_directory=directory,
                    full=full,
                    progress_callback=progress or (lambda _: None),
                )
            return device
    except Exception as exc:
        raise explain_error(exc) from exc


async def restore_device(
    directory: Path,
    *,
    source: str,
    password: str = "",
    progress: Callable[[float], None] | None = None,
) -> DeviceInfo:
    """Restore a complete local backup to the currently connected device.

    This can replace on-device data; UI must obtain explicit consent.
    """
    from .cloud import available_local_backups
    directory = Path(directory).expanduser()
    if source not in available_local_backups(directory):
        raise BackupError("Backup not found or incomplete. Select a valid local backup.")
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service

        async with await create_using_usbmux(connection_type="USB") as lockdown:
            device = get_device_info(lockdown)
            async with Mobilebackup2Service(lockdown) as service:
                await service.restore(
                    backup_directory=directory,
                    source=source,
                    password=password,
                    progress_callback=progress or (lambda _: None),
                    remove=False,
                    copy=True,
                )
            return device
    except Exception as exc:
        raise explain_error(exc) from exc
