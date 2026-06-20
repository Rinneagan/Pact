"""
Integrated PDF Reader view for Pact PDF application.
Embeds directly into the main window with smooth rendering, zoom controls,
and a scrollable viewport.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

# Optional dependencies
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

# Import utilities
from utils.typography import PremiumTypography
from utils.related_docs import find_related_documents


class PactReaderView(ctk.CTkFrame):
    """
    A premium, integrated PDF reader view for Pact.
    Embeds directly into the main window (swapped in place of the search
    results) instead of opening a separate popup window. Features smooth
    rendering, zoom controls, a scrollable viewport, and a "Back" control
    to return to search results.
    """

    def __init__(
        self,
        master,
        filepath: str,
        title: str,
        on_back: Callable[[], None],
        progress_store: Optional["ReadingProgressStore"] = None,
        downloads_dir: str = "",
        on_open_related: Optional[Callable[[str, str], None]] = None,
        start_page: int = 0,
        stats_store: Optional["ReadingStatsStore"] = None,
    ):
        super().__init__(master, fg_color="transparent")

        self.filepath = filepath
        self.doc_title = title
        self.on_back = on_back
        self.progress_store = progress_store
        self.downloads_dir = downloads_dir
        self.on_open_related = on_open_related
        self.stats_store = stats_store

        self.doc = fitz.open(filepath)
        self.total_pages = len(self.doc)
        self.current_page = start_page if 0 <= start_page < self.total_pages else 0
        self.zoom_level = 2.0  # Default 2x scale for crisp text
        self.side_panel_visible = True

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        self._build_ui()
        self.render_page()

    def _build_ui(self) -> None:
        """Construct the sleek, airy UI."""
        # Floating Toolbar
        self.toolbar = ctk.CTkFrame(
            self, height=60, corner_radius=15,
            fg_color=("#FFFFFF", "gray17"),
            border_width=1, border_color=("#ECE9E2", "gray25")
        )
        self.toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 10))
        self.toolbar.grid_propagate(False)

        self.toolbar.grid_columnconfigure(0, weight=1)
        self.toolbar.grid_columnconfigure(1, weight=1)
        self.toolbar.grid_columnconfigure(2, weight=1)

        # --- Left: Back + Panel toggle + Zoom Controls ---
        left_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="w", padx=15, pady=10)

        self.btn_back = ctk.CTkButton(
            left_frame, text="← Back", width=64, height=36, corner_radius=10,
            font=PremiumTypography.button_text(size=13),
            fg_color=("#F3F1EA", "gray22"), hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"), command=self._handle_back,
        )
        self.btn_back.pack(side="left", padx=(0, 10))

        self.btn_toggle_panel = ctk.CTkButton(
            left_frame, text="📑", width=36, height=36, corner_radius=10,
            font=ctk.CTkFont(size=15),
            fg_color=("#F3F1EA", "gray22"), hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"), command=self._toggle_side_panel,
        )
        self.btn_toggle_panel.pack(side="left", padx=(0, 10))

        self.btn_zoom_out = ctk.CTkButton(
            left_frame, text="−", width=36, height=36, corner_radius=10,
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=("#F3F1EA", "gray22"), hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"), command=self._zoom_out
        )
        self.btn_zoom_out.pack(side="left", padx=5)

        self.btn_zoom_in = ctk.CTkButton(
            left_frame, text="+", width=36, height=36, corner_radius=10,
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=("#F3F1EA", "gray22"), hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"), command=self._zoom_in
        )
        self.btn_zoom_in.pack(side="left", padx=5)

        # --- Center: Navigation Controls ---
        nav_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        nav_frame.grid(row=0, column=1, sticky="n", pady=10)

        self.btn_prev = ctk.CTkButton(
            nav_frame, text="◀", width=36, height=36, corner_radius=10,
            font=ctk.CTkFont(size=16),
            fg_color="#639922", hover_color="#4F7A1B",
            command=self._prev_page
        )
        self.btn_prev.pack(side="left", padx=10)

        self.page_label = ctk.CTkLabel(
            nav_frame, text=f"1 / {self.total_pages}",
            font=PremiumTypography.heading_medium()
        )
        self.page_label.pack(side="left", padx=10)

        self.btn_next = ctk.CTkButton(
            nav_frame, text="▶", width=36, height=36, corner_radius=10,
            font=ctk.CTkFont(size=16),
            fg_color="#639922", hover_color="#4F7A1B",
            command=self._next_page
        )
        self.btn_next.pack(side="left", padx=10)

        # --- Right: Title + Status ---
        right_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="e", padx=15, pady=10)

        display_title = self.doc_title if len(self.doc_title) <= 28 else self.doc_title[:25] + "…"
        self.title_label = ctk.CTkLabel(
            right_frame, text=display_title,
            font=PremiumTypography.body_small(size=12),
            text_color="gray",
        )
        self.title_label.pack(side="left", padx=(0, 12))

        self.status_label = ctk.CTkLabel(
            right_frame, text=f"{int(self.zoom_level * 50)}%",
            font=PremiumTypography.monospace(size=14),
            text_color="gray"
        )
        self.status_label.pack(side="left")

        # Collapsible side panel: document outline + related documents
        self.side_panel = ctk.CTkScrollableFrame(
            self, width=260, corner_radius=15,
            fg_color=("#F3F1EA", "gray17"),
        )
        self.side_panel.grid(row=1, column=0, sticky="ns", padx=(20, 10), pady=(0, 20))
        self._build_side_panel()

        # Scrollable Viewport
        self.viewport = ctk.CTkScrollableFrame(
            self, corner_radius=15,
            fg_color=("#F3F1EA", "gray17")
        )
        self.viewport.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))

        self.canvas_label = ctk.CTkLabel(self.viewport, text="")
        self.canvas_label.pack(expand=True, pady=20)

    def _build_side_panel(self) -> None:
        """Populate the side panel with a clickable Outline (from the PDF's
        own table of contents, if any) and a Related Documents list found
        via cheap filename-token overlap against the downloads folder."""
        ctk.CTkLabel(
            self.side_panel, text="📑 Outline",
            font=PremiumTypography.heading_small(size=13), anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 6))

        try:
            toc = self.doc.get_toc()
        except Exception:
            toc = []

        if not toc:
            ctk.CTkLabel(
                self.side_panel, text="No outline available",
                font=PremiumTypography.body_small(size=11), text_color="gray",
            ).pack(anchor="w", padx=14, pady=(0, 10))
        else:
            for level, entry_title, page in toc[:80]:
                indent = 10 + max(level - 1, 0) * 14
                display = entry_title if len(entry_title) <= 30 else entry_title[:27] + "…"
                ctk.CTkButton(
                    self.side_panel, text=display, anchor="w",
                    font=PremiumTypography.body_small(size=12 if level == 1 else 11),
                    fg_color="transparent", hover_color=("#E1EFC9", "gray30"),
                    text_color=("#2C2C2A", "gray90") if level == 1 else "gray",
                    command=lambda p=page: self._goto_page(p - 1),
                ).pack(fill="x", padx=(indent, 6), pady=1)

        ctk.CTkFrame(
            self.side_panel, height=1, fg_color=("#ECE9E2", "gray30"),
        ).pack(fill="x", padx=10, pady=(14, 10))

        ctk.CTkLabel(
            self.side_panel, text="🔗 Related Documents",
            font=PremiumTypography.heading_small(size=13), anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 6))

        related = find_related_documents(self.filepath, self.downloads_dir, limit=5) if self.downloads_dir else []

        if not related:
            ctk.CTkLabel(
                self.side_panel, text="No related documents found",
                font=PremiumTypography.body_small(size=11), text_color="gray",
            ).pack(anchor="w", padx=14, pady=(0, 14))
        else:
            for fpath, fname, _shared in related:
                display = fname if len(fname) <= 28 else fname[:25] + "…"
                ctk.CTkButton(
                    self.side_panel, text=f"📄 {display}", anchor="w",
                    font=PremiumTypography.body_small(size=12),
                    fg_color="transparent", hover_color=("#E1EFC9", "gray30"),
                    text_color=("#639922", "#97C459"),
                    command=lambda p=fpath, f=fname: self._open_related(p, f),
                ).pack(fill="x", padx=10, pady=1)

    def _toggle_side_panel(self) -> None:
        self.side_panel_visible = not self.side_panel_visible
        if self.side_panel_visible:
            self.side_panel.grid()
        else:
            self.side_panel.grid_remove()

    def _goto_page(self, page_index: int) -> None:
        self.current_page = max(0, min(page_index, self.total_pages - 1))
        self.render_page()

    def _open_related(self, filepath: str, filename: str) -> None:
        if self.on_open_related:
            self.on_open_related(filepath, filename)

    def _handle_back(self) -> None:
        self.on_back()

    def render_page(self) -> None:
        """Render the current page to the screen based on zoom level."""
        page = self.doc.load_page(self.current_page)

        mat = fitz.Matrix(self.zoom_level, self.zoom_level)
        pix = page.get_pixmap(matrix=mat)

        img = _Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        ctk_img = ctk.CTkImage(
            light_image=img, dark_image=img,
            size=(pix.width, pix.height)
        )

        self.canvas_label.configure(image=ctk_img)
        self.canvas_label.image = ctk_img  # Prevent GC

        self.page_label.configure(text=f"{self.current_page + 1} / {self.total_pages}")
        self.status_label.configure(text=f"{int(self.zoom_level * 50)}%")

        self.btn_prev.configure(state="normal" if self.current_page > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.current_page < self.total_pages - 1 else "disabled")

        if self.progress_store is not None:
            self.progress_store.update(self.filepath, self.current_page, self.total_pages, self.doc_title)

        if self.stats_store is not None:
            self.stats_store.log_page_view(self.filepath, self.current_page, self.total_pages, self.doc_title)

    def _next_page(self) -> None:
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.render_page()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.render_page()

    def _zoom_in(self) -> None:
        if self.zoom_level < 4.0:
            self.zoom_level += 0.5
            self.render_page()

    def _zoom_out(self) -> None:
        if self.zoom_level > 1.0:
            self.zoom_level -= 0.5
            self.render_page()

    def close(self) -> None:
        """Release the open document. Call before discarding this view."""
        try:
            if self.progress_store is not None:
                self.progress_store.update(self.filepath, self.current_page, self.total_pages, self.doc_title)
            self.doc.close()
        except Exception:
            pass
