"""
Pact - Modern Desktop Application
A secure PDF search and download application with a light, airy aesthetic.

Includes the integrated PactReader, embedded directly in the main window
(no separate popup window), plus draggable, resizable panels.
"""

from __future__ import annotations

import os
import platform
import subprocess
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

import customtkinter as ctk

# Module-level imports with explicit availability flags
try:
    import requests as _requests  # noqa: F401
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from PIL import ImageTk as _ImageTk, Image as _Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False


if TKDND_AVAILABLE:
    class _DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
        """customtkinter's CTk root doesn't natively support OS-level file
        drops. This mixes in TkinterDnD's DnD machinery so the same root
        window can both look like a CTk app and accept dragged-in PDFs."""

        def __init__(self, *args, **kwargs):
            ctk.CTk.__init__(self, *args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    _DnDCTk = ctk.CTk


# Import extracted modules
from persistence import (
    ReadingProgressStore,
    RecentSearchesStore,
    TagStore,
    ThumbnailCache,
    ReadingStatsStore,
)
from utils import PremiumTypography
from reader import PactReaderView
from ui.search import SearchManager
from ui.downloads import DownloadManager
from ui.library import LibraryManager
from ui.drag_drop import DragDropManager
from ui.reading_stats import ReadingStatsManager


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class PactApp:
    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.root = _DnDCTk()
        self.root.title("Pact")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 700)
        self.root.configure(fg_color=("#FAF9F6", "gray13"))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.is_dark_theme: bool = False
        self.selected_directory: str = ""
        self.search_results: list[str] = []
        self.active_downloads: dict[int, dict[str, Any]] = {}
        self.selected_pdf_url: str = ""
        self.selected_pdf_title: str = ""
        self.is_searching: bool = False

        self._skeleton_running: bool = False
        self._skeleton_phase: float = 0.0

        # Tracks the currently embedded reader view (None when showing search)
        self.reader_view: Optional[PactReaderView] = None
        # Which view to return to when the reader's Back button is used.
        self._reader_return_view: str = "results"

        # Initialize persistence stores
        self.progress_store = ReadingProgressStore()
        self.recent_searches = RecentSearchesStore()
        self.tag_store = TagStore()
        self.thumbnail_cache = ThumbnailCache()
        self.stats_store = ReadingStatsStore()

        # Initialize managers
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.search_manager = SearchManager(self)
        self.download_manager = DownloadManager(self)
        self.library_manager = LibraryManager(self)
        self.drag_drop_manager = DragDropManager(self)
        self.reading_stats_manager = ReadingStatsManager(self)

        self._setup_grid_layout()
        self._create_zone_frames()
        self._populate_sidebar()
        self._populate_main_view()
        self._populate_preview_pane()
        self._populate_footer()

        self._import_backend()
        self._refresh_downloads_list()
        self._refresh_continue_reading()
        self.reading_stats_manager.refresh_reading_stats()

        self.drag_drop_manager.setup_drag_and_drop()

        if not REQUESTS_AVAILABLE:
            self._show_error("requests library not installed — downloads disabled")
        if not PIL_AVAILABLE:
            self._show_error("Pillow not installed — PDF preview disabled")
        if not PYMUPDF_AVAILABLE:
            self._show_error("PyMuPDF not installed — Integrated reading disabled")

    def _on_close(self) -> None:
        self._skeleton_running = False
        for info in self.active_downloads.values():
            info["active"] = False
        if self.reader_view is not None:
            self.reader_view.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

    def _ui(self, callback: Callable[[], None]) -> None:
        self.root.after(0, callback)

    def _import_backend(self) -> None:
        try:
            from crawler import search_pdfs, preview_pdf, validate_url, validate_pdf_file
            from config import MAX_SEARCH_RESULTS, DEFAULT_DOWNLOAD_DIR, MAX_FILE_SIZE
            self.search_pdfs = search_pdfs
            self.preview_pdf = preview_pdf
            self.validate_url = validate_url
            self.validate_pdf_file = validate_pdf_file
            self.max_search_results: int = MAX_SEARCH_RESULTS
            self.default_download_dir: str = DEFAULT_DOWNLOAD_DIR
            self.max_file_size: int = MAX_FILE_SIZE
        except ImportError as exc:
            print(f"Warning: backend unavailable — {exc}")
            self.search_pdfs = None
            self.preview_pdf = None
            self.validate_url = None
            self.validate_pdf_file = None
            self.max_search_results = 50
            self.default_download_dir = os.path.expanduser("~/Documents")
            self.max_file_size = 100 * 1024 * 1024

    # ------------------------------------------------------------------
    # Layout — root grid holds the footer; everything above the footer
    # lives inside a resizable PanedWindow (draggable sashes between
    # sidebar / main view / preview pane).
    # ------------------------------------------------------------------
    def _setup_grid_layout(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=0)

    def _create_zone_frames(self) -> None:
        # A plain tk.PanedWindow gives us draggable, resizable sashes.
        # customtkinter doesn't have its own paned-window, so this stays
        # plain tkinter, styled to blend in with the rest of the app and
        # kept in sync with the light/dark toggle via _sync_paned_theme().
        self.paned_window = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            sashrelief="flat",
            sashwidth=5,
            sashpad=0,
            bg="#ECE9E2",
            bd=0,
            opaqueresize=True,
            cursor="sb_h_double_arrow",
        )
        self.paned_window.grid(row=0, column=0, sticky="nsew")

        self.sidebar_frame = ctk.CTkFrame(
            self.paned_window, width=240, corner_radius=0,
            fg_color=("#F3F1EA", "gray17"), border_width=0,
        )
        self.sidebar_frame.grid_rowconfigure(0, weight=0)
        self.sidebar_frame.grid_rowconfigure(1, weight=0)
        self.sidebar_frame.grid_rowconfigure(2, weight=0)
        self.sidebar_frame.grid_rowconfigure(3, weight=0)
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        self.sidebar_frame.grid_rowconfigure(5, weight=0)
        self.sidebar_frame.grid_rowconfigure(6, weight=0)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        self.main_view_frame = ctk.CTkFrame(
            self.paned_window, corner_radius=0, fg_color=("#FAF9F6", "gray14"),
        )
        self.main_view_frame.grid_rowconfigure(0, weight=0)
        self.main_view_frame.grid_rowconfigure(1, weight=1)
        self.main_view_frame.grid_columnconfigure(0, weight=1)

        self.preview_pane_frame = ctk.CTkFrame(
            self.paned_window, width=400, corner_radius=0,
            fg_color=("#F3F1EA", "gray17"),
        )
        self.preview_pane_frame.grid_rowconfigure(0, weight=1)
        self.preview_pane_frame.grid_rowconfigure(1, weight=0)
        self.preview_pane_frame.grid_columnconfigure(0, weight=1)

        # minsize keeps panels from being dragged down to nothing;
        # stretch="always" on the main view lets it absorb extra space.
        self.paned_window.add(self.sidebar_frame, minsize=180, width=240, stretch="never")
        self.paned_window.add(self.main_view_frame, minsize=400, stretch="always")
        self.paned_window.add(self.preview_pane_frame, minsize=280, width=400, stretch="never")

        self.footer_frame = ctk.CTkFrame(
            self.root, height=80, corner_radius=0,
            fg_color=("#FFFFFF", "gray17"),
            border_width=1, border_color=("#ECE9E2", "gray25"),
        )
        self.footer_frame.grid(row=1, column=0, sticky="nsew")
        self.footer_frame.grid_propagate(False)
        self.footer_frame.grid_rowconfigure(0, weight=1)
        self.footer_frame.grid_columnconfigure(0, weight=1)
        self.footer_frame.grid_columnconfigure(1, weight=0)

    def _populate_sidebar(self) -> None:
        self.title_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Pact",
            font=PremiumTypography.heading_large(size=32),
            text_color=("#2C2C2A", "gray90"),
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="ew")

        # --- Continue Reading shelf ---
        self.continue_reading_section = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.continue_reading_section.grid(row=1, column=0, padx=20, pady=(0, 14), sticky="ew")
        self.continue_reading_section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.continue_reading_section,
            text="Continue Reading",
            font=PremiumTypography.heading_small(size=13),
            text_color=("#2C2C2A", "gray90"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.continue_reading_frame = ctk.CTkFrame(self.continue_reading_section, fg_color="transparent")
        self.continue_reading_frame.grid(row=1, column=0, sticky="ew")
        self.continue_reading_frame.grid_columnconfigure(0, weight=1)

        self.continue_reading_section.grid_remove()  # shown once there's progress to display

        # --- Library entry point ---
        self.library_btn = ctk.CTkButton(
            self.sidebar_frame, text="📚  Library", height=38, corner_radius=10,
            anchor="w",
            font=PremiumTypography.button_text(size=13),
            fg_color=("#F3F1EA", "gray22"), hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"),
            command=self.library_manager.toggle_library_view,
        )
        self.library_btn.grid(row=2, column=0, padx=20, pady=(0, 14), sticky="ew")

        downloads_header = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        downloads_header.grid(row=3, column=0, padx=20, pady=(0, 5), sticky="ew")
        downloads_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            downloads_header,
            text="Downloaded Files",
            font=PremiumTypography.heading_small(size=13),
            text_color=("#2C2C2A", "gray90"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.refresh_downloads_btn = ctk.CTkButton(
            downloads_header, text="⟳", width=26, height=26, corner_radius=8,
            font=ctk.CTkFont(size=14),
            fg_color="transparent", hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"),
            command=self._refresh_downloads_list,
        )
        self.refresh_downloads_btn.grid(row=0, column=1, sticky="e")

        self.downloads_list_frame = ctk.CTkScrollableFrame(
            self.sidebar_frame, fg_color=("#FFFFFF", "gray20"), corner_radius=12,
        )
        self.downloads_list_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="nsew")

        self.downloads_empty_label = ctk.CTkLabel(
            self.downloads_list_frame,
            text="No downloads yet",
            font=PremiumTypography.body_small(),
            text_color="gray",
        )
        self.downloads_empty_label.pack(pady=15)

        # --- Reading Log ---
        self.reading_stats_manager.setup_ui(self.sidebar_frame)

        self.theme_switch = ctk.CTkSwitch(
            self.sidebar_frame,
            text="☀️",
            font=ctk.CTkFont(size=20),
            command=self._toggle_theme,
            switch_width=50,
            switch_height=25,
            corner_radius=15,
            progress_color="#639922",
        )
        self.theme_switch.grid(row=6, column=0, padx=20, pady=(0, 30), sticky="se")

    def _toggle_theme(self) -> None:
        self.is_dark_theme = not self.is_dark_theme
        ctk.set_appearance_mode("dark" if self.is_dark_theme else "light")
        self.theme_switch.configure(text="🌙" if self.is_dark_theme else "☀️")
        self._sync_paned_theme()
        self.reading_stats_manager.refresh_reading_stats()

    def _sync_paned_theme(self) -> None:
        """customtkinter doesn't theme plain tk widgets automatically, so the
        PanedWindow's sash color is kept in sync with light/dark mode here."""
        sash_color = "gray25" if self.is_dark_theme else "#ECE9E2"
        self.paned_window.configure(bg=sash_color)

    def _refresh_continue_reading(self) -> None:
        """Rebuild the 'Continue Reading' shelf from the progress store.
        Hides the whole section when there's nothing in progress."""
        for widget in self.continue_reading_frame.winfo_children():
            widget.destroy()

        items = self.progress_store.recent(limit=3)

        if not items:
            self.continue_reading_section.grid_remove()
            return

        self.continue_reading_section.grid()
        for filepath, info in items:
            self._create_continue_reading_card(filepath, info).pack(fill="x", pady=4, padx=2)

    def _create_continue_reading_card(self, filepath: str, info: dict[str, Any]) -> ctk.CTkFrame:
        item = ctk.CTkFrame(
            self.continue_reading_frame, corner_radius=10,
            fg_color=("#FFFFFF", "gray22"),
            border_width=1, border_color=("#E1EFC9", "gray30"),
        )
        item.grid_columnconfigure(0, weight=1)
        item.grid_columnconfigure(1, weight=0)

        title = info.get("title") or os.path.basename(filepath)
        display = title if len(title) <= 24 else title[:21] + "…"
        total = max(info.get("total_pages", 1), 1)
        current = info.get("current_page", 0)
        pct = max(0, min(100, int(((current + 1) / total) * 100)))

        name_label = ctk.CTkLabel(
            item, text=display, font=PremiumTypography.body_small(size=12), anchor="w",
        )
        name_label.grid(row=0, column=0, sticky="w", padx=(10, 4), pady=(8, 2))

        dismiss_btn = ctk.CTkButton(
            item, text="✕", width=20, height=20, corner_radius=6,
            font=ctk.CTkFont(size=10),
            fg_color="transparent", hover_color=("#F3D9D9", "gray30"),
            text_color="gray",
            command=lambda p=filepath: self._dismiss_continue_reading(p),
        )
        dismiss_btn.grid(row=0, column=1, sticky="ne", padx=(0, 6), pady=6)

        bar = ctk.CTkProgressBar(item, height=6, progress_color="#639922")
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 4))
        bar.set(pct / 100)

        pct_label = ctk.CTkLabel(
            item, text=f"{pct}% · p.{current + 1}/{total}",
            font=PremiumTypography.body_small(size=10), text_color="gray", anchor="w",
        )
        pct_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))

        select_cb = lambda e, p=filepath, f=os.path.basename(filepath): self._open_reader(p, f)
        for widget in (item, name_label, bar, pct_label):
            widget.bind("<Button-1>", select_cb)

        return item

    def _dismiss_continue_reading(self, filepath: str) -> None:
        self.progress_store.remove(filepath)
        self._refresh_continue_reading()

    def _populate_main_view(self) -> None:
        self.main_content_frame = ctk.CTkFrame(
            self.main_view_frame, fg_color="transparent",
        )
        self.main_content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

        self.error_label = ctk.CTkLabel(
            self.main_view_frame,
            text="",
            text_color="red",
            font=PremiumTypography.body_small(),
        )
        self.error_label.grid(row=0, column=0, sticky="s", padx=20, pady=(0, 10))

        # Set up library manager UI first (creates library_frame)
        self.library_manager.setup_ui(self.main_content_frame, self.library_btn)

        # Set up search manager UI (now library_frame exists)
        self.search_manager.setup_ui(
            self.main_view_frame,
            self.main_content_frame,
            self.library_manager.library_frame,
            self.error_label
        )

    def _populate_preview_pane(self) -> None:
        self.preview_frame = ctk.CTkFrame(
            self.preview_pane_frame, corner_radius=14,
            fg_color=("#F3F1EA", "gray20"),
        )
        self.preview_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.preview_frame.grid_rowconfigure(0, weight=1)
        self.preview_frame.grid_columnconfigure(0, weight=1)

        self.preview_placeholder = ctk.CTkLabel(
            self.preview_frame,
            text="No PDF Selected\nSelect a PDF to preview",
            font=PremiumTypography.body_text(),
            text_color="gray",
        )
        self.preview_placeholder.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        self.details_frame = ctk.CTkFrame(
            self.preview_pane_frame, corner_radius=14,
            fg_color=("#FFFFFF", "gray20"),
        )
        self.details_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))

        self.details_label = ctk.CTkLabel(
            self.details_frame,
            text="Document Details",
            font=PremiumTypography.heading_small(),
            text_color=("#2C2C2A", "gray90"),
        )
        self.details_label.grid(row=0, column=0, sticky="w", padx=15, pady=15)

        self.download_button = ctk.CTkButton(
            self.preview_pane_frame,
            text="Download PDF",
            font=PremiumTypography.button_text(),
            height=44, corner_radius=14,
            fg_color="#639922", hover_color="#4F7A1B",
            command=self.download_manager.download_pdf,
        )
        self.download_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.preview_pane_frame.grid_rowconfigure(2, weight=0)

    def _populate_footer(self) -> None:
        self.status_label = ctk.CTkLabel(
            self.footer_frame,
            text="Ready",
            font=PremiumTypography.body_small(),
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="w", padx=20, pady=10)

        # Set up download manager UI
        self.download_manager.setup_ui(self.footer_frame)

    def _preview_worker(self, url: str) -> None:
        """Worker thread for PDF preview generation."""
        try:
            if not self.preview_pdf:
                self._ui(lambda: self._show_error("Preview not available"))
                return
            image = self.preview_pdf(url)
            if image:
                self._ui(lambda: self._update_preview_image(image))
            else:
                self._ui(lambda: self._show_error("Could not generate preview"))
        except Exception as exc:
            msg = str(exc)
            self._ui(lambda: self._show_error(f"Preview failed: {msg}"))

    def _update_preview_image(self, image: Any) -> None:
        """Update the preview image in the UI."""
        if PIL_AVAILABLE:
            try:
                pil_img = image
                max_w, max_h = 360, 480
                pil_img.thumbnail((max_w, max_h), resample=1)
                ctk_image = ctk.CTkImage(
                    light_image=pil_img,
                    dark_image=pil_img,
                    size=pil_img.size,
                )
            except Exception as exc:
                self._show_error(f"Preview render failed: {exc}")
                return
        else:
            self._show_error("Pillow not installed — preview unavailable")
            return

        if hasattr(self, "preview_placeholder") and self.preview_placeholder.winfo_exists():
            self.preview_placeholder.destroy()

        if hasattr(self, "preview_image_label") and self.preview_image_label.winfo_exists():
            self.preview_image_label.destroy()

        self.preview_image_label = ctk.CTkLabel(
            self.preview_frame, image=ctk_image, text="",
        )
        self.preview_image_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.preview_image_label.image = ctk_image

    # ------------------------------------------------------------------
    # Embedded reader — swaps into the main view in place of search
    # results, instead of opening a new Toplevel window.
    # ------------------------------------------------------------------
    def _open_reader(self, filepath: str, filename: str) -> None:
        if not PYMUPDF_AVAILABLE:
            self._show_error("PyMuPDF is not installed. Cannot open reader.")
            return

        if not PIL_AVAILABLE:
            self._show_error("Pillow is not installed. Cannot open reader.")
            return

        if not os.path.exists(filepath):
            self._show_error("File no longer exists")
            self._refresh_downloads_list()
            return

        try:
            # Close any previously open reader first.
            if self.reader_view is not None:
                self.reader_view.close()
                self.reader_view.destroy()
                self.reader_view = None

            # Remember whether we came from search results or the library
            # grid, so "Back" returns to the right place — and hide both.
            self._reader_return_view = "library" if self.library_manager.library_frame.winfo_ismapped() else "results"
            self.search_manager.hide_results()
            self.library_manager.library_frame.grid_remove()

            progress_info = self.progress_store.get(filepath)
            start_page = progress_info["current_page"] if progress_info else 0

            self.reader_view = PactReaderView(
                self.main_content_frame, filepath, filename,
                on_back=self._close_reader_view,
                progress_store=self.progress_store,
                downloads_dir=self._get_downloads_dir(),
                on_open_related=self._open_reader,
                start_page=start_page,
                stats_store=self.stats_store,
            )
            self.reader_view.grid(row=0, column=0, sticky="nsew")

            self.status_label.configure(text=f"Reading: {filename}")
            self._refresh_continue_reading()
        except Exception as exc:
            self._show_error(f"Could not open reader: {exc}")
            self.reader_view = None
            self.search_manager.show_results()

    def _close_reader_view(self) -> None:
        """Tear down the embedded reader and bring back whichever view —
        search results or the library grid — was showing before."""
        if self.reader_view is not None:
            self.reader_view.close()
            self.reader_view.destroy()
            self.reader_view = None

        if self._reader_return_view == "library":
            self.library_manager.open_library_view()
        else:
            self.search_manager.show_results()
            self.status_label.configure(text="Ready")
        self._refresh_continue_reading()
        self.reading_stats_manager.refresh_reading_stats()

    def _close_library_view(self) -> None:
        """Close the library view and return to search results."""
        self.library_manager.close_library_view()

    def _get_downloads_dir(self) -> str:
        return self.selected_directory or self.default_download_dir

    def _refresh_downloads_list(self) -> None:
        """Scan the active download folder for PDFs and rebuild the sidebar list."""
        for widget in self.downloads_list_frame.winfo_children():
            widget.destroy()

        downloads_dir = self._get_downloads_dir()

        try:
            entries = [
                f for f in os.listdir(downloads_dir)
                if f.lower().endswith(".pdf")
                and os.path.isfile(os.path.join(downloads_dir, f))
            ]
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            entries = []

        # Most recently modified first
        entries.sort(
            key=lambda f: os.path.getmtime(os.path.join(downloads_dir, f)),
            reverse=True,
        )

        if not entries:
            self.downloads_empty_label = ctk.CTkLabel(
                self.downloads_list_frame,
                text="No downloads yet",
                font=PremiumTypography.body_small(),
                text_color="gray",
            )
            self.downloads_empty_label.pack(pady=15)
            self.library_manager.refresh_library_view_if_open()
            return

        for filename in entries:
            filepath = os.path.join(downloads_dir, filename)
            self._create_downloaded_file_item(filepath, filename).pack(
                fill="x", pady=3, padx=2
            )

        self.library_manager.refresh_library_view_if_open()

    def _create_downloaded_file_item(self, filepath: str, filename: str) -> ctk.CTkFrame:
        item = ctk.CTkFrame(
            self.downloads_list_frame, corner_radius=10,
            fg_color=("#F3F1EA", "gray25"),
        )
        item.grid_columnconfigure(0, weight=1)
        item.grid_columnconfigure(1, weight=0)
        item.grid_columnconfigure(2, weight=0)

        display_name = filename if len(filename) <= 24 else filename[:21] + "…"

        name_label = ctk.CTkLabel(
            item, text=display_name,
            font=PremiumTypography.body_small(size=12),
            anchor="w",
        )
        name_label.grid(row=0, column=0, sticky="w", padx=(10, 4), pady=8)

        open_btn = ctk.CTkButton(
            item, text="📖", width=26, height=26, corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"),
            command=lambda p=filepath, f=filename: self._open_reader(p, f),
        )
        open_btn.grid(row=0, column=1, padx=2, pady=6)

        external_btn = ctk.CTkButton(
            item, text="↗", width=26, height=26, corner_radius=8,
            font=ctk.CTkFont(size=14),
            fg_color="transparent", hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"),
            command=lambda p=filepath: self._open_file_external(p),
        )
        external_btn.grid(row=0, column=2, padx=(2, 8), pady=6)

        return item

    def _open_file_external(self, filepath: str) -> None:
        """Open a downloaded file in the operating system's default PDF viewer."""
        if not os.path.exists(filepath):
            self._show_error("File no longer exists")
            self._refresh_downloads_list()
            return

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(filepath)  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.Popen(["open", filepath])
            else:
                subprocess.Popen(["xdg-open", filepath])
        except Exception as exc:
            self._show_error(f"Could not open file: {exc}")

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        self.status_label.configure(text=f"Error: {message}")
        self.root.after(5000, lambda: self.error_label.configure(text=""))


if __name__ == "__main__":
    app = PactApp()
    app.run()
