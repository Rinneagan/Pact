"""
Library view functionality for Pact PDF application.
Manages the library grid view with thumbnails, tags, and recency grouping.
"""

from __future__ import annotations

import datetime
import os
from typing import Any

import customtkinter as ctk

from utils.typography import PremiumTypography


_RECENCY_BUCKET_ORDER = ["Today", "Yesterday", "This Week", "This Month", "Earlier"]


def _recency_bucket(mtime: float) -> str:
    """Determine the recency bucket for a file based on its modification time."""
    now = datetime.datetime.now()
    dt = datetime.datetime.fromtimestamp(mtime)
    days = (now.date() - dt.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days <= 7:
        return "This Week"
    if days <= 30:
        return "This Month"
    return "Earlier"


class LibraryManager:
    """Manages the library grid view with thumbnails and tags."""

    def __init__(self, app):
        self.app = app
        self.library_frame = None
        self.library_btn = None

    def setup_ui(self, main_content_frame, library_btn):
        """Set up the library UI components."""
        self.library_frame = ctk.CTkScrollableFrame(
            main_content_frame,
            label_text="Library",
            label_font=PremiumTypography.heading_medium(),
            corner_radius=14,
            fg_color="transparent",
            label_text_color=("#2C2C2A", "gray90"),
        )
        self.library_frame.grid(row=0, column=0, sticky="nsew")
        self.library_frame.grid_remove()
        self.library_btn = library_btn

    def toggle_library_view(self) -> None:
        """Toggle between library view and search results."""
        if self.app.reader_view is not None:
            # Closing the reader already restores whichever view was active
            # before it opened; force that back to "library" since that's
            # specifically what was just requested.
            self.app._reader_return_view = "library"
            self.app._close_reader_view()
            return
        if self.library_frame.winfo_ismapped():
            self.close_library_view()
        else:
            self.open_library_view()

    def open_library_view(self) -> None:
        """Open the library view."""
        self.app.search_manager.hide_results()
        self.library_frame.grid()
        self.library_btn.configure(fg_color=("#E1EFC9", "gray30"))
        self.populate_library_grid()
        self.app.status_label.configure(text="Library")

    def close_library_view(self) -> None:
        """Close the library view and return to search results."""
        self.library_frame.grid_remove()
        self.app.search_manager.show_results()
        self.library_btn.configure(fg_color=("#F3F1EA", "gray22"))
        self.app.status_label.configure(text="Ready")

    def refresh_library_view_if_open(self) -> None:
        """Refresh the library view if it's currently open."""
        if hasattr(self, "library_frame") and self.library_frame.winfo_ismapped():
            self.populate_library_grid()

    def populate_library_grid(self) -> None:
        """Populate the library grid with PDF files."""
        for widget in self.library_frame.winfo_children():
            widget.destroy()

        downloads_dir = self.app._get_downloads_dir()
        try:
            entries = [
                f for f in os.listdir(downloads_dir)
                if f.lower().endswith(".pdf")
                and os.path.isfile(os.path.join(downloads_dir, f))
            ]
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            entries = []

        if not entries:
            ctk.CTkLabel(
                self.library_frame,
                text="Your library is empty\nSearch and download, or drag a PDF in, to get started",
                font=PremiumTypography.body_text(),
                text_color="gray",
                justify="center",
            ).pack(pady=40)
            return

        items = []
        for f in entries:
            fpath = os.path.join(downloads_dir, f)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                mtime = 0
            items.append((fpath, f, mtime))

        tagged_groups: dict[str, list] = {}
        untagged: list = []
        for fpath, fname, mtime in items:
            tags = self.app.tag_store.get(fpath)
            if tags:
                for t in tags:
                    tagged_groups.setdefault(t, []).append((fpath, fname, mtime))
            else:
                untagged.append((fpath, fname, mtime))

        for tag in sorted(tagged_groups.keys()):
            group_items = sorted(tagged_groups[tag], key=lambda t: t[2], reverse=True)
            self.render_library_section(f"🏷 {tag}", group_items)

        buckets: dict[str, list] = {b: [] for b in _RECENCY_BUCKET_ORDER}
        for fpath, fname, mtime in untagged:
            buckets[_recency_bucket(mtime)].append((fpath, fname, mtime))

        for bucket in _RECENCY_BUCKET_ORDER:
            group_items = sorted(buckets[bucket], key=lambda t: t[2], reverse=True)
            if group_items:
                self.render_library_section(bucket, group_items)

    def render_library_section(self, header: str, items: list) -> None:
        """Render a section of the library grid."""
        section = ctk.CTkFrame(self.library_frame, fg_color="transparent")
        section.pack(fill="x", pady=(6, 12), padx=4)

        ctk.CTkLabel(
            section, text=header, font=PremiumTypography.heading_small(size=14),
            text_color=("#2C2C2A", "gray90"), anchor="w",
        ).pack(fill="x", padx=6, pady=(0, 8))

        grid = ctk.CTkFrame(section, fg_color="transparent")
        grid.pack(fill="x")
        cols = 4
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1)

        for idx, (fpath, fname, _mtime) in enumerate(items):
            card = self.create_library_card(grid, fpath, fname)
            card.grid(row=idx // cols, column=idx % cols, padx=6, pady=6, sticky="nsew")

    def create_library_card(self, parent, filepath: str, filename: str) -> ctk.CTkFrame:
        """Create a library card for a PDF file."""
        card = ctk.CTkFrame(
            parent, width=158, height=240, corner_radius=12,
            fg_color=("#FFFFFF", "gray20"),
            border_width=1, border_color=("#ECE9E2", "gray30"),
        )
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)

        thumb_label = ctk.CTkLabel(
            card, text="📄", font=ctk.CTkFont(size=40),
            fg_color=("#F3F1EA", "gray25"), corner_radius=8,
            width=138, height=164,
        )
        thumb_label.grid(row=0, column=0, padx=10, pady=(10, 6))

        display = filename if len(filename) <= 22 else filename[:19] + "…"
        ctk.CTkLabel(
            card, text=display, font=PremiumTypography.body_small(size=11),
            anchor="w", wraplength=138, justify="left",
        ).grid(row=1, column=0, padx=10, sticky="w")

        tags = self.app.tag_store.get(filepath)
        tag_text = " ".join(f"#{t}" for t in tags[:2]) if tags else ""
        tag_label = ctk.CTkLabel(
            card, text=tag_text, font=PremiumTypography.body_small(size=9),
            text_color=("#639922", "#97C459"), anchor="w",
        )
        tag_label.grid(row=2, column=0, padx=10, pady=(2, 6), sticky="w")

        tag_btn = ctk.CTkButton(
            card, text="🏷+", width=24, height=20, corner_radius=6,
            font=ctk.CTkFont(size=10), fg_color=("#FFFFFF", "gray20"),
            hover_color=("#E1EFC9", "gray30"), text_color="gray",
            command=lambda p=filepath: self.prompt_add_tag(p),
        )
        tag_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=6)

        open_cb = lambda e, p=filepath, f=filename: self.app._open_reader(p, f)
        for w in (card, thumb_label):
            w.bind("<Button-1>", open_cb)

        self.app.executor.submit(self.load_library_thumbnail, filepath, thumb_label)

        return card

    def load_library_thumbnail(self, filepath: str, label_widget: ctk.CTkLabel) -> None:
        """Load and display a thumbnail for a library card."""
        img = self.app.thumbnail_cache.get(filepath)
        if img is None:
            return

        def apply() -> None:
            if not label_widget.winfo_exists():
                return
            try:
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(138, 164))
                label_widget.configure(image=ctk_img, text="")
                label_widget.image = ctk_img
            except Exception:
                pass

        self.app._ui(apply)

    def prompt_add_tag(self, filepath: str) -> None:
        """Prompt the user to add a tag to a document."""
        dialog = ctk.CTkInputDialog(text="Tag this document:", title="Add Tag")
        tag = dialog.get_input()
        if tag:
            self.app.tag_store.set_tag(filepath, tag)
            self.refresh_library_view_if_open()
