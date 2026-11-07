from pathlib import Path

import pytest

from iphone_backup.cloud import (
    CloudSettings, available_local_backups, client, _valid_udid,
)


def test_local_backups_only_with_manifest(tmp_path: Path) -> None:
    good = tmp_path / "valid-123"
    good.mkdir()
    (good / "Manifest.plist").write_bytes(b"test")
    (tmp_path / "incomplete").mkdir()
    assert available_local_backups(tmp_path) == ["valid-123"]


def test_missing_local_backup_directory(tmp_path: Path) -> None:
    assert available_local_backups(tmp_path / "missing") == []


@pytest.mark.parametrize("name", ["../outside", "/root", "a/b", ""])
def test_reject_unsafe_backup_id(name: str) -> None:
    with pytest.raises(ValueError):
        _valid_udid(name)


def test_missing_cloud_credentials() -> None:
    config = CloudSettings("bucket", "us-east-1", "", "", "")
    with pytest.raises(ValueError):
        client(config)


def test_plaintext_endpoint_rejected() -> None:
    config = CloudSettings("bucket", "us-east-1", "http://cloud.example", "key", "secret")
    with pytest.raises(ValueError):
        client(config)
