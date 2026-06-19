"""Backfill citation counts for specific researchers' papers.

Usage: set DB env vars and run:
  python scripts/backfill_citations.py A5087556046 A5027798962 A5110776230

This script is conservative: it only updates existing `papers` rows and
writes `paper_citations_by_year` entries when OpenAlex provides `counts_by_year`.
It will not insert new paper rows.
"""
import sys
import logging
from typing import List

from db import get_connection, upsert_paper_citations_by_year
from utils import openalex_get, safe_paper_id
from config import OPENALEX_BASE

logging.basicConfig(level=logging.INFO)


def fetch_works_for_author(author_id: str) -> List[dict]:
    works = []
    cursor = "*"
    while True:
        data = openalex_get(
            f"{OPENALEX_BASE}/works",
            params={
                "filter": f"author.id:{author_id}",
                "per_page": 200,
                "cursor": cursor,
                "sort": "cited_by_count:desc",
            },
        )
        batch = data.get("results") or []
        works.extend(batch)
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
    return works


def backfill_for_researcher(author_id: str):
    logging.info("Backfilling citations for researcher %s", author_id)
    works = fetch_works_for_author(author_id)
    logging.info("Found %s works for %s", len(works), author_id)
    conn = get_connection()
    cur = conn.cursor()
    updated = 0
    try:
        for w in works:
            paper = {
                "doi": w.get("doi"),
                "title": w.get("title"),
                "year": w.get("publication_year"),
                "venue": (w.get("primary_location") or {}).get("source", {}).get("display_name"),
            }
            paper_id = safe_paper_id(author_id, paper)
            cited_by = int(w.get("cited_by_count") or 0)
            counts_by_year = w.get("counts_by_year") or []

            # Update lifetime citations if the paper row exists
            cur.execute(
                "SELECT id FROM papers WHERE id = %s OR embedding_id = %s LIMIT 1",
                (paper_id, paper_id),
            )
            row = cur.fetchone()
            if not row:
                logging.debug("Paper row not found for %s — skipping update", paper_id)
                continue

            cur.execute(
                "UPDATE papers SET citations = %s WHERE id = %s OR embedding_id = %s",
                (cited_by, paper_id, paper_id),
            )
            if counts_by_year:
                try:
                    upsert_paper_citations_by_year(cur, paper_id, counts_by_year)
                except Exception as e:
                    logging.warning("Failed to upsert per-year counts for %s: %s", paper_id, e)
            updated += 1

        conn.commit()
        logging.info("Updated %s existing paper rows for %s", updated, author_id)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def main(args):
    if not args:
        print("Usage: python scripts/backfill_citations.py <author_id> [<author_id> ...]")
        return
    for aid in args:
        backfill_for_researcher(aid)


if __name__ == "__main__":
    main(sys.argv[1:])
