"""
Pact - Modern Desktop Application
A secure PDF search and download application with a light, airy aesthetic.

Includes the integrated PactReader, embedded directly in the main window
(no separate popup window), plus draggable, resizable panels.
"""

from __future__ import annotations

from tkinter import filedialog as tk_filedialog

import datetime
import hashlib
import json
import os
import platform
import re
import subprocess
import time
import tkinter as tk
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

import customtkinter as ctk

# ---------------------------------------------------------------------------
# Module-level imports with explicit availability flags
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Local persistence — reading progress + recent searches.
# Both live under ~/.pact as small JSON sidecars. Failures are swallowed
# on purpose: persistence is a nice-to-have, never a reason to crash.
# ---------------------------------------------------------------------------

PACT_DIR = os.path.join(os.path.expanduser("~"), ".pact")
PROGRESS_FILE = os.path.join(PACT_DIR, "progress.json")
RECENT_SEARCHES_FILE = os.path.join(PACT_DIR, "recent_searches.json")


class ReadingProgressStore:
    """Tracks per-file reading position so the app can resume where the
    user left off and surface a 'Continue Reading' shelf."""

    def __init__(self) -> None:
        os.makedirs(PACT_DIR, exist_ok=True)
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        try:
            with open(PROGRESS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError:
            pass

    def update(self, filepath: str, current_page: int, total_pages: int, title: str = "") -> None:
        key = os.path.abspath(filepath)
        self._data[key] = {
            "current_page": current_page,
            "total_pages": total_pages,
            "title": title or os.path.basename(filepath),
            "last_opened": time.time(),
        }
        self._save()

    def get(self, filepath: str) -> Optional[dict[str, Any]]:
        return self._data.get(os.path.abspath(filepath))

    def remove(self, filepath: str) -> None:
        key = os.path.abspath(filepath)
        if key in self._data:
            del self._data[key]
            self._save()

    def recent(self, limit: int = 3, exclude_finished: bool = True) -> list[tuple[str, dict[str, Any]]]:
        """Most recently opened files, newest first. Skips files that no
        longer exist on disk and (optionally) ones already fully read."""
        items: list[tuple[str, dict[str, Any]]] = []
        for path, info in self._data.items():
            if not os.path.exists(path):
                continue
            total = max(info.get("total_pages", 1), 1)
            current = info.get("current_page", 0)
            if exclude_finished and current >= total - 1:
                continue
            items.append((path, info))
        items.sort(key=lambda kv: kv[1].get("last_opened", 0), reverse=True)
        return items[:limit]


class RecentSearchesStore:
    """Remembers the last ~20 search terms for quick re-use as chips."""

    MAX_ITEMS = 20

    def __init__(self) -> None:
        os.makedirs(PACT_DIR, exist_ok=True)
        self._terms: list[str] = self._load()

    def _load(self) -> list[str]:
        try:
            with open(RECENT_SEARCHES_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _save(self) -> None:
        try:
            with open(RECENT_SEARCHES_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._terms, fh, indent=2)
        except OSError:
            pass

    def add(self, term: str) -> None:
        term = term.strip()
        if not term:
            return
        self._terms = [t for t in self._terms if t.lower() != term.lower()]
        self._terms.insert(0, term)
        self._terms = self._terms[: self.MAX_ITEMS]
        self._save()

    def recent(self, limit: int = 8) -> list[str]:
        return self._terms[:limit]


TAGS_FILE = os.path.join(PACT_DIR, "tags.json")
THUMBNAIL_DIR = os.path.join(PACT_DIR, "thumbnails")
STATS_FILE = os.path.join(PACT_DIR, "reading_stats.json")


class TagStore:
    """Simple manual tagging so the Library view can group documents by
    subject instead of only by recency. Stored as filepath -> [tags]."""

    def __init__(self) -> None:
        os.makedirs(PACT_DIR, exist_ok=True)
        self._data: dict[str, list[str]] = self._load()

    def _load(self) -> dict[str, list[str]]:
        try:
            with open(TAGS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        try:
            with open(TAGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError:
            pass

    def get(self, filepath: str) -> list[str]:
        return self._data.get(os.path.abspath(filepath), [])

    def set_tag(self, filepath: str, tag: str) -> None:
        tag = tag.strip()
        if not tag:
            return
        key = os.path.abspath(filepath)
        tags = self._data.setdefault(key, [])
        if tag not in tags:
            tags.append(tag)
            self._save()

    def remove_tag(self, filepath: str, tag: str) -> None:
        key = os.path.abspath(filepath)
        if key in self._data and tag in self._data[key]:
            self._data[key].remove(tag)
            if not self._data[key]:
                del self._data[key]
            self._save()


class ThumbnailCache:
    """Generates and disk-caches small first-page preview images for the
    Library grid, so it doesn't have to re-render PDFs on every refresh.
    Cache keys include mtime so an edited/replaced file gets a fresh
    thumbnail automatically."""

    SIZE = (160, 200)

    def __init__(self) -> None:
        os.makedirs(THUMBNAIL_DIR, exist_ok=True)

    def _cache_path(self, filepath: str) -> str:
        try:
            mtime = int(os.path.getmtime(filepath))
        except OSError:
            mtime = 0
        key = f"{os.path.abspath(filepath)}:{mtime}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return os.path.join(THUMBNAIL_DIR, f"{digest}.jpg")

    def get(self, filepath: str) -> Optional[Any]:
        """Returns a PIL Image (generating + caching it if needed), or None
        on any failure — missing libs, corrupt PDF, vanished file, etc."""
        if not (PYMUPDF_AVAILABLE and PIL_AVAILABLE):
            return None
        try:
            cache_path = self._cache_path(filepath)
            if os.path.exists(cache_path):
                img = _Image.open(cache_path)
                img.load()
                return img.convert("RGB")

            doc = fitz.open(filepath)
            page = doc.load_page(0)
            mat = fitz.Matrix(0.7, 0.7)
            pix = page.get_pixmap(matrix=mat)
            img = _Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

            img.thumbnail(self.SIZE, resample=1)
            try:
                img.save(cache_path, "JPEG", quality=82)
            except OSError:
                pass
            return img
        except Exception:
            return None


class ReadingStatsStore:
    """A quiet, append-only-ish log behind the sidebar's Reading Log panel.
    Tracks pages viewed per day and which documents have been finished
    (reached their last page). Deliberately framed as a personal log, not
    a streak/nag mechanic — no 'don't break your streak' messaging."""

    def __init__(self) -> None:
        os.makedirs(PACT_DIR, exist_ok=True)
        self._data: dict[str, Any] = self._load()
        self._data.setdefault("daily_pages", {})
        self._data.setdefault("finished", {})

    def _load(self) -> dict[str, Any]:
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        try:
            with open(STATS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError:
            pass

    def log_page_view(self, filepath: str, current_page: int, total_pages: int, title: str = "") -> None:
        today = datetime.date.today().isoformat()
        daily = self._data["daily_pages"]
        daily[today] = daily.get(today, 0) + 1

        if total_pages > 0 and current_page >= total_pages - 1:
            key = os.path.abspath(filepath)
            if key not in self._data["finished"]:
                self._data["finished"][key] = {
                    "title": title or os.path.basename(filepath),
                    "total_pages": total_pages,
                    "finished_at": time.time(),
                }
        self._save()

    def documents_finished_this_month(self) -> int:
        now = datetime.datetime.now()
        count = 0
        for info in self._data["finished"].values():
            dt = datetime.datetime.fromtimestamp(info.get("finished_at", 0))
            if dt.year == now.year and dt.month == now.month:
                count += 1
        return count

    def longest_read(self) -> Optional[tuple[str, int]]:
        finished = self._data["finished"]
        if not finished:
            return None
        best = max(finished.values(), key=lambda i: i.get("total_pages", 0))
        if best.get("total_pages", 0) <= 0:
            return None
        return best.get("title", "—"), best.get("total_pages", 0)

    def last_n_days_pages(self, n: int = 7) -> list[int]:
        today = datetime.date.today()
        daily = self._data["daily_pages"]
        out = []
        for i in range(n - 1, -1, -1):
            day = (today - datetime.timedelta(days=i)).isoformat()
            out.append(daily.get(day, 0))
        return out


_RECENCY_BUCKET_ORDER = ["Today", "Yesterday", "This Week", "This Month", "Earlier"]


def _recency_bucket(mtime: float) -> str:
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


# ---------------------------------------------------------------------------
# Related documents — cheap, dependency-free token-overlap matching.
# No ML, no external index: just filename tokens weighted by how rare
# they are across the downloads folder (a crude IDF), so a shared token
# like "che352" counts for more than a generic one like "report".
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "your",
    "a", "an", "of", "to", "in", "on", "is", "are", "by", "or", "at",
    "report", "document", "final", "draft", "copy", "new", "untitled",
}


def _tokenize_name(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def find_related_documents(filepath: str, downloads_dir: str, limit: int = 5) -> list[tuple[str, str, int]]:
    """Returns up to `limit` (filepath, filename, shared_token_count) tuples
    for other PDFs in `downloads_dir` whose filenames share tokens with the
    given file, ranked by how distinctive the shared tokens are."""
    target_tokens = _tokenize_name(os.path.splitext(os.path.basename(filepath))[0])
    if not target_tokens:
        return []

    try:
        candidates = [f for f in os.listdir(downloads_dir) if f.lower().endswith(".pdf")]
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        candidates = []

    doc_tokens = {f: _tokenize_name(os.path.splitext(f)[0]) for f in candidates}

    token_doc_count: Counter[str] = Counter()
    for toks in doc_tokens.values():
        for t in toks:
            token_doc_count[t] += 1

    scored: list[tuple[float, str, str, int]] = []
    for fname, cand_tokens in doc_tokens.items():
        fpath = os.path.join(downloads_dir, fname)
        if os.path.abspath(fpath) == os.path.abspath(filepath):
            continue
        shared = target_tokens & cand_tokens
        if not shared:
            continue
        score = sum(1.0 / token_doc_count[t] for t in shared)
        scored.append((score, fpath, fname, len(shared)))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [(fpath, fname, shared) for _, fpath, fname, shared in scored[:limit]]


# ---------------------------------------------------------------------------
# Typography — cached font factory
# ---------------------------------------------------------------------------

class PremiumTypography:
    """Cached typography system for consistent, modern fonts."""

    GEOMETRIC_FONT_FAMILY: str = "Segoe UI"
    MONOSPACE_FONT_FAMILY: str = "Consolas"

    _cache: dict[tuple, ctk.CTkFont] = {}

    @classmethod
    def _get(cls, family: str, size: int, weight: str) -> ctk.CTkFont:
        key = (family, size, weight)
        if key not in cls._cache:
            cls._cache[key] = ctk.CTkFont(family=family, size=size, weight=weight)
        return cls._cache[key]

    @classmethod
    def heading_large(cls, size: int = 28, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def heading_medium(cls, size: int = 18, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def heading_small(cls, size: int = 16, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def body_text(cls, size: int = 14, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def body_small(cls, size: int = 12, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def monospace(cls, size: int = 11, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.MONOSPACE_FONT_FAMILY, size, weight)

    @classmethod
    def button_text(cls, size: int = 14, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)


# ---------------------------------------------------------------------------
# Integrated PDF Reader — now an embeddable frame, not a Toplevel window.
# ---------------------------------------------------------------------------

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
        self.download_slots: dict[int, dict[str, Any]] = {}

        # Tracks the currently embedded reader view (None when showing search)
        self.reader_view: Optional[PactReaderView] = None
        # Which view to return to when the reader's Back button is used.
        self._reader_return_view: str = "results"

        self.progress_store = ReadingProgressStore()
        self.recent_searches = RecentSearchesStore()
        self.tag_store = TagStore()
        self.thumbnail_cache = ThumbnailCache()
        self.stats_store = ReadingStatsStore()

        self.executor = ThreadPoolExecutor(max_workers=4)

        self._setup_grid_layout()
        self._create_zone_frames()
        self._populate_sidebar()
        self._populate_main_view()
        self._populate_preview_pane()
        self._populate_footer()

        self._import_backend()
        self._refresh_downloads_list()
        self._refresh_continue_reading()
        self._refresh_reading_stats()

        if TKDND_AVAILABLE:
            self._setup_drag_and_drop()
        else:
            print("tkinterdnd2 not installed — drag-and-drop import disabled")

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
            command=self._toggle_library_view,
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

        # --- Reading Log (feature 10): a quiet personal log, not a streak
        # mechanic — just "what have I actually been reading lately". ---
        self.stats_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.stats_frame.grid(row=5, column=0, padx=20, pady=(0, 8), sticky="ew")
        self.stats_frame.grid_columnconfigure(0, weight=1)

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
        self._refresh_reading_stats()

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

    def _select_folder(self) -> None:
        from tkinter import filedialog as tk_filedialog
        folder = tk_filedialog.askdirectory()
        if folder:
            self.selected_directory = folder
            self.status_label.configure(text=f"Download folder: {folder}")
            self._refresh_downloads_list()
        else:
            self.status_label.configure(text="Folder selection cancelled")

    def _populate_main_view(self) -> None:
        self.search_frame = ctk.CTkFrame(
            self.main_view_frame, height=80, fg_color="transparent",
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
        self.search_entry.bind("<Return>", lambda e: self._perform_search())
        self.search_entry.bind("<FocusIn>", self._show_search_suggestions)
        self.search_entry.bind("<KeyRelease>", self._on_search_entry_key)
        self.search_entry.bind("<FocusOut>", lambda e: self.root.after(150, self._hide_search_suggestions))

        self.search_button = ctk.CTkButton(
            self.search_frame,
            text="Search",
            font=PremiumTypography.button_text(),
            width=140, height=50, corner_radius=14,
            fg_color="#639922", hover_color="#4F7A1B",
            command=self._perform_search,
        )
        self.search_button.grid(row=0, column=1, pady=15, sticky="e")

        self.suggestions_frame = ctk.CTkFrame(self.search_frame, fg_color="transparent")
        self.suggestions_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=2, pady=(0, 6))
        self.suggestions_frame.grid_remove()

        # Holds either the results list or the embedded reader view.
        self.main_content_frame = ctk.CTkFrame(
            self.main_view_frame, fg_color="transparent",
        )
        self.main_content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

        self.results_frame = ctk.CTkScrollableFrame(
            self.main_content_frame,
            label_text="Search Results",
            label_font=PremiumTypography.heading_medium(),
            corner_radius=14,
            fg_color="transparent",
            label_text_color=("#2C2C2A", "gray90"),
        )
        self.results_frame.grid(row=0, column=0, sticky="nsew")

        # Library grid view (feature 9) — swaps in over results_frame.
        self.library_frame = ctk.CTkScrollableFrame(
            self.main_content_frame,
            label_text="Library",
            label_font=PremiumTypography.heading_medium(),
            corner_radius=14,
            fg_color="transparent",
            label_text_color=("#2C2C2A", "gray90"),
        )
        self.library_frame.grid(row=0, column=0, sticky="nsew")
        self.library_frame.grid_remove()

        self.error_label = ctk.CTkLabel(
            self.main_view_frame,
            text="",
            text_color="red",
            font=PremiumTypography.body_small(),
        )
        self.error_label.grid(row=0, column=0, sticky="s", padx=20, pady=(0, 10))

    def _perform_search(self) -> None:
        if self.is_searching:
            return

        search_term = self.search_entry.get().strip()
        if not search_term:
            self._show_error("Please enter a search term")
            return

        if not self.search_pdfs:
            self._show_error("Backend not available")
            return

        # If a PDF reader or the library grid is currently shown, return to
        # search before showing new results.
        if self.reader_view is not None:
            self._close_reader_view()
        if self.library_frame.winfo_ismapped():
            self._close_library_view()

        self.suggestions_frame.grid_remove()
        self.recent_searches.add(search_term)

        self.is_searching = True
        self._set_searching_state(True)
        self.executor.submit(self._search_worker, search_term)

    def _search_worker(self, search_term: str) -> None:
        try:
            results = self.search_pdfs(search_term, max_results=self.max_search_results)
            self._ui(lambda: self._update_search_results(results, search_term))
        except Exception as exc:
            msg = str(exc)
            self._ui(lambda: self._show_error(f"Search failed: {msg}"))
        finally:
            self._ui(lambda: self._set_searching_state(False))

    def _show_search_suggestions(self, event: Any = None) -> None:
        if self.search_entry.get().strip():
            return
        self._populate_suggestions_frame()
        if self.suggestions_frame.winfo_children():
            self.suggestions_frame.grid()

    def _on_search_entry_key(self, event: Any = None) -> None:
        if self.search_entry.get().strip():
            self.suggestions_frame.grid_remove()
        else:
            self._show_search_suggestions()

    def _hide_search_suggestions(self) -> None:
        self.suggestions_frame.grid_remove()

    def _populate_suggestions_frame(self) -> None:
        for widget in self.suggestions_frame.winfo_children():
            widget.destroy()

        terms = self.recent_searches.recent(limit=8)
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
                command=lambda t=term: self._use_suggested_search(t),
            )
            chip.pack(side="left", padx=3)

    def _use_suggested_search(self, term: str) -> None:
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, term)
        self.suggestions_frame.grid_remove()
        self._perform_search()

    def _set_searching_state(self, searching: bool) -> None:
        self.is_searching = searching
        if searching:
            self.search_button.configure(state="disabled", text="Searching…")
            self.search_entry.configure(state="disabled")
            self._show_skeleton_loader()
        else:
            self.search_button.configure(state="normal", text="Search")
            self.search_entry.configure(state="normal")
            self._hide_skeleton_loader()

    def _show_skeleton_loader(self) -> None:
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        self.skeleton_container = ctk.CTkFrame(
            self.results_frame, fg_color="transparent",
        )
        self.skeleton_container.pack(fill="x", pady=10)

        for _ in range(5):
            self._create_skeleton_card().pack(fill="x", pady=5, padx=10)

        self._skeleton_running = True
        self._skeleton_phase = 0.0
        self._animate_skeleton_gradient()

    def _create_skeleton_card(self) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self.skeleton_container, corner_radius=14,
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

    def _animate_skeleton_gradient(self) -> None:
        if not self._skeleton_running:
            return

        self._skeleton_phase = (self._skeleton_phase + 0.1) % 6.2832

        if hasattr(self, "skeleton_container") and self.skeleton_container.winfo_exists():
            bright = self._skeleton_phase < 3.14159
            for card in self.skeleton_container.winfo_children():
                if isinstance(card, ctk.CTkFrame):
                    for child in card.winfo_children():
                        if isinstance(child, ctk.CTkFrame):
                            child.configure(
                                fg_color=("gray75" if bright else "gray80", "gray20")
                            )

        self.root.after(16, self._animate_skeleton_gradient)

    def _hide_skeleton_loader(self) -> None:
        self._skeleton_running = False
        if hasattr(self, "skeleton_container") and self.skeleton_container.winfo_exists():
            self.skeleton_container.pack_forget()

    def _update_search_results(self, results: list[str], search_term: str) -> None:
        self._hide_skeleton_loader()

        for widget in self.results_frame.winfo_children():
            widget.destroy()

        self.search_results = results

        if not results:
            ctk.CTkLabel(
                self.results_frame,
                text=f"No PDFs found for '{search_term}'",
                font=PremiumTypography.body_text(),
                text_color="gray",
            ).pack(pady=20)
            self.status_label.configure(text=f"No results for '{search_term}'")
            return

        for idx, url in enumerate(results):
            self._create_result_item(idx, url).pack(fill="x", pady=5, padx=10)

        self.status_label.configure(text=f"Found {len(results)} PDFs for '{search_term}'")

    def _create_result_item(self, idx: int, url: str) -> ctk.CTkFrame:
        from urllib.parse import urlparse, unquote
        import re

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
            command=lambda u=url, f=filename: self._quick_download(u, f),
        )
        download_btn.grid(row=0, column=2, rowspan=2, sticky="e", padx=(0, 12), pady=12)

        select_cb = lambda e, u=url, f=filename: self._select_pdf(u, f)
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

    def _quick_download(self, url: str, filename: str) -> None:
        self._select_pdf(url, filename)
        self._download_pdf()

    def _select_pdf(self, url: str, filename: str) -> None:
        self.selected_pdf_url = url
        self.selected_pdf_title = filename
        self.status_label.configure(text=f"Selected: {filename}")
        self.details_label.configure(
            text=f"Filename: {filename}\nURL: {url[:50]}…"
        )
        self.executor.submit(self._preview_worker, url)

    def _preview_worker(self, url: str) -> None:
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
            command=self._download_pdf,
        )
        self.download_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.preview_pane_frame.grid_rowconfigure(2, weight=0)

    def _download_pdf(self) -> None:
        if not self.selected_pdf_url:
            self._show_error("No PDF selected")
            return

        if not REQUESTS_AVAILABLE:
            self._show_error("requests library not installed")
            return

        active_count = sum(
            1 for info in self.active_downloads.values() if info.get("active")
        )
        if active_count >= 3:
            self._show_error("Maximum 3 concurrent downloads")
            return

        if self.validate_url and not self.validate_url(self.selected_pdf_url):
            self._show_error("Invalid URL")
            return

        self.executor.submit(
            self._download_worker, self.selected_pdf_url, self.selected_pdf_title
        )

    def _download_worker(self, url: str, filename: str) -> None:
        import requests

        save_dir = self.selected_directory or self.default_download_dir
        save_path = os.path.join(save_dir, filename)

        # --- FIX: Prevent silent overwrites by appending a counter ---
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base} ({counter}){ext}"
            counter += 1
            
        # Grab the updated filename so the UI and the "Read" button use the right file
        actual_filename = os.path.basename(save_path)
        
        # Calculate the ID using the actual filename to prevent queue collisions
        download_id = id(actual_filename) ^ id(url)
        # -------------------------------------------------------------

        try:
            self._ui(lambda: self._add_download_to_queue(download_id, actual_filename))
            self.active_downloads[download_id] = {"active": True, "filename": actual_filename}

            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length", 0))

            if total_size > self.max_file_size:
                mb = total_size / (1024 * 1024)
                self._ui(lambda: self._show_error(f"File too large ({mb:.1f} MB)"))
                self._ui(lambda: self._remove_download_from_queue(download_id))
                return

            downloaded = 0
            with open(save_path, "wb") as fh:
                for chunk in response.iter_content(chunk_size=1024):
                    if not self.active_downloads.get(download_id, {}).get("active"):
                        break
                    downloaded += len(chunk)
                    fh.write(chunk)
                    progress = (downloaded / total_size * 100) if total_size else 0
                    self._ui(lambda p=progress: self._update_download_progress(download_id, p))

            if self.validate_pdf_file and not self.validate_pdf_file(save_path):
                os.remove(save_path)
                self._ui(lambda: self._show_error("Downloaded file is not a valid PDF"))
                self._ui(lambda: self._remove_download_from_queue(download_id))
                return

            self._ui(lambda: self._download_complete(download_id, actual_filename))

        except Exception as exc:
            msg = str(exc)
            self._ui(lambda: self._show_error(f"Download failed: {msg}"))
            self._ui(lambda: self._remove_download_from_queue(download_id))
        finally:
            if download_id in self.active_downloads:
                self.active_downloads[download_id]["active"] = False

    def _populate_footer(self) -> None:
        self.status_label = ctk.CTkLabel(
            self.footer_frame,
            text="Ready",
            font=PremiumTypography.body_small(),
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="w", padx=20, pady=10)

        self.download_queue_frame = ctk.CTkFrame(
            self.footer_frame, fg_color="transparent",
        )
        self.download_queue_frame.grid(row=0, column=1, sticky="e", padx=20, pady=10)

        for i in range(3):
            self.download_queue_frame.grid_columnconfigure(i, weight=0)
        self.download_queue_frame.grid_rowconfigure(0, weight=0)

    def _find_free_slot(self) -> int:
        used = {info["slot"] for info in self.download_slots.values()}
        for i in range(3):
            if i not in used:
                return i
        return -1

    def _add_download_to_queue(self, download_id: int, filename: str) -> None:
        slot_index = self._find_free_slot()
        if slot_index == -1:
            return

        slot_frame = ctk.CTkFrame(self.download_queue_frame)
        slot_frame.grid(row=0, column=slot_index, padx=5, pady=5)

        progress_bar = ctk.CTkProgressBar(slot_frame, width=150)
        progress_bar.grid(row=0, column=0, padx=5, pady=5)
        progress_bar.set(0)

        cancel_btn = ctk.CTkButton(
            slot_frame, text="✕", width=30, height=30,
            command=lambda: self._cancel_download(download_id),
        )
        cancel_btn.grid(row=0, column=1, padx=5, pady=5)

        self.download_slots[download_id] = {
            "slot": slot_index,
            "frame": slot_frame,
            "progress_bar": progress_bar,
        }

    def _remove_download_from_queue(self, download_id: int) -> None:
        slot = self.download_slots.pop(download_id, None)
        if slot and slot["frame"].winfo_exists():
            slot["frame"].destroy()

    def _update_download_progress(self, download_id: int, progress: float) -> None:
        slot = self.download_slots.get(download_id)
        if slot:
            slot["progress_bar"].set(progress / 100)

    def _download_complete(self, download_id: int, filename: str) -> None:
        self.status_label.configure(text=f"Downloaded: {filename}")

        slot = self.download_slots.get(download_id)
        if not slot:
            self._refresh_downloads_list()
            return

        slot["progress_bar"].set(1.0)

        save_dir = self.selected_directory or self.default_download_dir
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
            command=lambda p=save_path, f=filename: self._open_reader(p, f)
        )
        read_btn.grid(row=0, column=1, padx=5, pady=5)

        self._refresh_downloads_list()

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
            self._reader_return_view = "library" if self.library_frame.winfo_ismapped() else "results"
            self.results_frame.grid_remove()
            self.library_frame.grid_remove()

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
            self.results_frame.grid()

    def _close_reader_view(self) -> None:
        """Tear down the embedded reader and bring back whichever view —
        search results or the library grid — was showing before."""
        if self.reader_view is not None:
            self.reader_view.close()
            self.reader_view.destroy()
            self.reader_view = None

        if self._reader_return_view == "library":
            self.library_frame.grid()
            self.library_btn.configure(fg_color=("#E1EFC9", "gray30"))
            self._populate_library_grid()
            self.status_label.configure(text="Library")
        else:
            self.results_frame.grid()
            self.status_label.configure(text="Ready")
        self._refresh_continue_reading()
        self._refresh_reading_stats()

    def _cancel_download(self, download_id: int) -> None:
        if download_id in self.active_downloads:
            self.active_downloads[download_id]["active"] = False
        self._remove_download_from_queue(download_id)
        self.status_label.configure(text="Download cancelled")

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
            self._refresh_library_view_if_open()
            return

        for filename in entries:
            filepath = os.path.join(downloads_dir, filename)
            self._create_downloaded_file_item(filepath, filename).pack(
                fill="x", pady=3, padx=2
            )

        self._refresh_library_view_if_open()

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

    # ------------------------------------------------------------------
    # Library view (feature 9) — a grid of cover-thumbnail cards grouped
    # by tag first (when tags exist) and then by recency, instead of one
    # flat scrollable list. Swaps into main_content_frame the same way
    # the reader does.
    # ------------------------------------------------------------------
    def _toggle_library_view(self) -> None:
        if self.reader_view is not None:
            # Closing the reader already restores whichever view was active
            # before it opened; force that back to "library" since that's
            # specifically what was just requested.
            self._reader_return_view = "library"
            self._close_reader_view()
            return
        if self.library_frame.winfo_ismapped():
            self._close_library_view()
        else:
            self._open_library_view()

    def _open_library_view(self) -> None:
        self.results_frame.grid_remove()
        self.library_frame.grid()
        self.library_btn.configure(fg_color=("#E1EFC9", "gray30"))
        self._populate_library_grid()
        self.status_label.configure(text="Library")

    def _close_library_view(self) -> None:
        self.library_frame.grid_remove()
        self.results_frame.grid()
        self.library_btn.configure(fg_color=("#F3F1EA", "gray22"))
        self.status_label.configure(text="Ready")

    def _refresh_library_view_if_open(self) -> None:
        if hasattr(self, "library_frame") and self.library_frame.winfo_ismapped():
            self._populate_library_grid()

    def _populate_library_grid(self) -> None:
        for widget in self.library_frame.winfo_children():
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
            tags = self.tag_store.get(fpath)
            if tags: 
                for t in tags:
                    tagged_groups.setdefault(t, []).append((fpath, fname, mtime))
            else:
                untagged.append((fpath, fname, mtime))

        for tag in sorted(tagged_groups.keys()):
            group_items = sorted(tagged_groups[tag], key=lambda t: t[2], reverse=True)
            self._render_library_section(f"🏷 {tag}", group_items)

        buckets: dict[str, list] = {b: [] for b in _RECENCY_BUCKET_ORDER}
        for fpath, fname, mtime in untagged:
            buckets[_recency_bucket(mtime)].append((fpath, fname, mtime))

        for bucket in _RECENCY_BUCKET_ORDER:
            group_items = sorted(buckets[bucket], key=lambda t: t[2], reverse=True)
            if group_items:
                self._render_library_section(bucket, group_items)

    def _render_library_section(self, header: str, items: list) -> None:
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
            card = self._create_library_card(grid, fpath, fname)
            card.grid(row=idx // cols, column=idx % cols, padx=6, pady=6, sticky="nsew")

    def _create_library_card(self, parent, filepath: str, filename: str) -> ctk.CTkFrame:
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

        tags = self.tag_store.get(filepath)
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
            command=lambda p=filepath: self._prompt_add_tag(p),
        )
        tag_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=6)

        open_cb = lambda e, p=filepath, f=filename: self._open_reader(p, f)
        for w in (card, thumb_label):
            w.bind("<Button-1>", open_cb)

        self.executor.submit(self._load_library_thumbnail, filepath, thumb_label)

        return card

    def _load_library_thumbnail(self, filepath: str, label_widget: ctk.CTkLabel) -> None:
        img = self.thumbnail_cache.get(filepath)
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

        self._ui(apply)

    def _prompt_add_tag(self, filepath: str) -> None:
        dialog = ctk.CTkInputDialog(text="Tag this document:", title="Add Tag")
        tag = dialog.get_input()
        if tag:
            self.tag_store.set_tag(filepath, tag)
            self._refresh_library_view_if_open()

    # ------------------------------------------------------------------
    # Drag-and-drop import (feature 4) — lets a PDF be dropped straight
    # into the window to land in the downloads folder / library, without
    # going through search. Requires the optional tkinterdnd2 package;
    # silently does nothing (with a one-time console note) if it's absent.
    # ------------------------------------------------------------------
    def _setup_drag_and_drop(self) -> None:
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_files_dropped)
            self.root.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self.root.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        except Exception as exc:
            print(f"Drag-and-drop setup failed: {exc}")

    def _on_drag_enter(self, event: Any) -> None:
        self.main_view_frame.configure(border_width=2, border_color="#639922")

    def _on_drag_leave(self, event: Any) -> None:
        self.main_view_frame.configure(border_width=0)

    def _on_files_dropped(self, event: Any) -> None:
        self.main_view_frame.configure(border_width=0)
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]

        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        if not pdfs:
            self._show_error("Drop a PDF file to import it")
            return

        for src in pdfs:
            self.executor.submit(self._import_dropped_pdf, src)

    def _import_dropped_pdf(self, src_path: str) -> None:
        import shutil

        try:
            if not os.path.isfile(src_path):
                self._ui(lambda: self._show_error(f"File not found: {os.path.basename(src_path)}"))
                return

            if self.validate_pdf_file and not self.validate_pdf_file(src_path):
                name = os.path.basename(src_path)
                self._ui(lambda n=name: self._show_error(f"Not a valid PDF: {n}"))
                return

            dest_dir = self._get_downloads_dir()
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, os.path.basename(src_path))

            if os.path.abspath(src_path) != os.path.abspath(dest_path):
                base, ext = os.path.splitext(dest_path)
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = f"{base} ({counter}){ext}"
                    counter += 1
                shutil.copy2(src_path, dest_path)

            imported_name = os.path.basename(dest_path)
            self._ui(lambda n=imported_name: self.status_label.configure(text=f"Imported: {n}"))
            self._ui(self._refresh_downloads_list)
        except Exception as exc:
            msg = str(exc)
            self._ui(lambda: self._show_error(f"Import failed: {msg}"))

    # ------------------------------------------------------------------
    # Reading Log (feature 10) — a quiet, non-gamified glance at reading
    # activity: documents finished this month, the longest read, and a
    # tiny 7-day sparkline of pages viewed. No streaks, no guilt.
    # ------------------------------------------------------------------
    def _refresh_reading_stats(self) -> None:
        if not hasattr(self, "stats_frame"):
            return
        for widget in self.stats_frame.winfo_children():
            widget.destroy()

        finished_count = self.stats_store.documents_finished_this_month()
        longest = self.stats_store.longest_read()
        daily = self.stats_store.last_n_days_pages(7)

        ctk.CTkLabel(
            self.stats_frame, text="Reading Log",
            font=PremiumTypography.heading_small(size=12),
            text_color=("#2C2C2A", "gray90"), anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        if finished_count == 0 and not longest:
            summary = "Nothing finished yet"
        else:
            summary = f"{finished_count} finished this month"
            if longest:
                title, pages = longest
                short_title = title if len(title) <= 18 else title[:15] + "…"
                summary += f"\nLongest: {short_title} ({pages}p)"

        ctk.CTkLabel(
            self.stats_frame, text=summary,
            font=PremiumTypography.body_small(size=11),
            text_color="gray", anchor="w", justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 6))

        sparkline = self._draw_sparkline(self.stats_frame, daily)
        sparkline.grid(row=2, column=0, sticky="w")

    def _draw_sparkline(self, parent: Any, values: list[int]) -> tk.Canvas:
        width, height, bar_w, gap = 168, 28, 16, 4
        bg = "gray17" if self.is_dark_theme else "#F3F1EA"
        bar_color = "#97C459" if self.is_dark_theme else "#639922"

        canvas = tk.Canvas(parent, width=width, height=height, highlightthickness=0, bg=bg)
        max_val = max(values) if max(values) > 0 else 1
        for i, v in enumerate(values):
            bar_h = max(2, int((v / max_val) * (height - 4))) if v > 0 else 0
            x0 = i * (bar_w + gap)
            x1 = x0 + bar_w
            y1 = height
            y0 = height - bar_h if v > 0 else height - 2
            canvas.create_rectangle(x0, y0, x1, y1, fill=bar_color, outline="")
        return canvas

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        self.status_label.configure(text=f"Error: {message}")
        self.root.after(5000, lambda: self.error_label.configure(text=""))



if __name__ == "__main__":
    app = PactApp()
    app.run()