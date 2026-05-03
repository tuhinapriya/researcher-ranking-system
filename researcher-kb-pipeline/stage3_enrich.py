"""
Stage 3 -- Enrich Author Profiles
==================================
 3a  Full OpenAlex author profile + Semantic Scholar enrichment
 3b  Co-author / mentee analysis
 3c  Institution enrichment
"""

import os
from collections import defaultdict

from db import fetch_existing_institution_ids, fetch_existing_researcher_ids, get_connection

from config import (
    COAUTHORS_DIR,
    FIELD_AUTHOR_MAP_FILE,
    INSTITUTIONS_DIR,
    MAX_COAUTHOR_WORKS_PAGES,
    MAX_COAUTHORS_TO_CHECK,
    MENTEE_MAX_WORKS,
    OPENALEX_BASE,
    PROFILES_DIR,
    S2_BASE,
    WORKS_PER_PAGE,
    ensure_dirs,
)
from utils import (
    extract_author_id,
    extract_institution_id,
    is_stale,
    load_json,
    openalex_get,
    s2_get,
    save_json,
)


# ================================================================
#  Stage 3a  --  Author Profile Enrichment
# ================================================================


def _fetch_oa_author(author_id):
    """Fetch the full OpenAlex author object."""
    url = f"{OPENALEX_BASE}/authors/{author_id}"
    try:
        return openalex_get(url)
    except Exception as e:
        print(f"    [3a] Error fetching OpenAlex author {author_id}: {e}")
        return None


def _fetch_s2_author(author_name, known_dois=None):
    """
    Search Semantic Scholar for an author by name.
    Returns the best-matching S2 author dict, or None.
    """
    if not author_name:
        return None

    url = f"{S2_BASE}/author/search"
    params = {
        "query": author_name,
        "limit": 5,
        "fields": (
            "name,affiliations,homepage,paperCount,"
            "citationCount,hIndex,externalIds,url"
        ),
    }

    data = s2_get(url, params=params)
    if not data:
        return None

    hits = data.get("data", [])
    if not hits:
        return None

    # Prefer exact name match
    for hit in hits:
        if (hit.get("name") or "").lower().strip() == author_name.lower().strip():
            return hit

    # Fallback: top relevance hit
    return hits[0]


def run_3a(force=False, limit=None, author_map_override=None):
    """
    Fetch full author profiles from OpenAlex + Semantic Scholar.
    One JSON file per author in data/raw/profiles/.
    """
    ensure_dirs()

    if author_map_override is not None:
        author_map = author_map_override
        print("[Stage 3a] Using incremental in-memory batch for Stage 3a")
    else:
        author_map = load_json(FIELD_AUTHOR_MAP_FILE)
        if not author_map:
            print("[Stage 3a] Error: field_author_map.json not found. Run Stage 2 first.")
            return

    author_ids = list(author_map.keys())
    if limit:
        author_ids = author_ids[:limit]
    total = len(author_ids)
    print(f"[Stage 3a] Enriching {total} author profiles ...")

    skipped = fetched = errors = 0
    existing_researcher_ids = set()
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        existing_researcher_ids = fetch_existing_researcher_ids(cursor, author_ids)
    except Exception as e:
        print(f"[Stage 3a] DB lookup unavailable, continuing without reuse check: {e}")
    finally:
        if conn:
            conn.close()

    for i, author_id in enumerate(author_ids, start=1):
        profile_path = os.path.join(PROFILES_DIR, f"{author_id}.json")
        profile_is_fresh = not is_stale(profile_path)

        if author_id in existing_researcher_ids and profile_is_fresh:
            print(f"  [3a] Reusing existing researcher profile for {author_id}")
            skipped += 1
            continue

        if not force and profile_is_fresh:
            skipped += 1
            continue

        entry = author_map[author_id]
        author_name = entry.get("name")

        oa_profile = _fetch_oa_author(author_id)
        if not oa_profile:
            errors += 1
            print(f"  [{i}/{total}] {author_name} -- OpenAlex fetch failed")
            continue

        # Semantic Scholar (best-effort)
        # Collect DOIs across all concepts this author appears in
        known_dois = []
        for ce in entry.get("concepts", {}).values():
            known_dois.extend(
                p.get("doi") for p in ce.get("papers", []) if p.get("doi")
            )
        s2_profile = _fetch_s2_author(author_name, known_dois=known_dois)

        profile = {
            "author_id": author_id,
            "openalex": oa_profile,
            "semantic_scholar": s2_profile,
        }

        save_json(profile, profile_path)
        fetched += 1

        if i % 10 == 0 or i == total:
            print(
                f"  [{i}/{total}] Fetched {fetched}, skipped {skipped}, "
                f"errors {errors}"
            )

    print(
        f"[Stage 3a] Done. Fetched {fetched}, skipped {skipped} (cached), "
        f"errors {errors}."
    )


