#!/usr/bin/env python3
"""
Researcher Knowledge Base Pipeline
===================================
Builds a researcher-centric knowledge base by enriching author profiles
from OpenAlex and Semantic Scholar APIs.


Usage
-----
   python pipeline.py                 # Run all stages
   python pipeline.py --stage 1       # Run only Stage 1
   python pipeline.py --stage 3a      # Run only Stage 3a
   python pipeline.py --force          # Force re-fetch (ignore cache)
   python pipeline.py --limit 10      # Process only 10 authors (quick test)
   python pipeline.py --stage 3 --force  # Re-run all of Stage 3


Stages
------
 1   Discover papers (OpenAlex /works)
 2   Extract & deduplicate authors
 3a  Enrich author profiles (OpenAlex + Semantic Scholar)
 3b  Co-author / mentee analysis
 3c  Institution enrichment
 4   Assemble knowledge_base.json + summary Excel
"""


import argparse
import logging
import os
import sys
import time
from math import ceil
from queue import Queue
from threading import Event, Lock, Thread


from config import CONCEPTS, KNOWLEDGE_BASE_FILE, OPENALEX_BASE, ensure_dirs
from db import fetch_existing_researcher_ids, get_connection, insert_coauthor_edges_for_papers
from utils import load_json


import stage1_discover
import stage2_extract
import stage3_enrich
import stage4_assemble


