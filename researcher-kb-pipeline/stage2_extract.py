"""
Stage 2 -- Extract & Deduplicate Authors
=========================================
Parse papers from all concepts, build a unified map of unique
education-institution authors.  Each author carries per-concept
field data so the knowledge base can report relevance across
multiple fields.


Saves to data/intermediate/field_author_map.json.
"""

import json
import os
from collections import defaultdict


from config import (
    CONCEPTS,
    FIELD_AUTHOR_MAP_FILE,
    ensure_dirs,
    papers_file_for,
)
from utils import (
    extract_author_id,
    extract_institution_id,
    is_education_inst,
    save_json,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _empty_concept_entry(concept_label):
    """Return an empty per-concept stats dict for an author."""
    return {
        "concept_label": concept_label,
        "papers": [],
        "topic_counts": defaultdict(int),
        "funder_counts": defaultdict(int),
        "venue_counts": defaultdict(int),
        "total_field_citations": 0,
        "first_author_count": 0,
        "last_author_count": 0,
        "corresponding_author_count": 0,
    }


def _extract_author_ids_from_papers(papers):
    """
    Extract unique author IDs from a papers list using the same education-institution
    eligibility as Stage 2 processing.
    """
    ids = set()
    for paper in papers:
        for auth in paper.get("authorships", []):
            author = auth.get("author") or {}
            author_id = extract_author_id(author.get("id"))
            if not author_id:
                continue
            insts = auth.get("institutions") or []
            if not any(is_education_inst(inst) for inst in insts):
                continue
            ids.add(author_id)
    return ids


def _process_papers(papers, concept_label, author_map, allowed_author_ids=None):
    """
    Walk through a list of paper dicts and update *author_map* in place.
    Each author gets a per-concept sub-entry inside author_map[id]["concepts"].
    """
    for paper in papers:
        authorships = paper.get("authorships", [])
        total_authors = len(authorships)

        # Topic info
        primary_topic = paper.get("primary_topic")
        topic_info = None
        if primary_topic:
            topic_info = {
                "topic": primary_topic.get("display_name"),
                "subfield": (primary_topic.get("subfield") or {}).get("display_name"),
                "field": (primary_topic.get("field") or {}).get("display_name"),
                "domain": (primary_topic.get("domain") or {}).get("display_name"),
            }

        # Grant info
        grant_info = [
            {
                "funder": g.get("funder_display_name") or g.get("funder", ""),
                "award_id": g.get("award_id", ""),
            }
            for g in paper.get("grants", [])
        ]

        # Venue
        venue = None
        primary_location = paper.get("primary_location")
        if primary_location:
            source = primary_location.get("source")
            if source:
                venue = source.get("display_name")

        # --- iterate authorships ---
        for idx, auth in enumerate(authorships, start=1):
            author = auth.get("author") or {}
            author_id_url = author.get("id")
            author_id = extract_author_id(author_id_url)
            if not author_id:
                continue
            if allowed_author_ids is not None and author_id not in allowed_author_ids:
                continue

            author_name = author.get("display_name")
            author_position_text = auth.get("author_position")
            corresponding = bool(auth.get("is_corresponding"))

            # Filter to education institutions
            insts = auth.get("institutions") or []
            edu_insts = [i for i in insts if is_education_inst(i)]
            if not edu_insts:
                continue

            # Initialise top-level author entry
            if author_id not in author_map:
                author_map[author_id] = {
                    "author_id": author_id,
                    "author_id_url": author_id_url,
                    "name": author_name,
                    "institutions_seen": {},
                    "concepts": {},  # keyed by concept_label
                }

            entry = author_map[author_id]
            if author_name and not entry["name"]:
                entry["name"] = author_name

            # Initialise per-concept sub-entry
            if concept_label not in entry["concepts"]:
                entry["concepts"][concept_label] = _empty_concept_entry(concept_label)

            ce = entry["concepts"][concept_label]

            # Add paper record
            paper_record = {
                "title": paper.get("title"),
                "doi": paper.get("doi"),
                "year": paper.get("publication_year"),
                "citations": paper.get("cited_by_count"),
                "author_position": author_position_text,
                "author_position_num": f"{idx}/{total_authors}",
                "is_corresponding": corresponding,
                "abstract": paper.get("abstract"),
                "primary_topic": topic_info,
                "grants": grant_info,
                "venue": venue,
            }
            ce["papers"].append(paper_record)

            # Accumulate metrics
            ce["total_field_citations"] += paper.get("cited_by_count", 0) or 0

            if author_position_text == "first":
                ce["first_author_count"] += 1
            elif author_position_text == "last":
                ce["last_author_count"] += 1
            if corresponding:
                ce["corresponding_author_count"] += 1

            # Topic distribution
            if topic_info and topic_info.get("topic"):
                ce["topic_counts"][topic_info["topic"]] += 1

            # Funding
            for g in grant_info:
                funder = g.get("funder")
                if funder:
                    ce["funder_counts"][funder] += 1

            # Venue
            if venue:
                ce["venue_counts"][venue] += 1

            # Institutions (shared across concepts)
            for inst in edu_insts:
                inst_id = extract_institution_id(inst.get("id"))
                if inst_id and inst_id not in entry["institutions_seen"]:
                    entry["institutions_seen"][inst_id] = {
                        "id": inst.get("id"),
                        "name": inst.get("display_name"),
                        "type": inst.get("type"),
                        "country": inst.get("country_code"),
                    }


def _finalize_author_map(author_map):
    """Convert counters to plain dicts and compute summary fields."""
    for author_id, entry in author_map.items():
        total_citations_all = 0
        for clabel, ce in entry["concepts"].items():
            ce["topic_counts"] = dict(ce["topic_counts"])
            ce["funder_counts"] = dict(ce["funder_counts"])
            ce["venue_counts"] = dict(ce["venue_counts"])
            ce["paper_count"] = len(ce["papers"])
            years = [p["year"] for p in ce["papers"] if p.get("year")]
            ce["most_recent_year"] = max(years) if years else None
            total_citations_all += ce["total_field_citations"]

        entry["total_field_citations_all"] = total_citations_all

    return author_map


def _apply_author_limit(author_map, limit):
    """Return the top N authors by total field citations when *limit* is set."""
    if limit is None:
        return author_map

    sorted_authors = sorted(
        author_map.items(),
        key=lambda x: x[1].get("total_field_citations_all", 0),
        reverse=True,
    )[:limit]
    return dict(sorted_authors)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def run(force=False, limit=None):
    """
    Build the merged field-specific author map from all concept paper files.


    Args:
        force: If True, rebuild even if the map already exists.
        limit: If set, keep only the top N authors (by total field citations
               summed across all concepts).
    """
    ensure_dirs()

    if os.path.exists(FIELD_AUTHOR_MAP_FILE) and not force:
        data = json.load(open(FIELD_AUTHOR_MAP_FILE, "r"))
        print(
            f"[Stage 2] Author map already exists with {len(data)} authors. "
            "Use --force to rebuild."
        )
        return

    # Check that at least one papers file exists
    any_found = False
    for concept in CONCEPTS:
        if os.path.exists(papers_file_for(concept["label"])):
            any_found = True
            break

    if not any_found:
        print("[Stage 2] Error: no papers files found. Run Stage 1 first.")
        return

    print(f"[Stage 2] Extracting authors across {len(CONCEPTS)} concept(s) ...")

    author_map: dict[str, dict] = {}

    for concept in CONCEPTS:
        label = concept["label"]
        pfile = papers_file_for(label)

        if not os.path.exists(pfile):
            print(f"  [{label}] No papers file found, skipping.")
            continue

        papers = []
        with open(pfile, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    papers.append(json.loads(line))

        print(f"  [{label}] Loaded {len(papers)} papers.")
        _process_papers(papers, label, author_map)

    # ------------------------------------------------------------------
    # Finalise: convert defaultdicts, add summary fields
    # ------------------------------------------------------------------
    author_map = _finalize_author_map(author_map)

    # ------------------------------------------------------------------
    # Optionally limit to top N
    # ------------------------------------------------------------------
    if limit:
        author_map = _apply_author_limit(author_map, limit)
        print(f"  Limited to top {limit} authors by total field citations.")

    save_json(author_map, FIELD_AUTHOR_MAP_FILE)

    print(f"[Stage 2] Done. {len(author_map)} unique education-institution authors.")
    print(f"  Saved to {FIELD_AUTHOR_MAP_FILE}")
