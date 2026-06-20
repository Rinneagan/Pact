"""
Persistence stores for Pact PDF application.
Handles reading progress, recent searches, tags, thumbnails, and reading statistics.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import time
from typing import Any, Optional

# Optional dependencies
try:
    from PIL import Image as _Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PACT_DIR = os.path.join(os.path.expanduser("~"), ".pact")
PROGRESS_FILE = os.path.join(PACT_DIR, "progress.json")
RECENT_SEARCHES_FILE = os.path.join(PACT_DIR, "recent_searches.json")
TAGS_FILE = os.path.join(PACT_DIR, "tags.json")
THUMBNAIL_DIR = os.path.join(PACT_DIR, "thumbnails")
STATS_FILE = os.path.join(PACT_DIR, "reading_stats.json")


# ---------------------------------------------------------------------------
# Reading Progress Store
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Recent Searches Store
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tag Store
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Thumbnail Cache
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Reading Stats Store
# ---------------------------------------------------------------------------

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
