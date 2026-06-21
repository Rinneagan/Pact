"""
Download functionality for Pact PDF application.
Handles PDF downloads with progress tracking and queue management.
"""

from __future__ import annotations

import os
import re
from typing import Any

import customtkinter as ctk
import requests

from utils.typography import PremiumTypography


class DownloadManager:
    """Manages PDF downloads with progress tracking and queue management."""

    def __init__(self, app):
        self.app = app
        self.download_queue_frame = None
        self.download_slots: dict[int, dict[str, Any]] = {}

    def setup_ui(self, footer_frame):
        """Set up the download queue UI in the footer."""
        self.download_queue_frame = ctk.CTkFrame(
            footer_frame, fg_color="transparent",
        )
        self.download_queue_frame.grid(row=0, column=1, sticky="e", padx=20, pady=10)

        for i in range(3):
            self.download_queue_frame.grid_columnconfigure(i, weight=0)
        self.download_queue_frame.grid_rowconfigure(0, weight=0)

    def download_pdf(self) -> None:
        """Initiate a PDF download."""
        if not self.app.selected_pdf_url:
            self.app._show_error("No PDF selected")
            return

        active_count = sum(
            1 for info in self.app.active_downloads.values() if info.get("active")
        )
        if active_count >= 3:
            self.app._show_error("Maximum 3 concurrent downloads")
            return

        if self.app.validate_url and not self.app.validate_url(self.app.selected_pdf_url):
            self.app._show_error("Invalid URL")
            return

        self.app.executor.submit(
            self.download_worker, self.app.selected_pdf_url, self.app.selected_pdf_title
        )

    def download_worker(self, url: str, filename: str) -> None:
        """Worker thread for downloading a PDF."""
        save_dir = self.app.selected_directory or self.app.default_download_dir
        
        # Security: Sanitize filename to prevent path traversal and ensure safe extension/length
        clean_name = re.sub(r'[\\/:*?"<>|]', "_", filename)
        base, ext = os.path.splitext(clean_name)
        if not ext.lower().endswith(".pdf"):
            ext = ".pdf"
        clean_name = base[:150] + ext
        
        save_path = os.path.join(save_dir, clean_name)

        # Security check: verify containment within the target directory
        save_path = os.path.abspath(save_path)
        real_save_dir = os.path.abspath(save_dir)
        if not save_path.startswith(real_save_dir + os.sep) and save_path != real_save_dir:
            self.app._ui(lambda: self.app._show_error("Invalid download destination"))
            return

        # Prevent silent overwrites by appending a counter
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base} ({counter}){ext}"
            counter += 1

        # Grab the updated filename so the UI and the "Read" button use the right file
        actual_filename = os.path.basename(save_path)

        # Calculate the ID using the actual filename to prevent queue collisions
        download_id = id(actual_filename) ^ id(url)

        try:
            self.app._ui(lambda: self.add_download_to_queue(download_id, actual_filename))
            self.app.active_downloads[download_id] = {"active": True, "filename": actual_filename}

            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length", 0))

            if total_size > self.app.max_file_size:
                mb = total_size / (1024 * 1024)
                self.app._ui(lambda: self.app._show_error(f"File too large ({mb:.1f} MB)"))
                self.app._ui(lambda: self.remove_download_from_queue(download_id))
                return

            downloaded = 0
            cancelled = False
            with open(save_path, "wb") as fh:
                for chunk in response.iter_content(chunk_size=1024):
                    if not self.app.active_downloads.get(download_id, {}).get("active"):
                        cancelled = True
                        break
                    downloaded += len(chunk)
                    if downloaded > self.app.max_file_size:
                        mb = self.app.max_file_size / (1024 * 1024)
                        self.app._ui(lambda: self.app._show_error(f"File too large (exceeded {mb:.1f} MB limit)"))
                        cancelled = True
                        break
                    fh.write(chunk)
                    progress = (downloaded / total_size * 100) if total_size else 0
                    self.app._ui(lambda p=progress: self.update_download_progress(download_id, p))

            if cancelled or not self.app.active_downloads.get(download_id, {}).get("active"):
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                self.app._ui(lambda: self.remove_download_from_queue(download_id))
                return

            if self.app.validate_pdf_file and not self.app.validate_pdf_file(save_path):
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                self.app._ui(lambda: self.app._show_error("Downloaded file is not a valid PDF"))
                self.app._ui(lambda: self.remove_download_from_queue(download_id))
                return

            self.app._ui(lambda: self.download_complete(download_id, actual_filename))

        except Exception as exc:
            msg = str(exc)
            self.app._ui(lambda: self.app._show_error(f"Download failed: {msg}"))
            self.app._ui(lambda: self.remove_download_from_queue(download_id))
        finally:
            if download_id in self.app.active_downloads:
                self.app.active_downloads[download_id]["active"] = False

    def find_free_slot(self) -> int:
        """Find a free slot in the download queue."""
        used = {info["slot"] for info in self.download_slots.values()}
        for i in range(3):
            if i not in used:
                return i
        return -1

    def add_download_to_queue(self, download_id: int, filename: str) -> None:
        """Add a download to the queue UI."""
        slot_index = self.find_free_slot()
        if slot_index == -1:
            return

        slot_frame = ctk.CTkFrame(self.download_queue_frame)
        slot_frame.grid(row=0, column=slot_index, padx=5, pady=5)

        progress_bar = ctk.CTkProgressBar(slot_frame, width=150)
        progress_bar.grid(row=0, column=0, padx=5, pady=5)
        progress_bar.set(0)

        cancel_btn = ctk.CTkButton(
            slot_frame, text="✕", width=30, height=30,
            command=lambda: self.cancel_download(download_id),
        )
        cancel_btn.grid(row=0, column=1, padx=5, pady=5)

        self.download_slots[download_id] = {
            "slot": slot_index,
            "frame": slot_frame,
            "progress_bar": progress_bar,
        }

    def remove_download_from_queue(self, download_id: int) -> None:
        """Remove a download from the queue UI."""
        slot = self.download_slots.pop(download_id, None)
        if slot and slot["frame"].winfo_exists():
            slot["frame"].destroy()

    def update_download_progress(self, download_id: int, progress: float) -> None:
        """Update the progress bar for a download."""
        slot = self.download_slots.get(download_id)
        if slot:
            slot["progress_bar"].set(progress / 100)

    def download_complete(self, download_id: int, filename: str) -> None:
        """Handle download completion."""
        self.app.status_label.configure(text=f"Downloaded: {filename}")

        slot = self.download_slots.get(download_id)
        if not slot:
            self.app._refresh_downloads_list()
            return

        slot["progress_bar"].set(1.0)

        save_dir = self.app.selected_directory or self.app.default_download_dir
        save_path = os.path.join(save_dir, filename)

        for widget in slot["frame"].winfo_children():
            if isinstance(widget, ctk.CTkButton):
                widget.destroy()

        read_btn = ctk.CTkButton(
            slot["frame"],
            text="📖 Read",
            width=60, height=30,
            font=PremiumTypography.button_text(size=12),
            fg_color="#639922", hover_color="#4F7A1B",
            command=lambda p=save_path, f=filename: self.app._open_reader(p, f),
        )
        read_btn.grid(row=0, column=1, padx=5, pady=5)

        self.app._refresh_downloads_list()

    def cancel_download(self, download_id: int) -> None:
        """Cancel an active download."""
        if download_id in self.app.active_downloads:
            self.app.active_downloads[download_id]["active"] = False
        self.remove_download_from_queue(download_id)
        self.app.status_label.configure(text="Download cancelled")
