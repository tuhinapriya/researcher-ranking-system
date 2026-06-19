"""Utility helpers for stable, ASCII-safe identifier generation."""

import hashlib
import logging
import re
import unicodedata
from typing import Optional


def stable_hash(text: str, length: int = 12) -> str:
    if text is None:
        text = ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-]")


def sanitize_identifier(value: str, fallback_prefix: Optional[str] = None) -> str:
    """Return an ASCII-only identifier by removing/normalizing characters.

    Rules:
    - Normalize Unicode (NFKD), strip diacritics
    - Remove any character not in A-Za-z0-9_- (replace with empty string)
    - If result is empty, return fallback_prefix + stable_hash(value)
    - Log original and sanitized values at DEBUG level
    """
    if value is None:
        value = ""
    orig = str(value)
    # Normalize and remove diacritics
    normalized = unicodedata.normalize("NFKD", orig)
    # Remove combining marks
    normalized = "".join(
        ch for ch in normalized if not unicodedata.category(ch).startswith("M")
    )
    # Encode-ascii by ignoring non-ascii then filter allowed chars
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    sanitized = _SAFE_RE.sub("", ascii_only)
    if not sanitized:
        # Fallback to stable hashed id
        prefix = (fallback_prefix + "_") if fallback_prefix else "id_"
        sanitized = f"{prefix}{stable_hash(orig)}"
    if sanitized != orig:
        logging.debug("sanitize_identifier: original=%r sanitized=%r", orig, sanitized)
    return sanitized


def safe_paper_id(researcher_id: str, paper: dict) -> str:
    """Return a stable ASCII-safe paper id.

    Prefer DOI when available (cleaned and sanitized). Otherwise use a hash
    of stable paper attributes to produce reproducible id: <researcher>_<hash>.
    """
    doi = (paper.get("doi") or "") if paper else ""
    if doi:
        doi_clean = doi.replace("https://doi.org/", "")
        return sanitize_identifier(doi_clean, fallback_prefix=researcher_id)

    title = (paper.get("title") or "") if paper else ""
    year = str(paper.get("year") or "") if paper else ""
    venue = (paper.get("venue") or "") if paper else ""
    source = "||".join([title, year, venue])
    hashed = stable_hash(source)
    return sanitize_identifier(
        f"{researcher_id}_{hashed}", fallback_prefix=researcher_id
    )


def safe_embedding_id(researcher_id: str, paper_id: str) -> str:
    """Return a stable embedding id derived from the paper id.

    Guarantees ASCII hex characters and keeps mapping traceable.
    """
    base = f"{researcher_id}_{stable_hash(paper_id)}"
    return sanitize_identifier(base, fallback_prefix=researcher_id)


def is_ascii_safe_identifier(identifier: str) -> bool:
    """Allow only ASCII alphanumeric, dash, and underscore in IDs."""
    if not identifier:
        return False
    # must be ascii and match allowed set
    try:
        identifier.encode("ascii")
    except Exception:
        return False
    return re.fullmatch(r"[A-Za-z0-9_\-]+", identifier) is not None


def validate_and_filter_vectors(vectors: list) -> tuple[list, list]:
    """Validate vector IDs; return (valid_vectors, invalid_ids).

    This keeps invalid vectors from being sent to Pinecone and provides
    a list of rejected ids for logging. Filtering is aggressive: any id
    not matching the allowed charset is rejected.
    """
    valid = []
    invalid = []
    for v in vectors:
        vid = v.get("id")
        if vid and is_ascii_safe_identifier(vid):
            valid.append(v)
        else:
            invalid.append(vid)
    return valid, invalid


"""
Shared utility functions for the pipeline.
API helpers, abstract reconstruction, caching, JSON I/O.
"""

import json
import os
import time
from datetime import datetime, timedelta
from urllib.parse import quote


import requests


from config import HEADERS, OPENALEX_SLEEP, S2_BASE, S2_SLEEP, STALENESS_DAYS

# ============================================================
# API Helpers
# ============================================================


def openalex_get(url, params=None, timeout=30):
    """GET request to OpenAlex with polite-pool rate limiting."""
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    time.sleep(OPENALEX_SLEEP)
    return r.json()


def s2_get(url, params=None, timeout=20):
    """GET request to Semantic Scholar with rate limiting.
    Returns JSON dict on success, None on any error.
    """
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        time.sleep(S2_SLEEP)
        if r.status_code == 200:
            return r.json()
        return None
    except requests.RequestException:
        return None


# ============================================================
# Abstract Reconstruction
# ============================================================


def reconstruct_abstract(abstract_inverted_index):
    """
    OpenAlex stores abstracts as an inverted index.
    Reconstruct the full text.  Returns None if missing.
    """
    if not abstract_inverted_index:
        return None

    position_to_word = {}
    for word, positions in abstract_inverted_index.items():
        for pos in positions:
            position_to_word[pos] = word

    if not position_to_word:
        return None

    max_pos = max(position_to_word.keys())
    words = [position_to_word.get(i, "") for i in range(max_pos + 1)]
    text = " ".join(w for w in words if w).strip()
    return text if text else None


def fetch_s2_abstract(doi=None, title=None, timeout=None):
    """
    Try Semantic Scholar for an abstract.
    1) DOI lookup  (best match)
    2) Title search  (fallback)
    """
    if doi:
        doi_clean = doi.replace("https://doi.org/", "").strip()
        url = f"{S2_BASE}/paper/DOI:{quote(doi_clean)}"
        data = s2_get(
            url, params={"fields": "title,abstract,year"}, timeout=timeout or 20
        )
        if data:
            return data.get("abstract")

    if title:
        url = f"{S2_BASE}/paper/search"
        data = s2_get(
            url,
            params={"query": title, "limit": 1, "fields": "title,abstract,year"},
            timeout=timeout or 20,
        )
        if data:
            hits = data.get("data", [])
            if hits:
                return hits[0].get("abstract")

    return None


# ============================================================
# Institution Helpers
# ============================================================


def is_education_inst(inst):
    """Check if an OpenAlex institution object is type 'education'."""
    if not inst:
        return False
    return (inst.get("type") or "").lower() == "education"


# ============================================================
# ID Extraction
# ============================================================


def extract_id(openalex_url):
    """
    Extract the short ID from an OpenAlex URL.
    e.g. 'https://openalex.org/A5023888391' -> 'A5023888391'
    """
    if not openalex_url:
        return None
    return openalex_url.split("/")[-1]


# convenience aliases
extract_author_id = extract_id
extract_institution_id = extract_id


# ============================================================
# Caching & I/O
# ============================================================


def is_stale(filepath, staleness_days=None):
    """Return True if file doesn't exist or is older than staleness window."""
    if staleness_days is None:
        staleness_days = STALENESS_DAYS
    if not os.path.exists(filepath):
        return True
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    return datetime.now() - mtime > timedelta(days=staleness_days)


def save_json(data, filepath):
    """Write *data* as pretty-printed JSON."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(filepath):
    """Load a JSON file.  Returns None if the file doesn't exist."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
