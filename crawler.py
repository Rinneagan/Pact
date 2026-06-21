"""
crawler.py — backend for Pact PDF search & download application.

Public API (imported by pact.py):
    search_pdfs(query, max_results) -> list[str]
    preview_pdf(url)               -> PIL.Image.Image | None
    validate_url(url)              -> bool
    validate_pdf_file(file_path)   -> bool

Changes from original:
  - Removed PDFDownloaderApp class and all Tkinter UI code (ttk, messagebox,
    filedialog, Listbox, etc.) — UI lives entirely in pact.py.
  - Removed DownloadThread — pact.py manages its own ThreadPoolExecutor.
  - Removed get_pdf_metadata / display_metadata — not used by pact.py.
  - preview_pdf now returns a PIL.Image.Image instead of ImageTk.PhotoImage.
    Converting to ImageTk must happen on the main thread; pact.py does this
    in _update_preview_image which already runs via root.after(0, ...).
  - validate_pdf_file upgraded from PyPDF2 (deprecated) to pypdf.
  - Module-level imports only — no imports inside functions except pdf2image
    (which is optional and has its own install message).
  - retry logic added to search_pdfs with MAX_RETRIES from config.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
from urllib.parse import urlparse

import requests

from config import (
    MAX_FILE_SIZE,
    MAX_RETRIES,
    SERPAPI_KEY,
    TIMEOUT,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    filename="app.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ---------------------------------------------------------------------------
# Optional heavy dependencies — detected once at import time
# ---------------------------------------------------------------------------

try:
    # pyrefly: ignore [missing-import]
    from pypdf import PdfReader as _PdfReader
    _PYPDF_AVAILABLE = True
except ImportError:
    try:
        # Fallback: PyPDF2 still works if pypdf not installed
        from PyPDF2 import PdfReader as _PdfReader  # type: ignore[no-redef]
        _PYPDF_AVAILABLE = True
    except ImportError:
        _PYPDF_AVAILABLE = False
        logging.warning("Neither pypdf nor PyPDF2 is installed — PDF validation disabled.")

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logging.warning("Pillow not installed — PDF preview disabled.")

# pdf2image is checked lazily in preview_pdf (optional, needs poppler)

# ---------------------------------------------------------------------------
# Blocked domains for search results
# ---------------------------------------------------------------------------

_BLOCKED_DOMAINS = frozenset([
    "pdfdrive.com",
    "pdfroom.com",
    "epdf.tips",
    "yumpu.com",
    "docplayer.net",
    "scribd.com",
])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_pdfs(query: str, max_results: int = 50) -> list[str]:
    """Search for PDFs via SerpApi and return a list of URLs.

    Args:
        query:       Search term (the filetype:pdf suffix is added automatically).
        max_results: Cap on the number of URLs returned.

    Returns:
        List of PDF URLs, deduplicated and filtered.  Empty list on error.
    """
    if not SERPAPI_KEY:
        raise ValueError("SERPAPI_KEY environment variable is not set. Please set it in your .env file.")

    all_pdf_links: list[str] = []
    num_per_page = 20
    pages_to_fetch = (max_results + num_per_page - 1) // num_per_page

    for page in range(pages_to_fetch):
        start = page * num_per_page
        params = {
            "q": f"{query} filetype:pdf",
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": num_per_page,
            "start": start,
            "output": "json",
        }

        response = _get_with_retry("https://serpapi.com/search", params=params)
        if response is None:
            break

        results = response.json()
        organic_results = results.get("organic_results", [])

        for result in organic_results:
            link = result.get("link")
            if not link:
                continue

            lowered = link.lower()

            looks_like_pdf = (
                lowered.endswith(".pdf")
                or ".pdf?" in lowered
                or ".pdf#" in lowered
                or result.get("file_type", "").lower() == "pdf"
            )
            if not looks_like_pdf:
                continue

            if any(blocked in lowered for blocked in _BLOCKED_DOMAINS):
                continue

            if link in all_pdf_links:
                continue

            all_pdf_links.append(link)
            if len(all_pdf_links) >= max_results:
                break

        if len(all_pdf_links) >= max_results:
            break

        # SerpApi total_results is unreliable — stop when page is empty
        if not organic_results:
            break

    return all_pdf_links[:max_results]


def preview_pdf(url: str):
    """Fetch the first page of a remote PDF and return it as a PIL Image.

    Returns:
        PIL.Image.Image on success, None on failure.

    Note:
        Returns PIL.Image, NOT ImageTk.PhotoImage.  The caller (pact.py's
        _update_preview_image) must convert to ImageTk on the main thread.
        Creating ImageTk objects off the main thread crashes Tkinter on most
        platforms.
    """
    if not _PIL_AVAILABLE:
        logging.error("preview_pdf: Pillow not installed.")
        return None

    try:
        from pdf2image import convert_from_bytes  # optional — needs poppler
    except ImportError:
        logging.error(
            "preview_pdf: pdf2image not installed. "
            "Run: pip install pdf2image  (also requires poppler on your PATH)"
        )
        return None

    try:
        response = _get_with_retry(url)
        if response is None:
            return None

        pages = convert_from_bytes(response.content, first_page=1, last_page=1)
        if not pages:
            return None

        return pages[0]  # PIL.Image.Image

    except Exception as exc:
        logging.error(f"preview_pdf error: {exc}")
        return None


def validate_url(url: str) -> bool:
    """Return True if *url* is a well-formed http/https URL."""
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc) and parsed.scheme in ("http", "https")
    except Exception:
        return False


def validate_pdf_file(file_path: str) -> bool:
    """Return True if the file at *file_path* is a readable PDF.

    Uses pypdf (or PyPDF2 as fallback).  If neither is installed, logs a
    warning and returns True so downloads aren't silently discarded.
    """
    if not _PYPDF_AVAILABLE:
        logging.warning("validate_pdf_file: no PDF library installed — skipping validation.")
        return True

    try:
        with open(file_path, "rb") as fh:
            reader = _PdfReader(fh)
            return len(reader.pages) > 0
    except Exception as exc:
        logging.error(f"validate_pdf_file: {exc}")
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def clean_filename(filename: str) -> str:
    """Strip characters that are illegal in file names on Windows/macOS/Linux."""
    return re.sub(r'[\\/:*?"<>|]', "_", filename)


def _get_with_retry(
    url: str,
    params: dict | None = None,
    retries: int = MAX_RETRIES,
) -> requests.Response | None:
    """GET *url* with exponential back-off on transient failures.

    Returns the Response on success, None if all retries are exhausted.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    }
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            # 4xx errors won't be fixed by retrying
            if exc.response is not None and exc.response.status_code < 500:
                logging.error(f"_get_with_retry: non-retryable HTTP {exc.response.status_code} for {url}")
                return None
            logging.warning(f"_get_with_retry: attempt {attempt + 1} failed ({exc})")
        except requests.exceptions.RequestException as exc:
            logging.warning(f"_get_with_retry: attempt {attempt + 1} failed ({exc})")

        if attempt < retries - 1:
            time.sleep(2 ** attempt)  # 1s, 2s, 4s …

    logging.error(f"_get_with_retry: all {retries} attempts failed for {url}")
    return None