"""
Pact - Modern Desktop Application (pywebview version)
A secure PDF search and download application with a premium HTML/CSS/JS interface.
"""

from __future__ import annotations

import os
import re
import io
import time
import base64
import json
import platform
import subprocess
import threading
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor

import fitz  # PyMuPDF
import webview
import requests
from PIL import Image, ImageOps

# Import persistence stores & crawler backend
from persistence import (
    ReadingProgressStore,
    RecentSearchesStore,
    TagStore,
    ThumbnailCache,
    ReadingStatsStore,
    BookmarkStore,
)
from crawler import search_pdfs, validate_url, validate_pdf_file
from config import MAX_SEARCH_RESULTS, DEFAULT_DOWNLOAD_DIR, MAX_FILE_SIZE

PACT_DIR = os.path.join(os.path.expanduser("~"), ".pact")
THEME_FILE = os.path.join(PACT_DIR, "theme.json")


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    import sys
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class PactAPI:
    """JSON-RPC Bridge API exposed to pywebview front-end."""

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.active_downloads: dict[int, dict[str, Any]] = {}
        
        # Initialize persistence stores
        self.progress_store = ReadingProgressStore()
        self.recent_searches = RecentSearchesStore()
        self.tag_store = TagStore()
        self.thumbnail_cache = ThumbnailCache()
        self.stats_store = ReadingStatsStore()
        self.bookmark_store = BookmarkStore()

        # Cache open PyMuPDF document to improve page flipping speed
        self._cached_filepath: Optional[str] = None
        self._cached_doc: Optional[fitz.Document] = None

    def _get_doc(self, filepath: str) -> fitz.Document:
        """Retrieve cached fitz.Document or load it if not cached."""
        if self._cached_filepath == filepath and self._cached_doc is not None:
            return self._cached_doc
            
        if self._cached_doc is not None:
            try:
                self._cached_doc.close()
            except Exception:
                pass
                
        self._cached_filepath = filepath
        self._cached_doc = fitz.open(filepath)
        return self._cached_doc

    def close_document(self) -> None:
        """Explicitly close cached fitz document reference."""
        if self._cached_doc is not None:
            try:
                self._cached_doc.close()
            except Exception:
                pass
            self._cached_doc = None
            self._cached_filepath = None

    def get_theme(self) -> str:
        """Load persisted theme mode preference."""
        try:
            if os.path.exists(THEME_FILE):
                with open(THEME_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    return data.get("theme", "dark")
        except Exception:
            pass
        return "dark"

    def get_logos(self) -> dict[str, str]:
        """Fetch base64 strings of the original light and dark logos."""
        light_path = get_resource_path(os.path.join("assets", "P-logo-design-vector-Graphics-16857419-1-1-580x386.jpg"))
        dark_path = get_resource_path(os.path.join("assets", "Black.png"))
        
        out = {"light": "", "dark": ""}
        try:
            if os.path.exists(light_path):
                with open(light_path, "rb") as fh:
                    out["light"] = base64.b64encode(fh.read()).decode("utf-8")
        except Exception:
            pass
            
        try:
            if os.path.exists(dark_path):
                with open(dark_path, "rb") as fh:
                    out["dark"] = base64.b64encode(fh.read()).decode("utf-8")
        except Exception:
            pass
            
        return out

    def set_theme(self, theme: str) -> None:
        """Persist selected theme preference."""
        try:
            os.makedirs(PACT_DIR, exist_ok=True)
            with open(THEME_FILE, "w", encoding="utf-8") as fh:
                json.dump({"theme": theme}, fh)
        except Exception:
            pass

    def get_downloads_dir(self) -> str:
        """Get the default or configured download directory."""
        return DEFAULT_DOWNLOAD_DIR

    def search(self, query: str) -> list[str]:
        """Search for PDFs via crawler backend."""
        query = query.strip()
        if not query:
            return []
        # Save query to history
        self.recent_searches.add(query)
        # Invoke search crawler
        try:
            return search_pdfs(query, max_results=MAX_SEARCH_RESULTS)
        except Exception as exc:
            print(f"Crawler error: {exc}")
            return []

    def get_recent_searches(self) -> list[str]:
        """Return lists of recent search queries."""
        return self.recent_searches.recent(limit=8)

    def download(self, url: str, title: str) -> dict[str, str]:
        """Initiate PDF download in thread pool."""
        active_count = sum(1 for info in self.active_downloads.values() if info.get("active"))
        if active_count >= 3:
            return {"error": "Maximum 3 concurrent downloads"}

        if not validate_url(url):
            return {"error": "Invalid download URL"}

        download_id = hash(url) ^ int(time.time() * 1000)
        self.executor.submit(self._download_worker, download_id, url, title)
        return {"status": "enqueued", "id": str(download_id)}

    def _download_worker(self, download_id: int, url: str, filename: str) -> None:
        """Worker thread for downloads."""
        save_dir = self.get_downloads_dir()
        
        # Security: sanitize filename
        clean_name = re.sub(r'[\\/:*?"<>|]', "_", filename)
        base, ext = os.path.splitext(clean_name)
        if not ext.lower().endswith(".pdf"):
            ext = ".pdf"
        clean_name = base[:150] + ext
        
        save_path = os.path.join(save_dir, clean_name)

        # Path traversal check
        save_path = os.path.abspath(save_path)
        real_save_dir = os.path.abspath(save_dir)
        if not save_path.startswith(real_save_dir + os.sep) and save_path != real_save_dir:
            return

        # Prevent overwriting
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base} ({counter}){ext}"
            counter += 1

        actual_filename = os.path.basename(save_path)
        self.active_downloads[download_id] = {
            "filename": actual_filename,
            "progress": 0.0,
            "active": True,
            "complete": False,
            "failed": False,
            "error_msg": "",
            "save_path": save_path,
        }

        try:
            # Edge User-Agent header to prevent 403 Forbidden blocks
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
            }
            response = requests.get(url, stream=True, headers=headers, timeout=30)
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length", 0))

            if total_size > MAX_FILE_SIZE:
                self.active_downloads[download_id]["failed"] = True
                self.active_downloads[download_id]["error_msg"] = f"File size exceeds limit ({MAX_FILE_SIZE // 1024 // 1024}MB)"
                self.active_downloads[download_id]["active"] = False
                return

            downloaded = 0
            with open(save_path, "wb") as fh:
                for chunk in response.iter_content(chunk_size=4096):
                    if not self.active_downloads.get(download_id, {}).get("active"):
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE:
                        break
                    fh.write(chunk)
                    progress = (downloaded / total_size * 100) if total_size else 0
                    self.active_downloads[download_id]["progress"] = progress

            if not self.active_downloads.get(download_id, {}).get("active"):
                if os.path.exists(save_path):
                    os.remove(save_path)
                return

            # Validate file
            if not validate_pdf_file(save_path):
                if os.path.exists(save_path):
                    os.remove(save_path)
                self.active_downloads[download_id]["failed"] = True
                self.active_downloads[download_id]["error_msg"] = "Downloaded file is not a valid PDF document"
                self.active_downloads[download_id]["active"] = False
                return

            self.active_downloads[download_id]["complete"] = True
            
        except Exception as exc:
            import logging
            logging.error(f"Download failed for {url}: {exc}")
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except OSError:
                    pass
            self.active_downloads[download_id]["failed"] = True
            self.active_downloads[download_id]["error_msg"] = str(exc)
            self.active_downloads[download_id]["active"] = False
        finally:
            if download_id in self.active_downloads:
                self.active_downloads[download_id]["active"] = False

    def get_active_downloads(self) -> dict[str, dict[str, Any]]:
        """Return active download progress map."""
        out = {}
        for d_id, info in list(self.active_downloads.items()):
            # Keep completed or failed downloads in list until fetched once
            out[str(d_id)] = {
                "filename": info["filename"],
                "progress": info["progress"],
                "active": info["active"],
                "complete": info["complete"],
                "failed": info.get("failed", False),
                "error_msg": info.get("error_msg", ""),
                "save_path": info["save_path"],
            }
            if info["complete"] or not info["active"]:
                self.active_downloads.pop(d_id, None)
        return out

    def cancel_download(self, download_id: str) -> None:
        """Cancel a running download."""
        try:
            d_id = int(download_id)
            if d_id in self.active_downloads:
                self.active_downloads[d_id]["active"] = False
        except Exception:
            pass

    def get_downloads(self) -> list[dict[str, Any]]:
        """Get local PDF list in downloads directory."""
        downloads_dir = self.get_downloads_dir()
        try:
            entries = [
                f for f in os.listdir(downloads_dir)
                if f.lower().endswith(".pdf")
                and os.path.isfile(os.path.join(downloads_dir, f))
            ]
        except Exception:
            return []

        out = []
        for filename in entries:
            fpath = os.path.join(downloads_dir, filename)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                mtime = 0
            out.append({
                "filepath": fpath,
                "filename": filename,
                "mtime": mtime,
            })
        
        # Sorted by newest first
        out.sort(key=lambda x: x["mtime"], reverse=True)
        return out

    def get_thumbnail(self, filepath: str) -> Optional[str]:
        """Fetch base64 thumbnail bytes of a PDF."""
        try:
            img = self.thumbnail_cache.get(filepath)
            if img is not None:
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception:
            pass
        return None

    def get_reading_progress(self) -> list[tuple[str, dict[str, Any]]]:
        """Fetch recently read progress items."""
        return self.progress_store.recent(limit=5)

    def remove_reading_progress(self, filepath: str) -> None:
        """Remove progress item from shelf."""
        self.progress_store.remove(filepath)

    def get_all_tags(self) -> dict[str, list[str]]:
        """Fetch tag mappings for all documents."""
        return self.tag_store._data

    def add_tag(self, filepath: str, tag: str) -> None:
        """Add tag annotation to path."""
        self.tag_store.set_tag(filepath, tag)

    def remove_tag(self, filepath: str, tag: str) -> None:
        """Delete tag annotation."""
        self.tag_store.remove_tag(filepath, tag)

    def get_reading_stats(self) -> dict[str, Any]:
        """Fetch reading statistics and metrics."""
        return {
            "finished_this_month": self.stats_store.documents_finished_this_month(),
            "longest_read": self.stats_store.longest_read(),
            "weekly_pages": self.stats_store.last_n_days_pages(7),
        }

    def get_document_progress(self, filepath: str) -> Optional[dict[str, Any]]:
        """Fetch page progress settings."""
        return self.progress_store.get(filepath)

    def get_total_pages(self, filepath: str) -> int:
        """Fetch total pages in document."""
        try:
            doc = self._get_doc(filepath)
            return len(doc)
        except Exception:
            return 0

    def get_page_image(self, filepath: str, page_num: int, zoom: float, dark_mode: bool) -> Optional[str]:
        """Render a single PDF page to base64 bytes, dynamically inverting in dark mode."""
        try:
            doc = self._get_doc(filepath)
            page = doc.load_page(page_num)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            if dark_mode:
                try:
                    img = ImageOps.invert(img)
                except Exception:
                    pass
                    
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            
            # Log progress and stats views
            self.progress_store.update(filepath, page_num, len(doc))
            self.stats_store.log_page_view(filepath, page_num, len(doc))
            
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception as exc:
            print(f"Render error: {exc}")
            return None

    def get_toc(self, filepath: str) -> list[tuple[int, str, int]]:
        """Fetch table of contents outline."""
        try:
            doc = self._get_doc(filepath)
            return doc.get_toc()
        except Exception:
            return []

    def get_related(self, filepath: str) -> list[tuple[str, str, int]]:
        """Fetch similar PDFs in downloads dir."""
        try:
            from utils.related_docs import find_related_documents
            return find_related_documents(filepath, self.get_downloads_dir(), limit=5)
        except Exception:
            return []

    def get_bookmarks(self, filepath: str) -> list[dict[str, Any]]:
        """Fetch annotative notes and bookmarks."""
        return self.bookmark_store.get(filepath)

    def add_bookmark(self, filepath: str, page: int, note: str) -> None:
        """Save a page note or bookmark."""
        self.bookmark_store.add(filepath, page, note)

    def remove_bookmark(self, filepath: str, page: int) -> None:
        """Delete bookmark/note."""
        self.bookmark_store.remove(filepath, page)

    def get_keywords(self, filepath: str) -> list[dict[str, Any]]:
        """Extract top keywords from the PDF for side-panel keyword cloud navigation."""
        try:
            doc = self._get_doc(filepath)
            pages_to_read = min(len(doc), 15)
            text = ""
            for i in range(pages_to_read):
                text += doc.load_page(i).get_text()
            
            # Simple tokenization
            words = re.findall(r"\b[a-zA-Z]{4,15}\b", text.lower())
            
            stopwords = {
                "this", "that", "with", "from", "your", "them", "then", "there", "their", "they",
                "here", "have", "were", "been", "would", "could", "should", "will", "does", "done",
                "about", "above", "after", "again", "against", "other", "some", "such", "than", "then",
                "their", "these", "those", "under", "until", "upon", "very", "when", "where", "which",
                "while", "who", "whom", "why", "with", "would", "page", "number", "figure", "table"
            }
            
            filtered = [w for w in words if w not in stopwords]
            
            # Count frequencies
            freq: dict[str, int] = {}
            for w in filtered:
                freq[w] = freq.get(w, 0) + 1
                
            sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)
            top_words = sorted_freq[:25]
            if not top_words:
                return []
                
            max_count = top_words[0][1]
            return [
                {
                    "word": w,
                    "count": c,
                    "weight": round((c / max_count) * 10)
                }
                for w, c in top_words
            ]
        except Exception as exc:
            print(f"Keywords extraction error: {exc}")
            return []

    def search_word_pages(self, filepath: str, word: str) -> list[int]:
        """Search which page numbers contain the selected word inside the PDF."""
        try:
            doc = self._get_doc(filepath)
            matches = []
            word_lower = word.lower()
            for page_num in range(len(doc)):
                text = doc.load_page(page_num).get_text().lower()
                if word_lower in text:
                    matches.append(page_num + 1)
            return matches
        except Exception:
            return []

    def get_heatmap_data(self) -> list[dict[str, Any]]:
        """Return daily page log counts for the last 30 weeks (210 days) for contribution heatmap rendering."""
        try:
            import datetime
            today = datetime.date.today()
            daily_pages = self.stats_store._data.get("daily_pages", {})
            
            out = []
            for i in range(209, -1, -1):
                day = (today - datetime.timedelta(days=i)).isoformat()
                count = daily_pages.get(day, 0)
                out.append({
                    "date": day,
                    "count": count
                })
            return out
        except Exception:
            return []

    def get_today_pages_read(self) -> int:
        """Fetch today's pages read count from the statistics store."""
        try:
            import datetime
            today = datetime.date.today().isoformat()
            return self.stats_store._data.get("daily_pages", {}).get(today, 0)
        except Exception:
            return 0

    def open_external(self, filepath: str) -> None:
        """Securely invoke system handler to view PDF."""
        try:
            real_path = os.path.abspath(filepath)
            downloads_dir = os.path.abspath(self.get_downloads_dir())

            # Path traversal check
            if not real_path.startswith(downloads_dir + os.sep) and real_path != downloads_dir:
                return

            # File type enforcement
            if not real_path.lower().endswith(".pdf"):
                return

            if not os.path.exists(real_path):
                return

            system = platform.system()
            if system == "Windows":
                os.startfile(real_path)  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.Popen(["open", real_path])
            else:
                subprocess.Popen(["xdg-open", real_path])
        except Exception:
            pass


def main() -> None:
    api = PactAPI()
    
    # Create template .env if it doesn't exist in user profile
    user_env_file = os.path.join(PACT_DIR, ".env")
    if not os.path.exists(user_env_file):
        try:
            os.makedirs(PACT_DIR, exist_ok=True)
            with open(user_env_file, "w", encoding="utf-8") as fh:
                fh.write("# Pact API Configuration\n# Enter your SerpApi key below to enable PDF search:\nSERPAPI_KEY=\n")
        except Exception:
            pass

    # Ensure local downloads folder exists
    try:
        os.makedirs(api.get_downloads_dir(), exist_ok=True)
    except Exception:
        pass
            
    # Locate absolute path to web/ directory
    web_dir = get_resource_path("web")
    
    # Initialize pywebview window
    webview.create_window(
        title="Pact",
        url=os.path.join(web_dir, "index.html"),
        js_api=api,
        width=1400,
        height=850,
        min_size=(1100, 700),
        background_color="#0A0D14"
    )
    
    # Start app web server locally
    webview.start(http_server=True)


if __name__ == "__main__":
    main()
