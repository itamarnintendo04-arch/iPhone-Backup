"""IPHONE-BACKUP desktop application."""
from __future__ import annotations

import asyncio
import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from iphone_backup.backup import BackupError, DeviceInfo, backup_device, probe_device

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class BackupApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("IPHONE-BACKUP")
        self.geometry("760x565")
        self.minsize(650, 500)
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

        self.log = ctk.CTkTextbox(self, height=165, state="disabled")
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
                       self.directory_entry, self.full_checkbox):
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


if __name__ == "__main__":
    BackupApp().mainloop()
