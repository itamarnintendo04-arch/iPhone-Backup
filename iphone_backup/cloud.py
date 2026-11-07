"""S3-compatible backup storage. Credentials are only held in memory.

Bucket objects are placed under iphone-backup/<device-udid>/.
A manifest with SHA-256 checksums guards against partial/corrupt downloads.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Callable

import boto3
from botocore.config import Config


PREFIX = "iphone-backup"
MANIFEST = "_cloud_manifest.json"


@dataclass(frozen=True)
class CloudSettings:
    bucket: str
    region: str
    endpoint: str
    access_key: str
    secret_key: str


def client(settings: CloudSettings):
    if not settings.bucket.strip() or not settings.access_key or not settings.secret_key:
        raise ValueError("Cloud bucket, access key and secret key are required.")
    if settings.endpoint and not settings.endpoint.startswith("https://"):
        raise ValueError("Cloud endpoint must use HTTPS.")
    return boto3.client(
        "s3",
        region_name=settings.region.strip() or "us-east-1",
        endpoint_url=settings.endpoint.strip() or None,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        config=Config(retries={"max_attempts": 5, "mode": "standard"}),
    )


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _valid_udid(udid: str) -> str:
    if not udid or not all(c.isalnum() or c in "-_" for c in udid):
        raise ValueError("Invalid device backup identifier")
    return udid


def available_local_backups(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(
        entry.name for entry in root.iterdir()
        if entry.is_dir() and (entry / "Manifest.plist").is_file()
        and all(c.isalnum() or c in "-_" for c in entry.name)
    )


def upload_backup(settings: CloudSettings, root: Path, udid: str,
                  progress: Callable[[int, int], None] | None = None) -> None:
    udid = _valid_udid(udid)
    folder = root / udid
    if not (folder / "Manifest.plist").is_file():
        raise FileNotFoundError("No complete local backup found for this device.")
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    if not files:
        raise ValueError("The selected backup folder is empty.")
    s3 = client(settings)
    entries = []
    for idx, path in enumerate(files, 1):
        relative = path.relative_to(folder).as_posix()
        s3.upload_file(str(path), settings.bucket, f"{PREFIX}/{udid}/{relative}")
        entries.append({"path": relative, "size": path.stat().st_size, "sha256": _digest(path)})
        if progress:
            progress(idx, len(files))
    manifest = json.dumps({"version": 1, "device": udid, "files": entries}).encode("utf-8")
    # Publish the index last so interrupted uploads are not advertised as complete.
    s3.put_object(Bucket=settings.bucket, Key=f"{PREFIX}/{udid}/{MANIFEST}",
                  Body=manifest, ContentType="application/json")


def list_cloud_backups(settings: CloudSettings) -> list[str]:
    s3 = client(settings)
    paginator = s3.get_paginator("list_objects_v2")
    found = []
    for page in paginator.paginate(Bucket=settings.bucket, Prefix=f"{PREFIX}/",
                                   Delimiter="/"):
        for item in page.get("CommonPrefixes", []):
            path = item["Prefix"].rstrip("/").split("/")[-1]
            try:
                _valid_udid(path)
                s3.head_object(Bucket=settings.bucket, Key=f"{PREFIX}/{path}/{MANIFEST}")
                found.append(path)
            except (ValueError, Exception) as exc:
                # Incomplete uploads are not offered as downloadable backups.
                from botocore.exceptions import ClientError
                if not isinstance(exc, ClientError):
                    raise
    return sorted(set(found))


def download_backup(settings: CloudSettings, root: Path, udid: str,
                    progress: Callable[[int, int], None] | None = None) -> None:
    udid = _valid_udid(udid)
    s3 = client(settings)
    key = f"{PREFIX}/{udid}/{MANIFEST}"
    manifest = json.loads(s3.get_object(Bucket=settings.bucket, Key=key)["Body"].read())
    if manifest.get("version") != 1 or manifest.get("device") != udid:
        raise ValueError("Cloud manifest is invalid.")
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) > 2_000_000:
        raise ValueError("Cloud manifest has an invalid file list.")
    folder = root / udid
    if folder.exists():
        raise FileExistsError(
            "A local backup for this device already exists. Choose an empty destination "
            "folder to download without overwriting it."
        )
    # Avoid directory traversal from externally stored metadata.
    for entry in entries:
        name = entry.get("path", "")
        parts = PurePosixPath(name).parts
        if not isinstance(name, str) or not parts or name.startswith("/") or (
            any(part in ("..", ".") for part in parts)
        ) or "\\" in name or parts[-1] == MANIFEST:
            raise ValueError("Cloud manifest contains an unsafe file path.")
    folder.mkdir(parents=True, exist_ok=False)
    try:
        for idx, entry in enumerate(entries, 1):
            name = entry["path"]
            destination = folder.joinpath(*PurePosixPath(name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(settings.bucket, f"{PREFIX}/{udid}/{name}", str(destination))
            if destination.stat().st_size != entry["size"] or _digest(destination) != entry["sha256"]:
                raise ValueError(f"Cloud backup file failed integrity validation: {name}")
            if progress:
                progress(idx, len(entries))
        if not (folder / "Manifest.plist").is_file():
            raise ValueError("Downloaded backup is incomplete (missing Manifest.plist).")
    except Exception:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
