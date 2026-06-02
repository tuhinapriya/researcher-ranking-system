"""
Backfill paper_citations_by_year from the OpenAlex works API.

Reads all DOI-style paper IDs from the MySQL `papers` table that do not yet
have any rows in `paper_citations_by_year`, fetches counts_by_year from
OpenAlex in batches of 200, and inserts the results.

OpenAlex returns approximately the 10 most recent years of citation history
per paper.  The script is safe to re-run; it skips papers that already have
data (INSERT ON DUPLICATE KEY UPDATE).

Usage (from the workspace root with Cloud SQL Proxy running):
    cd researcher-kb-pipeline
    DB_HOST=127.0.0.1 DB_USER=... DB_PASSWORD=... DB_NAME=... \
        python ../scripts/backfill_paper_citations_by_year.py

Environment variables (same as the ranking service):
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
    DB_PORT        (default 3306)
    OPENALEX_EMAIL (optional polite-pool address)
    DRY_RUN        (set to "1" to print actions without writing to DB)
"""

import logging
import os
import sys
import time
from urllib.parse import urlencode

import requests

# Allow importing from researcher-kb-pipeline regardless of cwd
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PIPELINE_DIR = os.path.join(_SCRIPT_DIR, "..", "researcher-kb-pipeline")
sys.path.insert(0, _PIPELINE_DIR)

from db import get_connection, upsert_paper_citations_by_year  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
BATCH_SIZE = 50  # Keep URL short enough to avoid 400 errors from OpenAlex
REQUEST_DELAY = 0.12  # seconds between requests (polite pool = 10 req/s)
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"


def _openalex_headers():
    email = os.environ.get("OPENALEX_EMAIL", "")
    if email:
        return {"User-Agent": f"mailto:{email}"}
    return {}


def _fetch_papers_needing_backfill(cursor):
    """
    Return all paper IDs from `papers` that look like DOIs (start with '10.')
    and do not yet have any row in `paper_citations_by_year`.
    Non-DOI IDs (title-based fallback IDs) cannot be queried via OpenAlex and
    are skipped.
    """
    sql = """
        SELECT p.id
        FROM papers p
        LEFT JOIN paper_citations_by_year pcy ON pcy.paper_id = p.id
        WHERE p.id LIKE '10.%'
          AND pcy.paper_id IS NULL
        ORDER BY p.id
    """
    cursor.execute(sql)
    return [row[0] for row in cursor.fetchall()]


def _fetch_counts_by_year_batch(doi_list):
    """
    Query OpenAlex for counts_by_year for a batch of up to 200 DOIs.
    Returns a list of (doi, counts_by_year) tuples for papers found.
    doi values in the result are normalized (no https://doi.org/ prefix).
    """
    filter_str = "|".join(doi_list)
    params = {
        "filter": f"doi:{filter_str}",
        "select": "doi,counts_by_year",
        "per_page": len(doi_list),
    }
    url = f"{OPENALEX_WORKS_URL}?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=_openalex_headers(), timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as exc:
        log.warning("OpenAlex request failed for batch: %s", exc)
        return []

    out = []
    for work in results:
        doi = work.get("doi") or ""
        doi = doi.replace("https://doi.org/", "").strip().lower()
        counts = work.get("counts_by_year") or []
        if doi and counts:
            out.append((doi, counts))
    return out


def run():
    conn = get_connection()
    cursor = conn.cursor()

    log.info("Fetching paper IDs needing backfill …")
    paper_ids = _fetch_papers_needing_backfill(cursor)
    log.info("Found %d papers without yearly citation data.", len(paper_ids))

    if not paper_ids:
        log.info("Nothing to backfill. Exiting.")
        cursor.close()
        conn.close()
        return

    total_papers_updated = 0
    total_rows_written = 0
    batch_count = 0

    for batch_start in range(0, len(paper_ids), BATCH_SIZE):
        batch = paper_ids[batch_start : batch_start + BATCH_SIZE]
        batch_count += 1
        log.info(
            "Batch %d: fetching %d DOIs from OpenAlex (papers %d–%d of %d) …",
            batch_count,
            len(batch),
            batch_start + 1,
            batch_start + len(batch),
            len(paper_ids),
        )

        # OpenAlex DOI filter is case-insensitive; normalise to lowercase
        doi_lookup = {doi.lower(): doi for doi in batch}
        results = _fetch_counts_by_year_batch(list(doi_lookup.keys()))

        for oa_doi, counts_by_year in results:
            # Match back to the exact paper_id stored in MySQL
            original_id = doi_lookup.get(oa_doi) or doi_lookup.get(oa_doi.lower())
            if not original_id:
                log.debug("OpenAlex returned unmatched DOI: %s", oa_doi)
                continue

            if DRY_RUN:
                log.info(
                    "[DRY_RUN] Would write %d rows for %s",
                    len(counts_by_year),
                    original_id,
                )
            else:
                upsert_paper_citations_by_year(cursor, original_id, counts_by_year)
                total_rows_written += len(counts_by_year)

            total_papers_updated += 1

        if not DRY_RUN:
            conn.commit()
            log.info(
                "Batch %d committed. Papers updated this batch: %d",
                batch_count,
                len(results),
            )

        time.sleep(REQUEST_DELAY)

    cursor.close()
    conn.close()

    log.info(
        "Backfill complete. Papers updated: %d / %d. Rows written: %d.",
        total_papers_updated,
        len(paper_ids),
        total_rows_written,
    )
    if total_papers_updated < len(paper_ids):
        skipped = len(paper_ids) - total_papers_updated
        log.info(
            "%d papers were not found in OpenAlex (no counts_by_year available for them).",
            skipped,
        )


if __name__ == "__main__":
    run()