# ================================================================
#  Stage 3b  --  Co-author / Mentee Analysis
# ================================================================


def _fetch_recent_works(author_id, max_pages=None):
    """Fetch an author's recent works (last 5 years) from OpenAlex."""
    if max_pages is None:
        max_pages = MAX_COAUTHOR_WORKS_PAGES

    works = []
    cursor = "*"

    for _ in range(max_pages):
        url = f"{OPENALEX_BASE}/works"
        params = {
            "filter": f"author.id:{author_id},publication_year:>2019",
            "per_page": WORKS_PER_PAGE,
            "cursor": cursor,
            "select": "id,authorships,publication_year,cited_by_count",
        }

        try:
            data = openalex_get(url, params=params)
        except Exception as e:
            print(f"    [3b] Error fetching works for {author_id}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        works.extend(results)
        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor

    return works


def _analyse_coauthors(researcher_id, researcher_institutions, works):
    """
    Classify co-authors from a list of works.
    Returns {coauthor_id: info_dict}.
    """
    coauthor_info: dict[str, dict] = {}

    researcher_inst_ids = (
        set(researcher_institutions.keys()) if researcher_institutions else set()
    )

    for work in works:
        for auth in work.get("authorships", []):
            author = auth.get("author") or {}
            cid = extract_author_id(author.get("id"))

            if not cid or cid == researcher_id:
                continue

            if cid not in coauthor_info:
                coauthor_info[cid] = {
                    "name": author.get("display_name"),
                    "id": cid,
                    "shared_papers": 0,
                    "same_institution": False,
                    "institutions": set(),
                }

            info = coauthor_info[cid]
            info["shared_papers"] += 1

            for inst in auth.get("institutions") or []:
                inst_id = extract_institution_id(inst.get("id"))
                if inst_id:
                    info["institutions"].add(inst_id)
                    if inst_id in researcher_inst_ids:
                        info["same_institution"] = True

    # Convert sets for JSON serialisation
    for info in coauthor_info.values():
        info["institutions"] = list(info["institutions"])

    return coauthor_info


def run_3b(force=False, limit=None, author_map_override=None):
    """
    For each researcher, fetch recent works, identify likely mentees.
    One JSON file per author in data/raw/coauthors/.
    """
    ensure_dirs()

    if author_map_override is not None:
        author_map = author_map_override
        print("[Stage 3b] Using incremental in-memory batch for Stage 3b")
    else:
        author_map = load_json(FIELD_AUTHOR_MAP_FILE)
        if not author_map:
            print("[Stage 3b] Error: field_author_map.json not found. Run Stage 2 first.")
            return

    author_ids = list(author_map.keys())
    if limit:
        author_ids = author_ids[:limit]
    total = len(author_ids)
    print(f"[Stage 3b] Analysing co-authors for {total} researchers ...")

    skipped = fetched = 0

    for i, author_id in enumerate(author_ids, start=1):
        coauthor_path = os.path.join(COAUTHORS_DIR, f"{author_id}.json")

        if not force and not is_stale(coauthor_path):
            skipped += 1
            continue

        entry = author_map[author_id]
        institutions = entry.get("institutions_seen", {})

        # Fetch recent works
        works = _fetch_recent_works(author_id)

        # Classify co-authors
        coauthor_data = _analyse_coauthors(author_id, institutions, works)

        sorted_coauthors = sorted(
            coauthor_data.values(),
            key=lambda x: x["shared_papers"],
            reverse=True,
        )[:MAX_COAUTHORS_TO_CHECK]

        # Identify likely mentees (same institution, low works_count)
        likely_mentees = []
        same_inst = [c for c in sorted_coauthors if c.get("same_institution")]

        for coauthor in same_inst[:MAX_COAUTHORS_TO_CHECK]:
            cid = coauthor["id"]
            try:
                url = f"{OPENALEX_BASE}/authors/{cid}"
                params = {
                    "select": "id,display_name,works_count,summary_stats,created_date"
                }
                ca_profile = openalex_get(url, params=params)

                works_count = ca_profile.get("works_count", 999)
                if works_count <= MENTEE_MAX_WORKS:
                    likely_mentees.append(
                        {
                            "name": coauthor["name"],
                            "id": cid,
                            "works_count": works_count,
                            "shared_papers": coauthor["shared_papers"],
                        }
                    )
            except Exception:
                pass

        # Seniority signals from recent works
        total_papers = len(works)
        last_author_count = 0
        corresponding_count = 0

        for work in works:
            for auth in work.get("authorships", []):
                author = auth.get("author") or {}
                if extract_author_id(author.get("id")) == author_id:
                    if auth.get("author_position") == "last":
                        last_author_count += 1
                    if auth.get("is_corresponding"):
                        corresponding_count += 1

        result = {
            "author_id": author_id,
            "total_recent_works_analysed": total_papers,
            "total_unique_collaborators": len(coauthor_data),
            "estimated_mentee_count": len(likely_mentees),
            "likely_mentees": likely_mentees,
            "seniority_signals": {
                "last_author_ratio": (
                    round(last_author_count / total_papers, 2)
                    if total_papers > 0
                    else 0
                ),
                "corresponding_author_ratio": (
                    round(corresponding_count / total_papers, 2)
                    if total_papers > 0
                    else 0
                ),
            },
            "top_collaborators": [
                {
                    "name": c["name"],
                    "id": c["id"],
                    "shared_papers": c["shared_papers"],
                    "same_institution": c["same_institution"],
                }
                for c in sorted_coauthors[:10]
            ],
        }

        save_json(result, coauthor_path)
        fetched += 1

        if i % 10 == 0 or i == total:
            print(f"  [{i}/{total}] Analysed {fetched}, skipped {skipped}")

    print(f"[Stage 3b] Done. Analysed {fetched}, skipped {skipped} (cached).")


# ================================================================
#  Stage 3c  --  Institution Enrichment
# ================================================================


def run_3c(force=False, limit=None, author_map_override=None):
    """
    Fetch full OpenAlex institution profiles.
    Institutions are shared across researchers so we cache aggressively.
    One JSON file per institution in data/raw/institutions/.
    """
    ensure_dirs()

    if author_map_override is not None:
        author_map = author_map_override
        print("[Stage 3c] Using incremental in-memory batch for Stage 3c")
    else:
        author_map = load_json(FIELD_AUTHOR_MAP_FILE)
        if not author_map:
            print("[Stage 3c] Error: field_author_map.json not found. Run Stage 2 first.")
            return

    # Collect institution IDs -- only from the limited set of authors if limit is set
    author_ids = list(author_map.keys())
    if limit:
        author_ids = author_ids[:limit]

    all_inst_ids: set[str] = set()
    for aid in author_ids:
        entry = author_map[aid]
        for inst_id in entry.get("institutions_seen", {}).keys():
            all_inst_ids.add(inst_id)

    total = len(all_inst_ids)
    print(f"[Stage 3c] Enriching {total} unique institutions ...")

    skipped = fetched = errors = 0
    existing_inst_ids = set()
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        existing_inst_ids = fetch_existing_institution_ids(cursor, list(all_inst_ids))
    except Exception as e:
        print(f"[Stage 3c] DB lookup unavailable, continuing without reuse check: {e}")
    finally:
        if conn:
            conn.close()

    for i, inst_id in enumerate(sorted(all_inst_ids), start=1):
        inst_path = os.path.join(INSTITUTIONS_DIR, f"{inst_id}.json")

        if not force and not is_stale(inst_path):
            print(f"  [3c] Reusing existing institution for {inst_id}")
            skipped += 1
            continue

        if not force and inst_id in existing_inst_ids:
            print(f"  [3c] Reusing existing institution for {inst_id}")
            skipped += 1
            continue

        try:
            url = f"{OPENALEX_BASE}/institutions/{inst_id}"
            data = openalex_get(url)
            save_json(data, inst_path)
            fetched += 1
        except Exception as e:
            print(f"    [3c] Error fetching institution {inst_id}: {e}")
            errors += 1

        if i % 10 == 0 or i == total:
            print(
                f"  [{i}/{total}] Fetched {fetched}, skipped {skipped}, "
                f"errors {errors}"
            )

    print(
        f"[Stage 3c] Done. Fetched {fetched}, skipped {skipped} (cached), "
        f"errors {errors}."
    )


# ================================================================
#  Public API  --  run all sub-stages
# ================================================================


def run(force=False, limit=None):
    """Run all Stage 3 sub-stages sequentially."""
    run_3a(force=force, limit=limit)
    run_3b(force=force, limit=limit)
    run_3c(force=force, limit=limit)
