"""
Drag-and-drop functionality for Pact PDF application.
Handles importing PDFs by dragging them into the application window.
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Any

# Optional dependency
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False


class DragDropManager:
    """Manages drag-and-drop PDF import functionality."""

    def __init__(self, app):
        self.app = app

    def setup_drag_and_drop(self) -> None:
        """Set up drag-and-drop event handlers if tkinterdnd2 is available."""
        if not TKDND_AVAILABLE:
            print("tkinterdnd2 not installed — drag-and-drop import disabled")
            return

        try:
            self.app.root.drop_target_register(DND_FILES)
            self.app.root.dnd_bind("<<Drop>>", self.on_files_dropped)
            self.app.root.dnd_bind("<<DragEnter>>", self.on_drag_enter)
            self.app.root.dnd_bind("<<DragLeave>>", self.on_drag_leave)
        except Exception as exc:
            print(f"Drag-and-drop setup failed: {exc}")

    def on_drag_enter(self, event: Any) -> None:
        """Handle drag enter event - highlight the drop zone."""
        self.app.main_view_frame.configure(border_width=2, border_color="#639922")

    def on_drag_leave(self, event: Any) -> None:
        """Handle drag leave event - remove highlight."""
        self.app.main_view_frame.configure(border_width=0)

    def on_files_dropped(self, event: Any) -> None:
        """Handle files dropped onto the application window."""
        self.app.main_view_frame.configure(border_width=0)
        paths = []
        try:
            raw_paths = self.app.root.tk.splitlist(event.data)
            for p in raw_paths:
                p_clean = p.strip().strip('{}').strip()
                if p_clean:
                    paths.append(p_clean)
        except Exception:
            import re
            matches = re.findall(r'\{([^}]+)\}|(\S+)', event.data)
            for m1, m2 in matches:
                p_clean = (m1 or m2).strip().strip('{}').strip()
                if p_clean:
                    paths.append(p_clean)

        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        if not pdfs:
            self.app._show_error("Drop a PDF file to import it")
            return

        for src in pdfs:
            self.app.executor.submit(self.import_dropped_pdf, src)

    def import_dropped_pdf(self, src_path: str) -> None:
        """Import a dropped PDF file into the downloads directory."""
        try:
            if not os.path.isfile(src_path):
                self.app._ui(lambda: self.app._show_error(f"File not found: {os.path.basename(src_path)}"))
                return

            if self.app.validate_pdf_file and not self.app.validate_pdf_file(src_path):
                name = os.path.basename(src_path)
                self.app._ui(lambda n=name: self.app._show_error(f"Not a valid PDF: {n}"))
                return

            dest_dir = self.app._get_downloads_dir()
            os.makedirs(dest_dir, exist_ok=True)
            
            # Security: Sanitize the destination filename to prevent traversal/illegal characters
            raw_name = os.path.basename(src_path)
            clean_name = re.sub(r'[\\/:*?"<>|]', "_", raw_name)
            base, ext = os.path.splitext(clean_name)
            if not ext.lower().endswith(".pdf"):
                ext = ".pdf"
            clean_name = base[:150] + ext

            dest_path = os.path.join(dest_dir, clean_name)

            # Security check: verify containment within the destination directory
            dest_path = os.path.abspath(dest_path)
            real_dest_dir = os.path.abspath(dest_dir)
            if not dest_path.startswith(real_dest_dir + os.sep) and dest_path != real_dest_dir:
                self.app._ui(lambda: self.app._show_error("Invalid destination path"))
                return

            if os.path.abspath(src_path) != os.path.abspath(dest_path):
                base, ext = os.path.splitext(dest_path)
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = f"{base} ({counter}){ext}"
                    counter += 1
                shutil.copy2(src_path, dest_path)

            imported_name = os.path.basename(dest_path)
            self.app._ui(lambda n=imported_name: self.app.status_label.configure(text=f"Imported: {n}"))
            self.app._ui(self.app._refresh_downloads_list)
        except Exception as exc:
            msg = str(exc)
            self.app._ui(lambda: self.app._show_error(f"Import failed: {msg}"))
