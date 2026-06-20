"""
Search functionality for Pact PDF application.
Handles PDF search, results display, and search suggestions.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable
from urllib.parse import urlparse, unquote

import customtkinter as ctk

from utils.typography import PremiumTypography


class SearchManager:
    """Manages PDF search functionality including UI and results display."""

    def __init__(self, app):
        self.app = app
        self.search_frame = None
        self.search_entry = None
        self.search_button = None
        self.suggestions_frame = None
        self.results_frame = None
        self.main_content_frame = None
        self.library_frame = None
        self.error_label = None

    def setup_ui(self, main_view_frame, main_content_frame, library_frame, error_label):
        """Set up the search UI components."""
        self.main_content_frame = main_content_frame
        self.library_frame = library_frame
        self.error_label = error_label

        self.search_frame = ctk.CTkFrame(
            main_view_frame, height=80, fg_color="transparent",
        )
        self.search_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        self.search_frame.grid_columnconfigure(0, weight=1)
        self.search_frame.grid_columnconfigure(1, weight=0)

        self.search_entry = ctk.CTkEntry(
            self.search_frame,
            placeholder_text="Search for PDFs...",
            height=50,
            corner_radius=14,
            font=PremiumTypography.body_text(size=15),
            fg_color=("#FFFFFF", "gray20"),
            border_color=("#ECE9E2", "gray30"),
            border_width=1,
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 10), pady=15, sticky="ew")
        self.search_entry.bind("<Return>", lambda e: self.perform_search())
        self.search_entry.bind("<FocusIn>", self.show_search_suggestions)
        self.search_entry.bind("<KeyRelease>", self.on_search_entry_key)
        self.search_entry.bind("<FocusOut>", lambda e: self.app.root.after(150, self.hide_search_suggestions))

        self.search_button = ctk.CTkButton(
            self.search_frame,
            text="Search",
            font=PremiumTypography.button_text(),
            width=140, height=50, corner_radius=14,
            fg_color="#639922", hover_color="#4F7A1B",
            command=self.perform_search,
        )
        self.search_button.grid(row=0, column=1, pady=15, sticky="e")

        self.suggestions_frame = ctk.CTkFrame(self.search_frame, fg_color="transparent")
        self.suggestions_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=2, pady=(0, 6))
        self.suggestions_frame.grid_remove()

        self.results_frame = ctk.CTkScrollableFrame(
            self.main_content_frame,
            label_text="Search Results",
            label_font=PremiumTypography.heading_medium(),
            corner_radius=14,
            fg_color="transparent",
            label_text_color=("#2C2C2A", "gray90"),
        )
        self.results_frame.grid(row=0, column=0, sticky="nsew")

    def perform_search(self) -> None:
        """Perform a PDF search."""
        if self.app.is_searching:
            return

        search_term = self.search_entry.get().strip()
        if not search_term:
            self.app._show_error("Please enter a search term")
            return

        if not self.app.search_pdfs:
            self.app._show_error("Backend not available")
            return

        # If a PDF reader or the library grid is currently shown, return to
        # search before showing new results.
        if self.app.reader_view is not None:
            self.app._close_reader_view()
        if self.library_frame.winfo_ismapped():
            self.app._close_library_view()

        self.suggestions_frame.grid_remove()
        self.app.recent_searches.add(search_term)

        self.app.is_searching = True
        self.set_searching_state(True)
        self.app.executor.submit(self.search_worker, search_term)

    def search_worker(self, search_term: str) -> None:
        """Worker thread for performing search."""
        try:
            results = self.app.search_pdfs(search_term, max_results=self.app.max_search_results)
            self.app._ui(lambda: self.update_search_results(results, search_term))
        except Exception as exc:
            msg = str(exc)
            self.app._ui(lambda: self.app._show_error(f"Search failed: {msg}"))
        finally:
            self.app._ui(lambda: self.set_searching_state(False))

    def show_search_suggestions(self, event: Any = None) -> None:
        """Show search suggestions when entry is focused and empty."""
        if self.search_entry.get().strip():
            return
        self.populate_suggestions_frame()
        if self.suggestions_frame.winfo_children():
            self.suggestions_frame.grid()

    def on_search_entry_key(self, event: Any = None) -> None:
        """Handle key release events in search entry."""
        if self.search_entry.get().strip():
            self.suggestions_frame.grid_remove()
        else:
            self.show_search_suggestions()

    def hide_search_suggestions(self) -> None:
        """Hide search suggestions."""
        self.suggestions_frame.grid_remove()

    def populate_suggestions_frame(self) -> None:
        """Populate the suggestions frame with recent searches."""
        for widget in self.suggestions_frame.winfo_children():
            widget.destroy()

        terms = self.app.recent_searches.recent(limit=8)
        if not terms:
            return

        ctk.CTkLabel(
            self.suggestions_frame, text="Recent:",
            font=PremiumTypography.body_small(size=11), text_color="gray",
        ).pack(side="left", padx=(8, 6))

        for term in terms:
            chip = ctk.CTkButton(
                self.suggestions_frame, text=term, height=26, corner_radius=13,
                font=PremiumTypography.body_small(size=11),
                fg_color=("#F3F1EA", "gray22"), hover_color=("#E1EFC9", "gray30"),
                text_color=("#639922", "#97C459"),
                command=lambda t=term: self.use_suggested_search(t),
            )
            chip.pack(side="left", padx=3)

    def use_suggested_search(self, term: str) -> None:
        """Use a suggested search term."""
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, term)
        self.suggestions_frame.grid_remove()
        self.perform_search()

    def set_searching_state(self, searching: bool) -> None:
        """Set the searching state of the UI."""
        self.app.is_searching = searching
        if searching:
            self.search_button.configure(state="disabled", text="Searching…")
            self.search_entry.configure(state="disabled")
            self.show_skeleton_loader()
        else:
            self.search_button.configure(state="normal", text="Search")
            self.search_entry.configure(state="normal")
            self.hide_skeleton_loader()

    def show_skeleton_loader(self) -> None:
        """Show skeleton loader while searching."""
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        self.app.skeleton_container = ctk.CTkFrame(
            self.results_frame, fg_color="transparent",
        )
        self.app.skeleton_container.pack(fill="x", pady=10)

        for _ in range(5):
            self.create_skeleton_card().pack(fill="x", pady=5, padx=10)

        self.app._skeleton_running = True
        self.app._skeleton_phase = 0.0
        self.animate_skeleton_gradient()

    def create_skeleton_card(self) -> ctk.CTkFrame:
        """Create a skeleton loading card."""
        card = ctk.CTkFrame(
            self.app.skeleton_container, corner_radius=14,
            fg_color=("#ECE9E2", "gray25"),
        )
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(
            card, height=20, fg_color=("#DDD9CC", "gray20"), corner_radius=4,
        ).grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 5))

        ctk.CTkFrame(
            card, height=16, fg_color=("#E3DFD2", "gray22"), corner_radius=4,
        ).grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 12))

        return card

    def animate_skeleton_gradient(self) -> None:
        """Animate the skeleton loader gradient."""
        if not self.app._skeleton_running:
            return

        self.app._skeleton_phase = (self.app._skeleton_phase + 0.1) % 6.2832

        if hasattr(self.app, "skeleton_container") and self.app.skeleton_container.winfo_exists():
            bright = self.app._skeleton_phase < 3.14159
            for card in self.app.skeleton_container.winfo_children():
                if isinstance(card, ctk.CTkFrame):
                    for child in card.winfo_children():
                        if isinstance(child, ctk.CTkFrame):
                            child.configure(
                                fg_color=("gray75" if bright else "gray80", "gray20")
                            )

        self.app.root.after(16, self.animate_skeleton_gradient)

    def hide_skeleton_loader(self) -> None:
        """Hide the skeleton loader."""
        self.app._skeleton_running = False
        if hasattr(self.app, "skeleton_container") and self.app.skeleton_container.winfo_exists():
            self.app.skeleton_container.pack_forget()

    def update_search_results(self, results: list[str], search_term: str) -> None:
        """Update the search results display."""
        self.hide_skeleton_loader()

        for widget in self.results_frame.winfo_children():
            widget.destroy()

        self.app.search_results = results

        if not results:
            ctk.CTkLabel(
                self.results_frame,
                text=f"No PDFs found for '{search_term}'",
                font=PremiumTypography.body_text(),
                text_color="gray",
            ).pack(pady=20)
            self.app.status_label.configure(text=f"No results for '{search_term}'")
            return

        for idx, url in enumerate(results):
            self.create_result_item(idx, url).pack(fill="x", pady=5, padx=10)

        self.app.status_label.configure(text=f"Found {len(results)} PDFs for '{search_term}'")

    def create_result_item(self, idx: int, url: str) -> ctk.CTkFrame:
        """Create a search result item."""
        # Safely extract and clean the filename from the URL
        parsed_url = urlparse(url)
        raw_name = unquote(os.path.basename(parsed_url.path))
        if not raw_name:
            raw_name = f"document_{idx+1}.pdf"

        # Strip illegal characters for Windows/Mac
        filename = re.sub(r'[\\/:*?"<>|]', "_", raw_name)
        if not filename.lower().endswith('.pdf'):
            filename += ".pdf"

        frame = ctk.CTkFrame(
            self.results_frame, corner_radius=14,
            fg_color=("#FFFFFF", "gray20"),
            border_width=1, border_color=("#ECE9E2", "gray30"),
        )
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)

        file_icon = ctk.CTkLabel(
            frame, text="\U0001F4C4", font=ctk.CTkFont(size=18),
            text_color=("#97C459", "#79B82B"), width=24,
        )
        file_icon.grid(row=0, column=0, rowspan=2, sticky="w", padx=(15, 8), pady=12)

        title_label = ctk.CTkLabel(
            frame,
            text=f"{idx + 1}. {filename}",
            font=PremiumTypography.heading_small(size=15),
            anchor="w",
        )
        title_label.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(12, 5))

        url_label = ctk.CTkLabel(
            frame,
            text=url[:70] + "…" if len(url) > 70 else url,
            font=PremiumTypography.monospace(size=10),
            text_color="gray",
            anchor="w",
        )
        url_label.grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(0, 12))

        download_btn = ctk.CTkButton(
            frame,
            text="↓",
            font=ctk.CTkFont(size=18, weight="bold"),
            width=34, height=34, corner_radius=10,
            fg_color="transparent",
            hover_color=("#E1EFC9", "gray30"),
            text_color=("#639922", "#97C459"),
            command=lambda u=url, f=filename: self.quick_download(u, f),
        )
        download_btn.grid(row=0, column=2, rowspan=2, sticky="e", padx=(0, 12), pady=12)

        select_cb = lambda e, u=url, f=filename: self.select_pdf(u, f)
        frame.bind("<Button-1>", select_cb)
        file_icon.bind("<Button-1>", select_cb)
        title_label.bind("<Button-1>", select_cb)
        url_label.bind("<Button-1>", select_cb)

        def on_enter(e: Any, fr=frame, tl=title_label, ul=url_label) -> None:
            fr.configure(
                border_color=("#639922", "#97C459"),
                fg_color=("#F3F1EA", "gray25"),
            )
            tl.grid_configure(pady=(10, 5))
            ul.grid_configure(pady=(0, 10))

        def on_leave(e: Any, fr=frame, tl=title_label, ul=url_label) -> None:
            fr.configure(
                border_color=("#ECE9E2", "gray30"),
                fg_color=("#FFFFFF", "gray20"),
            )
            tl.grid_configure(pady=(12, 5))
            ul.grid_configure(pady=(0, 12))

        for widget in (frame, file_icon, title_label, url_label):
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)

        return frame

    def quick_download(self, url: str, filename: str) -> None:
        """Quick download a PDF from the search results."""
        self.select_pdf(url, filename)
        self.app._download_pdf()

    def select_pdf(self, url: str, filename: str) -> None:
        """Select a PDF from the search results."""
        self.app.selected_pdf_url = url
        self.app.selected_pdf_title = filename
        self.app.status_label.configure(text=f"Selected: {filename}")
        self.app.details_label.configure(
            text=f"Filename: {filename}\nURL: {url[:50]}…"
        )
        self.app.executor.submit(self.app._preview_worker, url)

    def show_results(self) -> None:
        """Show the search results frame."""
        self.results_frame.grid()

    def hide_results(self) -> None:
        """Hide the search results frame."""
        self.results_frame.grid_remove()
