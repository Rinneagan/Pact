"""
Related documents functionality for Pact PDF application.
Uses token-overlap matching to find similar documents by filename.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Optional


# ---------------------------------------------------------------------------
# Stopwords for token filtering
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "your",
    "a", "an", "of", "to", "in", "on", "is", "are", "by", "or", "at",
    "report", "document", "final", "draft", "copy", "new", "untitled",
}


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

def _tokenize_name(text: str) -> set[str]:
    """Extract meaningful tokens from a filename."""
    tokens = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


# ---------------------------------------------------------------------------
# Related documents discovery
# ---------------------------------------------------------------------------

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