def _configure_logging():
    """
    Send all log output to stdout so Cloud Run captures it in Cloud Logging.
    Format is human-readable but structured enough for the log viewer.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,  # override any root handlers set by imported modules
    )


def _drop_region_mismatch_after_stage3a(author_map, region):
    if not author_map:
        return {}, 0

    normalized_region = region.strip().lower()
    kept = {}
    dropped = 0
    for author_id, entry in author_map.items():
        profile = load_json(os.path.join(stage3_enrich.PROFILES_DIR, f"{author_id}.json")) or {}
        oa = profile.get("openalex") or {}
        institutions = oa.get("last_known_institutions") or []
        matches = False
        for inst in institutions:
            cc = (inst.get("country_code") or "").lower()
            reg = (inst.get("region") or "").lower()
            if cc == normalized_region or reg == normalized_region:
                matches = True
                break
        if matches:
            kept[author_id] = entry
        else:
            dropped += 1
            print(
                f"[Incremental] Dropping researcher after Stage 3a due to region mismatch: {author_id}"
            )
    return kept, dropped


def _build_stage1_filter_and_search(args, concept_id):
    filter_parts = []
    search_term = args.query.strip() if args.query and args.query.strip() else None
    if not search_term:
        if concept_id.startswith("T"):
            filter_parts.append(f"primary_topic.id:{concept_id}")
        else:
            filter_parts.append(f"concept.id:{concept_id}")
    if args.region and args.region.strip():
        filter_parts.append(
            f"authorships.institutions.country_code:{args.region.strip().upper()}"
        )
    if args.start_year is not None and args.end_year is not None:
        filter_parts.append(f"publication_year:>={args.start_year}")
        filter_parts.append(f"publication_year:<={args.end_year}")
    elif args.start_year is not None:
        filter_parts.append(f"publication_year:>={args.start_year}")
    elif args.end_year is not None:
        filter_parts.append(f"publication_year:<={args.end_year}")
    if args.start_date is not None:
        filter_parts.append(f"from_publication_date:{args.start_date}")
    if args.end_date is not None:
        filter_parts.append(f"to_publication_date:{args.end_date}")
    return ",".join(filter_parts), search_term


def _estimate_total_papers(args):
    total = 0
    for concept in CONCEPTS:
        filter_str, search_term = _build_stage1_filter_and_search(args, concept["id"])
        params = {"per_page": 1, "cursor": "*"}
        if filter_str:
            params["filter"] = filter_str
        if search_term:
            params["search"] = search_term
        try:
            data = stage1_discover.openalex_get(f"{OPENALEX_BASE}/works", params=params)
            total += data.get("meta", {}).get("count", 0) or 0
        except Exception as e:
            print(f"[Progress] Unable to estimate paper count for {concept['label']}: {e}")
    return total


def _run_incremental_all(args):
    pending_author_map: dict[str, dict] = {}
    pending_order: list[str] = []
    seen_in_run: set[str] = set()
    batch_size = 200
    effective_per_page = 100
    limit_cushion = 5 if args.limit is not None and args.limit >= 20 else 0
    target_new_candidates = (
        (args.limit + limit_cushion) if args.limit is not None else None
    )
    stop_fetch_logged = False
    paper_total = _estimate_total_papers(args)
    page_total = ceil(paper_total / effective_per_page) if paper_total else 0
    print(f"[Progress] Total OpenAlex paper count estimate: {paper_total}")
    print(f"[Progress] Estimated total pages at {effective_per_page}/page: {page_total}")

    q_3a = Queue(maxsize=2)
    q_3b = Queue(maxsize=2)
    q_3c = Queue(maxsize=2)
    q_4 = Queue(maxsize=2)
    sentinel = object()

    state_lock = Lock()
    stop_event = Event()
    errors = []
    batch_id_counter = 0
    counters = {
        "papers_seen": 0,
        "researcher_ids_found": 0,
        "skipped_existing": 0,
        "coauthor_edges_inserted": 0,
        "cumulative_inserted": 0,
        "cumulative_dropped": 0,
    }

    def log_queue_sizes():
        print(
            f"[Progress] Queue sizes: q_s1_3a={q_3a.qsize()} q_3a_3b={q_3b.qsize()} "
            f"q_3b_3c={q_3c.qsize()} q_3c_4={q_4.qsize()}"
        )

    if args.limit is not None:
        if limit_cushion > 0:
            print(
                f"[Incremental] Using limit target={args.limit} with cushion={limit_cushion} "
                f"(collect up to {target_new_candidates} new candidates before stopping fetch)"
            )
        else:
            print(
                f"[Incremental] Using limit target={args.limit} "
                "(stop fetching as soon as enough new candidates are collected)"
            )

    if args.works_per_page not in (None, 100):
        print(
            f"[Incremental] Overriding works_per_page={args.works_per_page} to 100 "
            "to keep stable cursor-page behavior"
        )

    def worker_3a():
        while True:
            item = q_3a.get()
            if item is sentinel:
                q_3a.task_done()
                q_3b.put(sentinel)
                break
            try:
                batch_id = item["batch_id"]
                author_map = item["author_map"]
                print(
                    f"[Progress] Batch {batch_id} entering Stage 3a with {len(author_map)} researchers"
                )
                stage3_enrich.run_3a(force=args.force, author_map_override=author_map)
                dropped = 0
                if args.region:
                    author_map, dropped = _drop_region_mismatch_after_stage3a(
                        author_map, args.region
                    )
                with state_lock:
                    counters["cumulative_dropped"] += dropped
                print(
                    f"[Progress] Batch {batch_id} exiting Stage 3a with {len(author_map)} researchers retained"
                )
                item["author_map"] = author_map
                q_3b.put(item)
                log_queue_sizes()
            except Exception as e:
                errors.append(e)
                stop_event.set()
                q_3b.put(sentinel)
                break
            finally:
                q_3a.task_done()

    def worker_3b():
        while True:
            item = q_3b.get()
            if item is sentinel:
                q_3b.task_done()
                q_3c.put(sentinel)
                break
            try:
                batch_id = item["batch_id"]
                print(
                    f"[Progress] Batch {batch_id} entering Stage 3b with {len(item['author_map'])} researchers"
                )
                stage3_enrich.run_3b(
                    force=args.force, author_map_override=item["author_map"]
                )
                q_3c.put(item)
                log_queue_sizes()
            except Exception as e:
                errors.append(e)
                stop_event.set()
                q_3c.put(sentinel)
                break
            finally:
                q_3b.task_done()

    def worker_3c():
        while True:
            item = q_3c.get()
            if item is sentinel:
                q_3c.task_done()
                q_4.put(sentinel)
                break
            try:
                batch_id = item["batch_id"]
                print(
                    f"[Progress] Batch {batch_id} entering Stage 3c with {len(item['author_map'])} researchers"
                )
                stage3_enrich.run_3c(
                    force=args.force, author_map_override=item["author_map"]
                )
                q_4.put(item)
                log_queue_sizes()
            except Exception as e:
                errors.append(e)
                stop_event.set()
                q_4.put(sentinel)
                break
            finally:
                q_3c.task_done()

    def worker_4():
        while True:
            item = q_4.get()
            if item is sentinel:
                q_4.task_done()
                break
            try:
                batch_id = item["batch_id"]
                print(
                    f"[Progress] Batch {batch_id} entering Stage 4 with {len(item['author_map'])} researchers"
                )
                result = stage4_assemble.run(
                    force=args.force,
                    region=args.region,
                    author_map_override=item["author_map"],
                    export_artifacts=bool(getattr(args, "export_artifacts", False)),
                )
                inserted = (result or {}).get("inserted_researchers", 0)
                with state_lock:
                    counters["cumulative_inserted"] += inserted
                    cumulative_inserted = counters["cumulative_inserted"]
                    cumulative_dropped = counters["cumulative_dropped"]
                    cumulative_skipped = counters["skipped_existing"]
                print(
                    f"[Progress] Batch {batch_id} written: inserted={inserted}, "
                    f"cumulative_inserted={cumulative_inserted}, "
                    f"cumulative_dropped={cumulative_dropped}, "
                    f"cumulative_skipped_existing={cumulative_skipped}"
                )
                log_queue_sizes()
            except Exception as e:
                errors.append(e)
                stop_event.set()
                break
            finally:
                q_4.task_done()

    workers = [
        Thread(target=worker_3a, name="stage3a-worker", daemon=True),
        Thread(target=worker_3b, name="stage3b-worker", daemon=True),
        Thread(target=worker_3c, name="stage3c-worker", daemon=True),
        Thread(target=worker_4, name="stage4-worker", daemon=True),
    ]
    print("[Progress] Starting staged workers: one worker each for 3a/3b/3c/4")
    for w in workers:
        w.start()

    conn = get_connection()
    cursor = conn.cursor()

    def should_stop_fetch():
        nonlocal stop_fetch_logged
        if stop_event.is_set():
            return True
        if target_new_candidates is None:
            return False
        reached = len(seen_in_run) >= target_new_candidates
        if reached and not stop_fetch_logged:
            print("[Incremental] Researcher limit reached during page fetch, stopping early")
            stop_fetch_logged = True
        return reached

    def on_page_fetched(concept_id, concept_label, page_num, papers):
        nonlocal pending_author_map, pending_order, seen_in_run, batch_id_counter
        print(f"[Incremental] Fetched page {page_num} with {len(papers)} papers")
        inserted_edges = insert_coauthor_edges_for_papers(cursor, papers)
        if inserted_edges:
            conn.commit()
        with state_lock:
            counters["coauthor_edges_inserted"] += inserted_edges
            counters["papers_seen"] += len(papers)
            papers_seen = counters["papers_seen"]
            edges_total = counters["coauthor_edges_inserted"]
        print(f"[Progress] Papers seen: {papers_seen} / {paper_total or 'unknown'}")
        page_ids = stage2_extract._extract_author_ids_from_papers(papers)
        print(f"[Incremental] Found {len(page_ids)} researcher IDs on this page")
        with state_lock:
            counters["researcher_ids_found"] += len(page_ids)
        if not page_ids:
            return

        existing_ids = fetch_existing_researcher_ids(cursor, list(page_ids))
        print(f"[Incremental] Skipped {len(existing_ids)} researchers already in DB")
        with state_lock:
            counters["skipped_existing"] += len(existing_ids)

        fresh_ids = [
            rid for rid in sorted(page_ids) if rid not in existing_ids and rid not in seen_in_run
        ]

        if target_new_candidates is not None:
            remaining = max(target_new_candidates - len(seen_in_run), 0)
            fresh_ids = fresh_ids[:remaining]

        for rid in fresh_ids:
            seen_in_run.add(rid)
            pending_order.append(rid)
        print(
            f"[Incremental] Pending new researchers collected: {len(seen_in_run)}"
        )
        print(
            f"[Progress] Cumulative IDs found={counters['researcher_ids_found']} "
            f"skipped_existing={counters['skipped_existing']} "
            f"coauthor_edges_inserted={edges_total}"
        )

        active_pending_ids = set(pending_order)
        if active_pending_ids:
            stage2_extract._process_papers(
                papers,
                concept_label,
                pending_author_map,
                allowed_author_ids=active_pending_ids,
            )

        while len(pending_order) >= batch_size:
            batch_ids = pending_order[:batch_size]
            pending_order = pending_order[batch_size:]
            batch_map = {}
            for rid in batch_ids:
                if rid in pending_author_map:
                    batch_map[rid] = pending_author_map.pop(rid)
            if batch_map:
                batch_id_counter += 1
                finalized_batch = stage2_extract._finalize_author_map(batch_map)
                q_3a.put({"batch_id": batch_id_counter, "author_map": finalized_batch})
                print(
                    f"[Progress] Batch {batch_id_counter} queued from Stage 1 with "
                    f"{len(finalized_batch)} researchers"
                )
                log_queue_sizes()

    try:
        for concept in CONCEPTS:
            if should_stop_fetch():
                break
            stage1_discover._discover_concept(
                concept["id"],
                concept["label"],
                papers_file=stage1_discover.papers_file_for(concept["label"]),
                force=args.force,
                start_year=args.start_year,
                end_year=args.end_year,
                start_date=args.start_date,
                end_date=args.end_date,
                no_limit=args.no_limit,
                works_per_page=effective_per_page,
                author_map=None,
                researcher_limit=None,
                query=args.query,
                region=args.region,
                on_page_fetched=on_page_fetched,
                should_stop_fetch=should_stop_fetch,
            )

        if pending_order:
            batch_map = {}
            for rid in list(pending_order):
                if rid in pending_author_map:
                    batch_map[rid] = pending_author_map.pop(rid)
            pending_order = []
            if batch_map:
                batch_id_counter += 1
                finalized_batch = stage2_extract._finalize_author_map(batch_map)
                q_3a.put({"batch_id": batch_id_counter, "author_map": finalized_batch})
                print(
                    f"[Progress] Batch {batch_id_counter} queued from Stage 1 with "
                    f"{len(finalized_batch)} researchers"
                )
                log_queue_sizes()
        q_3a.put(sentinel)
        q_3a.join()
        q_3b.join()
        q_3c.join()
        q_4.join()
        for w in workers:
            w.join(timeout=1)
        if errors:
            raise errors[0]
    finally:
        conn.close()


def main():

    parser = argparse.ArgumentParser(
        description="Researcher Knowledge Base Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--stage",
        type=str,
        default="all",
        choices=["all", "1", "2", "3", "3a", "3b", "3c", "4"],
        help="Which stage to run (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-fetch, ignoring cached / recent data",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of authors to process (for quick testing)",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="Earliest publication year to fetch from OpenAlex (Stage 1)",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Latest publication year to fetch from OpenAlex (Stage 1)",
    )
    parser.add_argument(
        "--no-limit",
        action="store_true",
        help="Fetch all OpenAlex pages (Stage 1, disables MAX_WORKS_PAGES)",
    )
    parser.add_argument(
        "--works-per-page",
        type=int,
        default=None,
        help="Number of works per OpenAlex page (max 200)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Earliest publication date to fetch from OpenAlex (Stage 1, e.g. 2023-01-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Latest publication date to fetch from OpenAlex (Stage 1, e.g. 2023-12-31)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Optional institution country or region filter for Stage 4 output",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Optional OpenAlex keyword/text search term for Stage 1 retrieval",
    )
    parser.add_argument(
        "--export-artifacts",
        action="store_true",
        help="In incremental all-stage runs, export JSON/Excel/schema artifacts in Stage 4",
    )

    args = parser.parse_args()
    _configure_logging()
    ensure_dirs()

    env_limit = os.environ.get("LIMIT")
    if env_limit is not None:
        env_limit_normalized = env_limit.strip().lower()
        if env_limit_normalized == "all":
            args.limit = None
            limit = "all"
        else:
            try:
                args.limit = int(env_limit_normalized)
                limit = args.limit
            except ValueError as exc:
                raise ValueError("LIMIT must be an integer or 'all'") from exc
    else:
        limit = args.limit if args.limit is not None else "all"

    print(f"[Config] LIMIT={limit}")

    # Validation
    if args.works_per_page is not None and args.works_per_page > 200:
        raise ValueError("--works-per-page cannot exceed 200 (OpenAlex API limit)")
    if args.start_year is not None and args.end_year is not None:
        if args.start_year > args.end_year:
            raise ValueError("--start-year must be <= --end-year")
    # Validate date args using the same regex as stage1_discover
    import re

    _DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")
    for arg_name, arg_val in (
        ("--start-date", args.start_date),
        ("--end-date", args.end_date),
    ):
        if arg_val is not None and not _DATE_RE.match(arg_val):
            raise ValueError(
                f"{arg_name} '{arg_val}': expected YYYY-MM-DD (e.g. 2023-01-31)"
            )
    if args.start_date is not None and args.end_date is not None:
        if args.start_date > args.end_date:
            raise ValueError("--start-date must be <= --end-date")

    limit_label = str(args.limit) if args.limit is not None else "all"
    concepts_str = ", ".join(c["label"] for c in CONCEPTS)
    print("=" * 60)
    print("  Researcher Knowledge Base Pipeline")
    print(f"  Concepts: {concepts_str}")
    print(f"  Force   : {args.force}")
    print(f"  Limit   : {limit_label}")
    print(f"  Region  : {args.region or 'all'}")
    if args.query:
        print(f"  Query   : {args.query}")
    print("=" * 60)
    if args.query:
        print(
            "[Config] Retrieval mode: query (topic-ID filters in config are ignored for this run)"
        )
    else:
        print("[Config] Retrieval mode: topic")
    if args.start_date is not None or args.end_date is not None:
        print(
            f"[Config] Applying date range: start_date={args.start_date or 'none'}, "
            f"end_date={args.end_date or 'none'}"
        )
    elif args.start_year is not None or args.end_year is not None:
        print(
            f"[Config] Applying year range: start_year={args.start_year or 'none'}, "
            f"end_year={args.end_year or 'none'}"
        )
    if args.region:
        print(f"[Config] Applying region filter: {args.region}")
    if args.stage == "all":
        print(
            "[Config] Stage 4 artifacts in incremental mode: "
            f"{'enabled' if args.export_artifacts else 'disabled'}"
        )

    start = time.time()

    limit_kwargs = {"limit": args.limit} if args.limit else {}

    if args.stage == "all":
        _run_incremental_all(args)
        elapsed = time.time() - start
        print(f"\nPipeline finished in {elapsed:.1f}s")
        print(f"Knowledge base: {KNOWLEDGE_BASE_FILE}")
        return

    # Stage 1 -- discovers papers (limit not applicable here)
    if args.stage in ("1",):
        stage1_discover.run(
            force=args.force,
            start_year=args.start_year,
            end_year=args.end_year,
            start_date=args.start_date,
            end_date=args.end_date,
            no_limit=args.no_limit,
            works_per_page=args.works_per_page,
            limit=args.limit,
            query=args.query,
            region=args.region,
        )

    # Stage 2
    if args.stage in ("2",):
        stage2_extract.run(force=args.force, **limit_kwargs)

    # Stage 3a
    if args.stage in ("3", "3a"):
        stage3_enrich.run_3a(force=args.force, **limit_kwargs)

    # Stage 3b
    if args.stage in ("3", "3b"):
        stage3_enrich.run_3b(force=args.force, **limit_kwargs)

    # Stage 3c
    if args.stage in ("3", "3c"):
        stage3_enrich.run_3c(force=args.force, **limit_kwargs)

    # Stage 4
    if args.stage in ("4",):
        stage4_assemble.run(force=args.force, region=args.region, **limit_kwargs)

    elapsed = time.time() - start
    print(f"\nPipeline finished in {elapsed:.1f}s")

    if args.stage in ("4",):
        print(f"Knowledge base: {KNOWLEDGE_BASE_FILE}")


if __name__ == "__main__":
    main()
