"""
Library view functionality for Pact PDF application.
Manages the library grid view with thumbnails, tags, and recency grouping.
"""

from __future__ import annotations

import datetime
import hashlib
import os
from typing import Any

import customtkinter as ctk

from utils.typography import PremiumTypography
from utils import NamidaTheme, NamidaIcons


_RECENCY_BUCKET_ORDER = ["Today", "Yesterday", "This Week", "This Month", "Earlier"]

# Spine colors for library cards (light, dark) tuples
_SPINE_COLORS = [
    ("#00A3C4", "#00E5FF"), # Neon Cyan
    ("#7A00E0", "#9D00FF"), # Neon Purple
    ("#0F6E56", "#00E676"), # Teal / Neon Green
    ("#993C1D", "#FF9100"), # Terracotta / Neon Orange
    ("#3B6D11", "#A8E6CF"), # Moss / Green
    ("#FF5B5B", "#FF8A8A"), # Red / Coral
    ("#FF9F43", "#FFC38A"), # Orange
    ("#F1C40F", "#FFEAA7"), # Yellow
    ("#3498DB", "#A2D5F2"), # Blue
]


def _get_spine_color(tag: str) -> tuple[str, str]:
    if not tag:
        return ("#D8E2ED", "#202A3C") # Using NamidaTheme.BORDER
    val = sum(ord(c) for c in tag)
    return _SPINE_COLORS[val % len(_SPINE_COLORS)]


def _recency_bucket(mtime: float) -> str:
    """Determine the recency bucket for a file based on its modification time."""
    dt = datetime.datetime.fromtimestamp(mtime)
    today = datetime.date.today()
    diff = today - dt.date()
    days = diff.days

    if days == 0:
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
            fg_color=NamidaTheme.BG_MAIN,
            label_text_color=NamidaTheme.TEXT_PRIMARY,
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
        self.library_btn.configure(fg_color=NamidaTheme.ACCENT_HOVER)
        self.populate_library_grid()
        self.app.status_label.configure(text="Library")

    def close_library_view(self) -> None:
        """Close the library view and return to search results."""
        self.library_frame.grid_remove()
        self.app.search_manager.show_results()
        self.library_btn.configure(fg_color=NamidaTheme.BG_CARD)
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
                text_color=NamidaTheme.TEXT_MUTED,
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
            text_color=NamidaTheme.TEXT_MUTED, anchor="w",
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
        """Create a library card for a PDF file with colored spine stripe."""
        card = ctk.CTkFrame(
            parent, width=158, height=240, corner_radius=12,
            fg_color=NamidaTheme.BG_CARD,
            border_width=1, border_color=NamidaTheme.BORDER,
        )
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=0)  # Spine
        card.grid_columnconfigure(1, weight=1)  # Content

        # Get spine color based on first tag
        tags = self.app.tag_store.get(filepath)
        first_tag = tags[0] if tags else ""
        spine_color = _get_spine_color(first_tag)

        # Colored spine stripe on left edge, inset to prevent corner bleeding
        spine = ctk.CTkFrame(
            card, width=6, corner_radius=3,
            fg_color=spine_color,
        )
        spine.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(6, 0), pady=12)

        # Content frame
        content_frame = ctk.CTkFrame(card, fg_color="transparent")
        content_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=8, pady=8)
        content_frame.grid_columnconfigure(0, weight=1)

        thumb_label = ctk.CTkLabel(
            content_frame, text="",
            image=NamidaIcons.get("library", size=48, light_color=NamidaTheme.ACCENT_PRIMARY[0], dark_color=NamidaTheme.ACCENT_PRIMARY[1]),
            fg_color=NamidaTheme.BG_CARD_SECONDARY, corner_radius=8,
            width=130, height=164,
        )
        thumb_label.grid(row=0, column=0, padx=0, pady=(0, 6))

        display = filename if len(filename) <= 22 else filename[:19] + "…"
        title_label = ctk.CTkLabel(
            content_frame, text=display, font=PremiumTypography.body_small(size=11),
            text_color=NamidaTheme.TEXT_PRIMARY,
            anchor="w", wraplength=130, justify="left",
        )
        title_label.grid(row=1, column=0, padx=0, sticky="w")

        tag_text = " ".join(f"#{t}" for t in tags[:2]) if tags else ""
        tag_label = ctk.CTkLabel(
            content_frame, text=tag_text, font=PremiumTypography.body_small(size=9),
            text_color=NamidaTheme.ACCENT_PRIMARY, anchor="w",
        )
        tag_label.grid(row=2, column=0, padx=0, pady=(2, 0), sticky="w")

        tag_btn = ctk.CTkButton(
            content_frame, text="", width=24, height=20, corner_radius=6,
            fg_color=NamidaTheme.BG_CARD_SECONDARY,
            hover_color=NamidaTheme.ACCENT_HOVER,
            image=NamidaIcons.get("bookmark", size=10, light_color=NamidaTheme.TEXT_MUTED[0], dark_color=NamidaTheme.TEXT_MUTED[1]),
            command=lambda p=filepath: self.prompt_add_tag(p),
        )
        tag_btn.grid(row=2, column=0, padx=0, pady=(2, 0), sticky="e")
        tag_btn.configure(cursor="hand2")

        open_cb = lambda e, p=filepath, f=filename: self.app._open_reader(p, f)
        for w in (card, content_frame, thumb_label, title_label, tag_label):
            w.bind("<Button-1>", open_cb)
            w.configure(cursor="hand2")

        card._hovered = False

        def on_enter(e: Any) -> None:
            if not card._hovered:
                card._hovered = True
                card.configure(
                    border_color=NamidaTheme.ACCENT_PRIMARY,
                    fg_color=NamidaTheme.BG_CARD_SECONDARY,
                )

        def on_leave(e: Any) -> None:
            if card._hovered:
                # Check if mouse is actually outside the card's boundaries
                under_mouse = card.winfo_containing(e.x_root, e.y_root)
                if under_mouse:
                    card_path = str(card)
                    under_path = str(under_mouse)
                    if under_path == card_path or under_path.startswith(card_path + "."):
                        return
                card._hovered = False
                card.configure(
                    border_color=NamidaTheme.BORDER,
                    fg_color=NamidaTheme.BG_CARD,
                )

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

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
