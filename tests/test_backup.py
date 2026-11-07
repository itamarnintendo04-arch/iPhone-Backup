import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from iphone_backup.backup import (
    BackupError, DeviceInfo, backup_device, explain_error, get_device_info,
)


def test_device_info():
    fake = SimpleNamespace(
        all_values={"DeviceName": "Test iPhone", "ProductVersion": "18.0"},
        udid="1234",
    )
    assert get_device_info(fake) == DeviceInfo("Test iPhone", "18.0", "1234")


def test_trust_error_is_actionable():
    error = explain_error(Exception("Invalid Host ID; pairing failed"))
    assert "Trust" in str(error)


def test_permission_error_is_actionable():
    assert "writable folder" in str(explain_error(PermissionError("denied")))


def test_missing_device_error():
    assert "USB" in str(explain_error(Exception("No device found")))


def test_backup_error_type():
    assert isinstance(explain_error(OSError("disk full")), BackupError)
