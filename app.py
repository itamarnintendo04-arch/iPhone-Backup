"""IPHONE-BACKUP desktop application."""
from __future__ import annotations

import asyncio
import queue
import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from iphone_backup.backup import BackupError, DeviceInfo, backup_device, probe_device, restore_device
from iphone_backup.cloud import CloudSettings, available_local_backups, upload_backup, download_backup, list_cloud_backups

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class BackupApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("IPHONE-BACKUP")
        self.geometry("820x860")
        self.minsize(690, 700)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.device: DeviceInfo | None = None

        ctk.CTkLabel(self, text="IPHONE-BACKUP", font=ctk.CTkFont(size=28, weight="bold")).pack(
            anchor="w", padx=26, pady=(22, 4)
        )
        ctk.CTkLabel(
            self, text="Local USB backups for iPhone and iPad · Windows / macOS",
            text_color="gray",
        ).pack(anchor="w", padx=26, pady=(0, 18))

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=26, pady=8)
        self.device_label = ctk.CTkLabel(
            top, text="No device checked yet", anchor="w", wraplength=560
        )
        self.device_label.pack(side="left", fill="x", expand=True, padx=15, pady=16)
        self.detect_button = ctk.CTkButton(top, text="Detect USB device", command=self.detect)
        self.detect_button.pack(side="right", padx=12)

        ctk.CTkLabel(self, text="Backup destination", anchor="w").pack(
            fill="x", padx=26, pady=(12, 3)
        )
        dest = ctk.CTkFrame(self, fg_color="transparent")
        dest.pack(fill="x", padx=26)
        self.directory = ctk.StringVar(value=str(Path.home() / "iPhoneBackups"))
        self.directory_entry = ctk.CTkEntry(dest, textvariable=self.directory)
        self.directory_entry.pack(side="left", fill="x", expand=True)
        self.browse_button = ctk.CTkButton(
            dest, text="Browse", width=100, command=self.browse
        )
        self.browse_button.pack(side="left", padx=(8, 0))

        self.full_backup = ctk.BooleanVar(value=False)
        self.full_checkbox = ctk.CTkCheckBox(
            self, text="Force a full backup (otherwise incremental if possible)",
            variable=self.full_backup,
        )
        self.full_checkbox.pack(anchor="w", padx=26, pady=(18, 10))

        self.start_button = ctk.CTkButton(
            self, text="Start backup", height=40, command=self.start
        )
        self.start_button.pack(fill="x", padx=26, pady=(5, 12))
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=26, pady=(0, 8))
        self.status = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status.pack(fill="x", padx=26)

        # Cloud credentials are not written to disk and are never uploaded to GitHub.
        cloud_frame = ctk.CTkFrame(self)
        cloud_frame.pack(fill="x", padx=26, pady=(8, 4))
        ctk.CTkLabel(cloud_frame, text="Optional S3-compatible cloud storage",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(8, 3))
        self.cloud_bucket = ctk.CTkEntry(cloud_frame, placeholder_text="Bucket name")
        self.cloud_bucket.pack(fill="x", padx=12, pady=2)
        self.cloud_endpoint = ctk.CTkEntry(cloud_frame, placeholder_text="HTTPS endpoint (blank = AWS S3)")
        self.cloud_endpoint.pack(fill="x", padx=12, pady=2)
        self.cloud_region = ctk.CTkEntry(cloud_frame, placeholder_text="Region (default us-east-1)")
        self.cloud_region.pack(fill="x", padx=12, pady=2)
        self.cloud_key = ctk.CTkEntry(cloud_frame, placeholder_text="Access key")
        self.cloud_key.pack(fill="x", padx=12, pady=2)
        self.cloud_secret = ctk.CTkEntry(cloud_frame, placeholder_text="Secret key", show="*")
        self.cloud_secret.pack(fill="x", padx=12, pady=(2, 8))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=26, pady=6)
        self.upload_button = ctk.CTkButton(actions, text="Upload backup to cloud",
                                          command=self.upload_cloud)
        self.upload_button.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.download_button = ctk.CTkButton(actions, text="Download cloud backup",
                                            command=self.download_cloud)
        self.download_button.pack(side="left", expand=True, fill="x", padx=4)
        self.restore_button = ctk.CTkButton(actions, text="Restore to iPhone",
                                           fg_color="#ad502d", hover_color="#853b21",
                                           command=self.restore)
        self.restore_button.pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.log = ctk.CTkTextbox(self, height=120, state="disabled")
        self.log.pack(fill="both", expand=True, padx=26, pady=(12, 20))
        self.write_log("Connect and unlock your iPhone, then tap Trust on the device.")
        self.after(100, self.poll_events)

    def write_log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def browse(self) -> None:
        selected = filedialog.askdirectory(title="Choose backup folder")
        if selected:
            self.directory.set(selected)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self.detect_button, self.start_button, self.browse_button,
                       self.directory_entry, self.full_checkbox, self.upload_button,
                       self.download_button, self.restore_button):
            widget.configure(state=state)

    def spawn(self, kind: str, worker) -> None:
        if self.busy:
            return
        self.set_busy(True)
        def run() -> None:
            try:
                asyncio.run(worker())
            except Exception as exc:
                self.events.put(("error", exc))
            finally:
                self.events.put(("finished", kind))
        threading.Thread(target=run, daemon=True, name=f"usb-{kind}").start()

    def detect(self) -> None:
        self.status.configure(text="Checking USB connection...")
        self.write_log("Detecting USB device...")
        async def worker() -> None:
            device = await probe_device()
            self.events.put(("device", device))
        self.spawn("detect", worker)

    def start(self) -> None:
        raw = self.directory.get().strip()
        if not raw:
            messagebox.showerror("Missing destination", "Choose a backup folder.")
            return
        directory = Path(raw).expanduser()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.is_dir():
                raise OSError("Destination is not a directory")
        except OSError as exc:
            messagebox.showerror("Invalid destination", str(exc))
            return

        self.progress.set(0)
        self.status.configure(text="Backing up — keep device connected...")
        self.write_log(f"Starting backup into {directory}")
        full = bool(self.full_backup.get())

        async def worker() -> None:
            device = await backup_device(
                directory,
                full=full,
                progress=lambda pct: self.events.put(("progress", pct)),
            )
            self.events.put(("backup_success", device))
        self.spawn("backup", worker)

    def poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "device":
                    self.device = payload
                    self.device_label.configure(text=f"{payload.name} · {payload.version} · {payload.udid}")
                    self.status.configure(text="USB device ready")
                    self.write_log(f"Connected: {payload.name} ({payload.version})")
                elif event == "progress":
                    value = max(0.0, min(100.0, float(payload)))
                    self.progress.set(value / 100)
                    self.status.configure(text=f"Backup in progress: {value:.1f}%")
                elif event == "backup_success":
                    self.device = payload
                    self.progress.set(1)
                    self.status.configure(text="Backup completed successfully")
                    self.write_log(f"Backup finished for {payload.name}")
                    messagebox.showinfo("Backup complete", "Your local backup has completed.")
                elif event == "cloud_progress":
                    done, total = payload
                    self.progress.set(done / total if total else 0)
                    self.status.configure(text=f"Cloud transfer: {done}/{total} files")
                elif event == "cloud_list":
                    from tkinter import simpledialog
                    settings, root, names = payload
                    if not names:
                        self.status.configure(text="No completed cloud backups found")
                        self.write_log("No completed cloud backups found.")
                    else:
                        source = simpledialog.askstring(
                            "Download cloud backup",
                            "Available device backup IDs:\\n" + "\\n".join(names) +
                            "\\n\\nEnter the ID to download:", initialvalue=names[0], parent=self
                        )
                        if source:
                            source = source.strip()
                            if source in names:
                                # The list worker still owns the busy state until 'finished'.
                                self.events.put(("download_request", (settings, root, source)))
                            else:
                                messagebox.showerror("Invalid backup", "Choose an ID shown in the list.")
                elif event == "download_request":
                    settings, root, source = payload
                    self.after(150, lambda s=settings, r=root, u=source:
                               self.download_selected(s, r, u))
                elif event == "notice":
                    self.progress.set(1)
                    self.status.configure(text=str(payload))
                    self.write_log(str(payload))
                    messagebox.showinfo("IPHONE-BACKUP", str(payload))
                elif event == "error":
                    msg = str(payload) if isinstance(payload, BackupError) else f"Unexpected error: {payload}"
                    self.status.configure(text="Operation failed")
                    self.write_log("ERROR: " + msg)
                    messagebox.showerror("IPHONE-BACKUP", msg)
                elif event == "finished":
                    self.set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self.poll_events)

    def cloud_settings(self) -> CloudSettings:
        return CloudSettings(
            bucket=self.cloud_bucket.get().strip(),
            endpoint=self.cloud_endpoint.get().strip(),
            region=self.cloud_region.get().strip(),
            access_key=self.cloud_key.get().strip(),
            secret_key=self.cloud_secret.get(),
        )

    def local_root(self) -> Path:
        return Path(self.directory.get().strip()).expanduser()

    def upload_cloud(self) -> None:
        root = self.local_root()
        backups = available_local_backups(root)
        if not backups:
            messagebox.showerror("No local backup", "Create a backup before uploading to cloud.")
            return
        # Prefer backup of current connected phone if known.
        source = self.device.udid if self.device and self.device.udid in backups else backups[0]
        if len(backups) > 1 and (not self.device or self.device.udid not in backups):
            messagebox.showinfo("Backup selection", f"Using backup: {source}")
        settings = self.cloud_settings()
        if not messagebox.askyesno(
            "Cloud backup privacy",
            "This uploads potentially sensitive iPhone data to your configured cloud bucket. "
            "Use an encrypted iPhone backup and private cloud storage. Continue?"
        ):
            return
        self.status.configure(text="Uploading cloud backup...")
        async def worker() -> None:
            import asyncio
            await asyncio.to_thread(
                upload_backup, settings, root, source,
                lambda done, total: self.events.put(("cloud_progress", (done, total))),
            )
            self.events.put(("notice", "Cloud upload completed."))
        self.spawn("cloud-upload", worker)

    def download_cloud(self) -> None:
        from tkinter import simpledialog
        settings = self.cloud_settings()
        root = self.local_root()
        try:
            # Listing is performed on a worker thread to keep GUI responsive.
            pass
        except Exception:
            pass
        async def worker() -> None:
            import asyncio
            names = await asyncio.to_thread(list_cloud_backups, settings)
            self.events.put(("cloud_list", (settings, root, names)))
        self.status.configure(text="Loading cloud backups...")
        self.spawn("cloud-list", worker)

    def download_selected(self, settings: CloudSettings, root: Path, source: str) -> None:
        self.status.configure(text="Downloading cloud backup...")
        async def worker() -> None:
            import asyncio
            await asyncio.to_thread(
                download_backup, settings, root, source,
                lambda done, total: self.events.put(("cloud_progress", (done, total))),
            )
            self.events.put(("notice", f"Cloud backup {source} downloaded and verified."))
        self.spawn("cloud-download", worker)

    def restore(self) -> None:
        from tkinter import simpledialog
        root = self.local_root()
        backups = available_local_backups(root)
        if not backups:
            messagebox.showerror("No backup", "Download or create a backup first.")
            return
        default = self.device.udid if self.device and self.device.udid in backups else backups[0]
        source = simpledialog.askstring("Select local backup",
            "Available backup IDs:\\n" + "\\n".join(backups) + "\\n\\nEnter backup ID:",
            initialvalue=default, parent=self)
        if source is None:
            return
        source = source.strip()
        if source not in backups:
            messagebox.showerror("Invalid backup", "Choose a backup ID from the list.")
            return
        if not messagebox.askyesno(
            "Restore may replace data",
            "Restoring can replace existing data on the connected iPhone. "
            "First create a separate current backup and keep the USB cable connected. "
            f"Restore backup {source}?", icon="warning",
        ):
            return
        password = simpledialog.askstring(
            "Backup password", "If the backup is encrypted, enter its password. "
            "Otherwise leave blank:", show="*", parent=self
        )
        if password is None:
            return
        self.progress.set(0)
        self.status.configure(text="Restoring backup over USB...")
        async def worker() -> None:
            device = await restore_device(
                root, source=source, password=password,
                progress=lambda pct: self.events.put(("progress", pct)),
            )
            self.events.put(("notice", f"Restore completed for {device.name}."))
        self.spawn("restore", worker)


if __name__ == "__main__":
    BackupApp().mainloop()
