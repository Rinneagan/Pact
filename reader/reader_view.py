"""
Integrated PDF Reader view for Pact PDF application.
Embeds directly into the main window with smooth rendering, zoom controls,
and a scrollable viewport.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from persistence import ReadingProgressStore, ReadingStatsStore, BookmarkStore

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
from utils import PremiumTypography, find_related_documents, NamidaTheme, NamidaIcons


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
        bookmark_store: Optional["BookmarkStore"] = None,
    ):
        super().__init__(master, fg_color="transparent")

        self.filepath = filepath
        self.doc_title = title
        self.on_back = on_back
        self.progress_store = progress_store
        self.downloads_dir = downloads_dir
        self.on_open_related = on_open_related
        self.stats_store = stats_store
        self.bookmark_store = bookmark_store

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
            fg_color=NamidaTheme.BG_CARD,
            border_width=1, border_color=NamidaTheme.BORDER
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
            left_frame, text=" Back", width=80, height=36, corner_radius=10,
            font=PremiumTypography.button_text(size=13),
            fg_color=NamidaTheme.BG_CARD, hover_color=NamidaTheme.ACCENT_HOVER,
            text_color=NamidaTheme.TEXT_PRIMARY, command=self._handle_back,
            image=NamidaIcons.get("arrow_left", size=18, light_color=NamidaTheme.TEXT_PRIMARY[0], dark_color=NamidaTheme.TEXT_PRIMARY[1]),
        )
        self.btn_back.pack(side="left", padx=(0, 10))
        self.btn_back.configure(cursor="hand2")

        self.btn_toggle_panel = ctk.CTkButton(
            left_frame, text="", width=36, height=36, corner_radius=10,
            fg_color=NamidaTheme.BG_CARD, hover_color=NamidaTheme.ACCENT_HOVER,
            text_color=NamidaTheme.TEXT_PRIMARY, command=self._toggle_side_panel,
            image=NamidaIcons.get("outline", size=18, light_color=NamidaTheme.TEXT_PRIMARY[0], dark_color=NamidaTheme.TEXT_PRIMARY[1]),
        )
        self.btn_toggle_panel.pack(side="left", padx=(0, 10))
        self.btn_toggle_panel.configure(cursor="hand2")

        self.btn_zoom_out = ctk.CTkButton(
            left_frame, text="", width=36, height=36, corner_radius=10,
            fg_color=NamidaTheme.BG_CARD, hover_color=NamidaTheme.ACCENT_HOVER,
            text_color=NamidaTheme.TEXT_PRIMARY, command=self._zoom_out,
            image=NamidaIcons.get("minus", size=18, light_color=NamidaTheme.TEXT_PRIMARY[0], dark_color=NamidaTheme.TEXT_PRIMARY[1]),
        )
        self.btn_zoom_out.pack(side="left", padx=5)
        self.btn_zoom_out.configure(cursor="hand2")

        self.btn_zoom_in = ctk.CTkButton(
            left_frame, text="", width=36, height=36, corner_radius=10,
            fg_color=NamidaTheme.BG_CARD, hover_color=NamidaTheme.ACCENT_HOVER,
            text_color=NamidaTheme.TEXT_PRIMARY, command=self._zoom_in,
            image=NamidaIcons.get("plus", size=18, light_color=NamidaTheme.TEXT_PRIMARY[0], dark_color=NamidaTheme.TEXT_PRIMARY[1]),
        )
        self.btn_zoom_in.pack(side="left", padx=5)
        self.btn_zoom_in.configure(cursor="hand2")

        # --- Center: Navigation Controls ---
        nav_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        nav_frame.grid(row=0, column=1, sticky="n", pady=10)

        self.btn_prev = ctk.CTkButton(
            nav_frame, text="", width=36, height=36, corner_radius=10,
            fg_color=NamidaTheme.ACCENT_PRIMARY, hover_color=NamidaTheme.ACCENT_SECONDARY,
            text_color="#FFFFFF",
            command=self._prev_page,
            image=NamidaIcons.get("chevron_left", size=18, light_color="#FFFFFF", dark_color="#FFFFFF"),
        )
        self.btn_prev.pack(side="left", padx=10)
        self.btn_prev.configure(cursor="hand2")

        self.page_label = ctk.CTkLabel(
            nav_frame, text=f"1 / {self.total_pages}",
            font=PremiumTypography.heading_medium(),
            text_color=NamidaTheme.TEXT_PRIMARY,
        )
        self.page_label.pack(side="left", padx=10)

        self.btn_next = ctk.CTkButton(
            nav_frame, text="", width=36, height=36, corner_radius=10,
            fg_color=NamidaTheme.ACCENT_PRIMARY, hover_color=NamidaTheme.ACCENT_SECONDARY,
            text_color="#FFFFFF",
            command=self._next_page,
            image=NamidaIcons.get("chevron_right", size=18, light_color="#FFFFFF", dark_color="#FFFFFF"),
        )
        self.btn_next.pack(side="left", padx=10)
        self.btn_next.configure(cursor="hand2")

        self.btn_bookmark = ctk.CTkButton(
            nav_frame, text="", width=36, height=36, corner_radius=10,
            fg_color=NamidaTheme.BG_CARD, hover_color=NamidaTheme.ACCENT_HOVER,
            text_color=NamidaTheme.TEXT_PRIMARY,
            command=self._toggle_current_page_bookmark,
        )
        self.btn_bookmark.pack(side="left", padx=(10, 0))
        self.btn_bookmark.configure(cursor="hand2")

        # --- Right: Title + Status ---
        right_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="e", padx=15, pady=10)

        display_title = self.doc_title if len(self.doc_title) <= 28 else self.doc_title[:25] + "…"
        self.title_label = ctk.CTkLabel(
            right_frame, text=display_title,
            font=PremiumTypography.body_small(size=12),
            text_color=NamidaTheme.TEXT_MUTED,
        )
        self.title_label.pack(side="left", padx=(0, 12))

        self.status_label = ctk.CTkLabel(
            right_frame, text=f"{int(self.zoom_level * 50)}%",
            font=PremiumTypography.monospace(size=14),
            text_color=NamidaTheme.TEXT_MUTED
        )
        self.status_label.pack(side="left")

        # Collapsible side panel: document outline + related documents
        self.side_panel = ctk.CTkFrame(
            self, width=260, corner_radius=15,
            fg_color=NamidaTheme.BG_SIDEBAR,
            border_width=1, border_color=NamidaTheme.BORDER
        )
        self.side_panel.grid(row=1, column=0, sticky="ns", padx=(20, 10), pady=(0, 20))
        self.side_panel.grid_propagate(False)
        self._build_side_panel()

        # Scrollable Viewport
        self.viewport = ctk.CTkScrollableFrame(
            self, corner_radius=15,
            fg_color=NamidaTheme.BG_MAIN,
            border_width=1, border_color=NamidaTheme.BORDER
        )
        self.viewport.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))

        self.canvas_label = ctk.CTkLabel(self.viewport, text="")
        self.canvas_label.pack(expand=True, pady=20)

    def _build_side_panel(self) -> None:
        """Create tab header switcher and layout container inside the side panel."""
        self.tab_switch = ctk.CTkSegmentedButton(
            self.side_panel,
            values=["Outline", "Related", "Notes"],
            command=lambda v: self._switch_tab(v.lower()),
            selected_color=NamidaTheme.ACCENT_PRIMARY,
            text_color=NamidaTheme.TEXT_PRIMARY,
            fg_color=NamidaTheme.BG_CARD,
            corner_radius=8,
            font=PremiumTypography.button_text(size=11),
        )
        self.tab_switch.pack(fill="x", padx=10, pady=(15, 10))
        
        divider = ctk.CTkFrame(self.side_panel, height=1, fg_color=NamidaTheme.BORDER)
        divider.pack(fill="x", padx=10, pady=(0, 10))
        
        self.sidebar_content_frame = ctk.CTkScrollableFrame(
            self.side_panel,
            fg_color="transparent",
            corner_radius=0
        )
        self.sidebar_content_frame.pack(fill="both", expand=True, padx=4, pady=(0, 10))
        
        self.active_tab = "outline"
        self.tab_switch.set("Outline")
        self._switch_tab("outline")

    def _switch_tab(self, tab_name: str) -> None:
        self.active_tab = tab_name
        
        display_name = tab_name.capitalize()
        if self.tab_switch.get() != display_name:
            self.tab_switch.set(display_name)
                
        for child in self.sidebar_content_frame.winfo_children():
            child.destroy()
            
        if tab_name == "outline":
            self._populate_outline()
        elif tab_name == "related":
            self._populate_related()
        elif tab_name == "notes":
            self._populate_notes()

    def _populate_outline(self) -> None:
        try:
            toc = self.doc.get_toc()
        except Exception:
            toc = []

        if not toc:
            label = ctk.CTkLabel(
                self.sidebar_content_frame, text="No outline available",
                font=PremiumTypography.body_small(size=11), text_color=NamidaTheme.TEXT_MUTED,
            )
            label.pack(anchor="w", padx=14, pady=10)
        else:
            for level, entry_title, page in toc[:80]:
                indent = max(level - 1, 0) * 12
                display = entry_title if len(entry_title) <= 26 else entry_title[:23] + "…"
                btn = ctk.CTkButton(
                    self.sidebar_content_frame, text=display, anchor="w",
                    font=PremiumTypography.body_small(size=12 if level == 1 else 11),
                    fg_color="transparent", hover_color=NamidaTheme.ACCENT_HOVER,
                    text_color=NamidaTheme.TEXT_PRIMARY if level == 1 else NamidaTheme.TEXT_MUTED,
                    command=lambda p=page: self._goto_page(p - 1),
                    height=28,
                    corner_radius=6,
                )
                btn.pack(fill="x", padx=(indent, 2), pady=1)
                btn.configure(cursor="hand2")

    def _populate_related(self) -> None:
        related = find_related_documents(self.filepath, self.downloads_dir, limit=5) if self.downloads_dir else []

        if not related:
            label = ctk.CTkLabel(
                self.sidebar_content_frame, text="No related documents found",
                font=PremiumTypography.body_small(size=11), text_color=NamidaTheme.TEXT_MUTED,
            )
            label.pack(anchor="w", padx=14, pady=10)
        else:
            for fpath, fname, _shared in related:
                display = fname if len(fname) <= 26 else fname[:23] + "…"
                btn = ctk.CTkButton(
                    self.sidebar_content_frame, text=f" {display}", anchor="w",
                    font=PremiumTypography.body_small(size=12),
                    fg_color="transparent", hover_color=NamidaTheme.ACCENT_HOVER,
                    text_color=NamidaTheme.ACCENT_PRIMARY,
                    image=NamidaIcons.get("external_link", size=14, light_color=NamidaTheme.ACCENT_PRIMARY[0], dark_color=NamidaTheme.ACCENT_PRIMARY[1]),
                    command=lambda p=fpath, f=fname: self._open_related(p, f),
                    height=32,
                    corner_radius=8,
                )
                btn.pack(fill="x", padx=4, pady=2)
                btn.configure(cursor="hand2")

    def _populate_notes(self) -> None:
        # Input form frame
        input_frame = ctk.CTkFrame(self.sidebar_content_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=4, pady=(5, 10))

        self.note_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text=f"Optional page note...",
            height=32,
            corner_radius=8,
            font=PremiumTypography.body_small(size=12),
            fg_color=NamidaTheme.BG_CARD,
            text_color=NamidaTheme.TEXT_PRIMARY,
            placeholder_text_color=NamidaTheme.TEXT_MUTED,
            border_color=NamidaTheme.BORDER
        )
        self.note_entry.pack(fill="x", pady=(0, 6))
        self.note_entry.bind("<Return>", lambda e: self._add_current_note())

        self.btn_add_note = ctk.CTkButton(
            input_frame,
            text="Save Note",
            font=PremiumTypography.button_text(size=12),
            fg_color=NamidaTheme.ACCENT_PRIMARY,
            hover_color=NamidaTheme.ACCENT_SECONDARY,
            text_color="#FFFFFF",
            height=28,
            corner_radius=8,
            command=self._add_current_note
        )
        self.btn_add_note.pack(fill="x")
        self.btn_add_note.configure(cursor="hand2")

        # Scrollable list of existing bookmarks/notes
        bookmarks = self.bookmark_store.get(self.filepath) if self.bookmark_store else []
        if not bookmarks:
            no_notes_label = ctk.CTkLabel(
                self.sidebar_content_frame,
                text="No bookmarks or notes.\nUse toolbar 🔖 or add note above.",
                font=PremiumTypography.body_small(size=11),
                text_color=NamidaTheme.TEXT_MUTED,
                justify="center"
            )
            no_notes_label.pack(pady=20)
        else:
            for b in bookmarks:
                page_idx = b.get("page", 0)
                note_text = b.get("note", "")
                
                card = ctk.CTkFrame(
                    self.sidebar_content_frame,
                    corner_radius=8,
                    fg_color=NamidaTheme.BG_CARD,
                    border_width=1,
                    border_color=NamidaTheme.BORDER
                )
                card.pack(fill="x", padx=4, pady=4)
                card.grid_columnconfigure(0, weight=1)
                card.grid_columnconfigure(1, weight=0)
                
                title_lbl = ctk.CTkLabel(
                    card,
                    text=f"Page {page_idx + 1}",
                    font=PremiumTypography.heading_small(size=12),
                    text_color=NamidaTheme.ACCENT_PRIMARY,
                    anchor="w"
                )
                title_lbl.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))
                
                del_btn = ctk.CTkButton(
                    card,
                    text="",
                    width=20,
                    height=20,
                    corner_radius=6,
                    fg_color="transparent",
                    hover_color=NamidaTheme.ACCENT_HOVER,
                    image=NamidaIcons.get("close", size=10, light_color=NamidaTheme.TEXT_MUTED[0], dark_color=NamidaTheme.TEXT_MUTED[1]),
                    command=lambda p=page_idx: self._delete_bookmark(p)
                )
                del_btn.grid(row=0, column=1, sticky="ne", padx=6, pady=4)
                del_btn.configure(cursor="hand2")
                
                if note_text:
                    content_lbl = ctk.CTkLabel(
                        card,
                        text=note_text,
                        font=PremiumTypography.body_small(size=11),
                        text_color=NamidaTheme.TEXT_PRIMARY,
                        wraplength=200,
                        justify="left",
                        anchor="w"
                    )
                    content_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))
                else:
                    card.grid_rowconfigure(1, minsize=4)
                    
                def on_enter(e, widget=card):
                    try:
                        widget.configure(border_color=NamidaTheme.ACCENT_SECONDARY)
                    except Exception:
                        pass
                def on_leave(e, widget=card):
                    try:
                        widget.configure(border_color=NamidaTheme.BORDER)
                    except Exception:
                        pass
                card.bind("<Enter>", on_enter)
                card.bind("<Leave>", on_leave)

                jump_cb = lambda e, p=page_idx: self._goto_page(p)
                for widget in (card, title_lbl):
                    widget.bind("<Button-1>", jump_cb)
                    widget.configure(cursor="hand2")
                if note_text:
                    content_lbl.bind("<Button-1>", jump_cb)
                    content_lbl.configure(cursor="hand2")
                    content_lbl.bind("<Enter>", on_enter)
                    content_lbl.bind("<Leave>", on_leave)
                title_lbl.bind("<Enter>", on_enter)
                title_lbl.bind("<Leave>", on_leave)

    def _add_current_note(self) -> None:
        if not self.bookmark_store:
            return
        note = self.note_entry.get().strip()
        self.bookmark_store.add(self.filepath, self.current_page, note)
        self.note_entry.delete(0, "end")
        self._switch_tab("notes")
        self._update_toolbar_bookmark_button()

    def _delete_bookmark(self, page_index: int) -> None:
        if not self.bookmark_store:
            return
        self.bookmark_store.remove(self.filepath, page_index)
        if self.active_tab == "notes":
            self._switch_tab("notes")
        self._update_toolbar_bookmark_button()

    def _toggle_current_page_bookmark(self) -> None:
        if not self.bookmark_store:
            return
        bookmarks = self.bookmark_store.get(self.filepath)
        is_bookmarked = any(b.get("page") == self.current_page for b in bookmarks)
        if is_bookmarked:
            self.bookmark_store.remove(self.filepath, self.current_page)
        else:
            self.bookmark_store.add(self.filepath, self.current_page, "")
            self._switch_tab("notes")
            
        self._update_toolbar_bookmark_button()
        if self.active_tab == "notes":
            self._switch_tab("notes")

    def _update_toolbar_bookmark_button(self) -> None:
        if not hasattr(self, "btn_bookmark") or not self.btn_bookmark.winfo_exists():
            return
        is_bookmarked = False
        if self.bookmark_store:
            bookmarks = self.bookmark_store.get(self.filepath)
            is_bookmarked = any(b.get("page") == self.current_page for b in bookmarks)
        if is_bookmarked:
            self.btn_bookmark.configure(
                fg_color=NamidaTheme.ACCENT_SECONDARY,
                hover_color=NamidaTheme.ACCENT_PRIMARY,
                image=NamidaIcons.get("bookmark", size=18, light_color="#FFFFFF", dark_color="#FFFFFF"),
            )
        else:
            self.btn_bookmark.configure(
                fg_color=NamidaTheme.BG_CARD,
                hover_color=NamidaTheme.ACCENT_HOVER,
                image=NamidaIcons.get("bookmark", size=18, light_color=NamidaTheme.TEXT_MUTED[0], dark_color=NamidaTheme.TEXT_MUTED[1]),
            )

    def _update_notes_entry_placeholder(self) -> None:
        if hasattr(self, "note_entry") and self.note_entry.winfo_exists():
            self.note_entry.configure(placeholder_text=f"Optional page note...")

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

        # Generate inverted image for dark mode to prevent eye strain
        dark_img = img
        try:
            from PIL import ImageOps
            dark_img = ImageOps.invert(img)
        except Exception:
            pass

        ctk_img = ctk.CTkImage(
            light_image=img, dark_image=dark_img,
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

        self._update_toolbar_bookmark_button()
        self._update_notes_entry_placeholder()

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

    def sync_native_backgrounds(self, is_dark: bool) -> None:
        """Synchronizes native Tkinter backgrounds to prevent resizing flickering."""
        sidebar_bg = NamidaTheme.BG_SIDEBAR[1] if is_dark else NamidaTheme.BG_SIDEBAR[0]
        main_bg = NamidaTheme.BG_MAIN[1] if is_dark else NamidaTheme.BG_MAIN[0]
        
        import tkinter as tk
        try:
            tk.Frame.configure(self.side_panel, bg=sidebar_bg)
        except Exception:
            pass
        try:
            tk.Frame.configure(self.viewport, bg=main_bg)
        except Exception:
            pass

    def close(self) -> None:
        """Release the open document. Call before discarding this view."""
        try:
            if self.progress_store is not None:
                self.progress_store.update(self.filepath, self.current_page, self.total_pages, self.doc_title)
            self.doc.close()
        except Exception:
            pass
