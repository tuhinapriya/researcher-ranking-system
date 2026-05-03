"""
Stage 1 -- Discover Papers
==========================
Query OpenAlex /works for papers matching each configured concept.
Uses cursor-based pagination.  Saves one papers file per concept
under data/raw/papers/.
"""

import json
import os
import re

from config import (
    CONCEPTS,
    FIELD_AUTHOR_MAP_FILE,
    OPENALEX_BASE,
    WORKS_PER_PAGE,
    ensure_dirs,
    papers_file_for,
)
from stage2_extract import _apply_author_limit, _finalize_author_map, _process_papers
from utils import fetch_s2_abstract, openalex_get, reconstruct_abstract

_DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")


def _validate_date(value: str, param_name: str) -> None:
    """Raise ValueError if *value* is not in YYYY-MM-DD format."""
    if not _DATE_RE.match(value):
        raise ValueError(
            f"Invalid {param_name} '{value}': expected YYYY-MM-DD (e.g. 2023-01-31)"
        )


def _discover_concept(
    concept_id,
    concept_label,
    papers_file,
    force=False,
    start_year=None,
    end_year=None,
    start_date=None,
    end_date=None,
    no_limit=False,
    works_per_page=None,
    author_map=None,
    researcher_limit=None,
    query=None,
    region=None,
    on_page_fetched=None,
    should_stop_fetch=None,
):
    """Fetch papers for a single concept with pagination and year/date filtering."""
    if os.path.exists(papers_file) and not force:
        with open(papers_file, "r") as f:
            count = sum(1 for _ in f)
        print(
            f"  [{concept_label}] Already have {count} papers. "
            "Use --force to re-fetch."
        )
        return
    print(f"  [{concept_label}] Fetching papers for {concept_id} ...")
    works_url = f"{OPENALEX_BASE}/works"
    cursor = "*"
    total_fetched = 0
    page_num = 1
    pages_fetched = 0
    per_page = works_per_page if works_per_page is not None else WORKS_PER_PAGE
    # Validate date params if provided
    if start_date is not None:
        _validate_date(start_date, "start_date")
    if end_date is not None:
        _validate_date(end_date, "end_date")
    # Build filter string
    filter_parts = []
    use_query_mode = bool(query and query.strip())
    if use_query_mode:
        print(
            f"    Using query-based retrieval with search term '{query.strip()}'"
        )
    else:
        if concept_id.startswith("T"):
            topic_filter = f"primary_topic.id:{concept_id}"
        else:
            topic_filter = f"concept.id:{concept_id}"
        filter_parts.append(topic_filter)
        print(f"    Using topic-based retrieval with topic ID {concept_id}")
    if region and region.strip():
        region_code = region.strip().upper()
        filter_parts.append(f"authorships.institutions.country_code:{region_code}")
        print(f"    Applying region filter at Stage 1: {region_code}")
    if start_year is not None and end_year is not None:
        filter_parts.append(f"publication_year:>={start_year}")
        filter_parts.append(f"publication_year:<={end_year}")
    elif start_year is not None:
        filter_parts.append(f"publication_year:>={start_year}")
    elif end_year is not None:
        filter_parts.append(f"publication_year:<={end_year}")
    # Date filters take precedence over year filters when both are provided
    if start_date is not None:
        filter_parts.append(f"from_publication_date:{start_date}")
    if end_date is not None:
        filter_parts.append(f"to_publication_date:{end_date}")
    filter_str = ",".join(filter_parts)
    if filter_str:
        print(f"    Using OpenAlex filter: {filter_str}")
    else:
        print("    Using OpenAlex filter: (none)")
    if start_date is not None or end_date is not None:
        print(
            f"    Applying date range: start_date={start_date or 'none'}, "
            f"end_date={end_date or 'none'}"
        )
    elif start_year is not None or end_year is not None:
        print(
            f"    Applying year range: start_year={start_year or 'none'}, "
            f"end_year={end_year or 'none'}"
        )
    with open(papers_file, "w", encoding="utf-8") as f:
        while True:
            params = {
                "per_page": per_page,
                "sort": "cited_by_count:desc",
                "cursor": cursor,
            }
            if filter_str:
                params["filter"] = filter_str
            if use_query_mode:
                params["search"] = query.strip()
            try:
                data = openalex_get(works_url, params=params)
            except Exception as e:
                print(f"    Error on page {page_num}: {e}")
                break
            if page_num == 1:
                total_count = data.get("meta", {}).get("count", 0)
                print(f"    OpenAlex count for date range: {total_count}")
                print("    Fetching full dataset with cursor paging")
            works = data.get("results", [])
            if not works:
                break
            next_cursor = data.get("meta", {}).get("next_cursor")
            batch_records = []
            for work in works:
                abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
                if not abstract:
                    abstract = fetch_s2_abstract(
                        doi=work.get("doi"), title=work.get("title")
                    )
                record = {
                    "id": work.get("id"),
                    "doi": work.get("doi"),
                    "title": work.get("title"),
                    "publication_year": work.get("publication_year"),
                    "cited_by_count": work.get("cited_by_count"),
                    "abstract": abstract,
                    "authorships": work.get("authorships", []),
                    "primary_topic": work.get("primary_topic"),
                    "topics": work.get("topics", []),
                    "grants": work.get("grants", []),
                    "primary_location": work.get("primary_location"),
                    "type": work.get("type"),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                batch_records.append(record)
                total_fetched += 1
            print(f"    Fetched paper batch {page_num} with {len(batch_records)} papers")
            if on_page_fetched is not None:
                on_page_fetched(
                    concept_id=concept_id,
                    concept_label=concept_label,
                    page_num=page_num,
                    papers=batch_records,
                )
            if should_stop_fetch is not None and should_stop_fetch():
                print(
                    f"    Stopping after page {page_num} because enough new researchers were collected"
                )
                break
            if author_map is not None:
                unique_before = len(author_map)
                _process_papers(batch_records, concept_label, author_map)
                new_unique = len(author_map) - unique_before
                print(f"    Discovered {new_unique} new unique researchers in this batch")
                print(f"    Total unique researchers collected: {len(author_map)}")
            pages_fetched += 1
            print(f"    Processed {page_num} pages / {total_fetched} papers")
            if researcher_limit is not None and author_map is not None:
                if len(author_map) >= researcher_limit:
                    print("    Researcher limit reached, stopping paper fetch early")
                    break
            page_num += 1
            if not next_cursor:
                break
            cursor = next_cursor
    print(
        f"  [{concept_label}] Saved {total_fetched} papers. Pages fetched: {pages_fetched}"
    )


def run(
    force=False,
    start_year=None,
    end_year=None,
    start_date=None,
    end_date=None,
    no_limit=False,
    works_per_page=None,
    limit=None,
    query=None,
    region=None,
    on_page_fetched=None,
    should_stop_fetch=None,
):
    """Discover papers for every concept in CONCEPTS with pagination and year/date filtering."""
    ensure_dirs()
    print(f"[Stage 1] Discovering papers for {len(CONCEPTS)} concept(s) ...")
    author_map = {} if limit is not None else None
    for concept in CONCEPTS:
        cid = concept["id"]
        label = concept["label"]
        papers_file = papers_file_for(label)
        _discover_concept(
            cid,
            label,
            papers_file,
            force=force,
            start_year=start_year,
            end_year=end_year,
            start_date=start_date,
            end_date=end_date,
            no_limit=no_limit,
            works_per_page=works_per_page,
            author_map=author_map,
            researcher_limit=limit,
            query=query,
            region=region,
            on_page_fetched=on_page_fetched,
            should_stop_fetch=should_stop_fetch,
        )
        if limit is not None and len(author_map) >= limit:
            break
    if limit is not None:
        author_map = _finalize_author_map(author_map)
        author_map = _apply_author_limit(author_map, limit)
        from utils import save_json

        save_json(author_map, FIELD_AUTHOR_MAP_FILE)
        print(f"[Stage 1] Saved limited author map to {FIELD_AUTHOR_MAP_FILE}")
    print("[Stage 1] Done.")
