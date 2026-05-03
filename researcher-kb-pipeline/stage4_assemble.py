"""
Stage 4 -- Assemble the Knowledge Base
=======================================
Merge all enrichment stages into a single knowledge_base.json
and a summary Excel spreadsheet.


Supports multiple concepts: each researcher has a list of
field_relevance entries (one per concept they appear in).
"""

import os
from datetime import datetime
import logging
from db import (
    PineconeUpsertError,
    get_connection,
    upsert_institution,
    upsert_researcher,
    upsert_papers,
    upsert_topics,
    upsert_collaborations,
)


import pandas as pd


from config import (
    COAUTHORS_DIR,
    FIELD_AUTHOR_MAP_FILE,
    INSTITUTIONS_DIR,
    KNOWLEDGE_BASE_FILE,
    PROFILES_DIR,
    SUMMARY_SCHEMA_FILE,
    SUMMARY_EXCEL_FILE,
    ensure_dirs,
)
from utils import extract_institution_id, load_json, save_json


INSTITUTION_SANITIZATION_RULES = {
    "id": {"required": True},
    "name": {"required": True},
    "country": {"default": "Unknown"},
    "city": {"default": "Unknown"},
    "type": {"default": "Unknown"},
    "region": {"allow_null": True},
}

RESEARCHER_SANITIZATION_RULES = {
    "id": {"required": True},
    "name": {"required": True},
    "total_works": {"default": 0},
    "total_citations": {"default": 0},
    "h_index": {"default": 0},
    "i10_index": {"default": 0},
    "career_start_year": {"allow_null": True},
    "years_active": {"allow_null": True},
    "last_author_ratio_recent": {"allow_null": True},
    "current_institution_id": {"allow_null": True},
    "country": {"allow_null": True},
    "last_updated": {"allow_null": True},
}

SUMMARY_COLUMN_DESCRIPTIONS = {
    "Name": "The researcher's display name.",
    "Current Institution": "The researcher's primary current affiliated institution.",
    "Country": "The country associated with the current institution.",
    "Concepts": "The tracked research concepts this researcher appears in.",
    "Total Citations": "The researcher's total citation count from OpenAlex.",
    "h-index": "The researcher's h-index from OpenAlex summary metrics.",
    "Total Works": "The researcher's total published works count.",
    "Field Papers (all concepts)": "The number of tracked papers across all included concepts.",
    "Field Citations (all concepts)": "The citations earned by tracked papers across all included concepts.",
    "Estimated Mentees": "The estimated number of likely mentees inferred from coauthor analysis.",
    "Collaborators": "The total number of unique collaborators found in recent work analysis.",
    "Career Start": "The earliest affiliation year used as an estimated career start.",
    "Years Active": "The estimated number of active years since career start.",
    "Institution h-index": "The h-index of the current institution when available.",
    "ORCID": "The researcher's ORCID identifier when available.",
    "Homepage": "The researcher's homepage from Semantic Scholar when available.",
}


def _is_missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _sanitize_record(record_type, record, rules, context_label):
    sanitized = {}
    missing_required = []

    for field, rule in rules.items():
        value = record.get(field)

        if _is_missing(value):
            if rule.get("required"):
                missing_required.append(field)
                continue

            if "default" in rule:
                value = rule["default"]
                logging.warning(
                    "[Stage 4] Defaulting %s to %s for %s",
                    field,
                    value,
                    context_label,
                )
            else:
                value = None
        elif isinstance(value, str):
            value = value.strip()

        sanitized[field] = value

    if missing_required:
        logging.warning(
            "[Stage 4] Skipping %s due to missing %s",
            record_type,
            "/".join(missing_required),
        )
        return None

    return sanitized


def _normalize_filter_value(value):
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _institution_matches_region_filter(inst, institution_cache, region_filter):
    normalized_filter = _normalize_filter_value(region_filter)
    if not normalized_filter:
        return True

    inst_id = extract_institution_id(inst.get("id")) if inst else None
    cached_inst = institution_cache.get(inst_id, {}) if inst_id else {}
    cached_geo = cached_inst.get("geo", {})

    candidate_values = {
        inst.get("country") if inst else None,
        inst.get("region") if inst else None,
        cached_geo.get("country"),
        cached_geo.get("country_code"),
        cached_geo.get("region"),
    }

    return normalized_filter in {
        normalized
        for normalized in (_normalize_filter_value(value) for value in candidate_values)
        if normalized
    }


def _researcher_matches_region_filter(researcher, institution_cache, region_filter):
    if not _normalize_filter_value(region_filter):
        return True

    affiliation = researcher.get("affiliation", {})
    institutions = affiliation.get("current") or affiliation.get("history") or []
    return any(
        _institution_matches_region_filter(inst, institution_cache, region_filter)
        for inst in institutions
    )


def _build_summary_column_schema(rows):
    if not rows:
        return []

    return [
        {
            "column": column,
            "description": SUMMARY_COLUMN_DESCRIPTIONS.get(
                column, "Plain-English description not yet defined."
            ),
        }
        for column in rows[0].keys()
    ]


# ================================================================
#  Build one researcher profile
# ================================================================


def _build_field_relevance(concept_label, ce):
    """Build a single field_relevance dict from a per-concept entry."""
    papers = ce.get("papers", [])

    venue_counts = ce.get("venue_counts", {})
    top_venues = [
        {"venue": v, "count": c}
        for v, c in sorted(venue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    funder_counts = ce.get("funder_counts", {})
    funding_sources = [
        {"funder": f, "grant_count": c}
        for f, c in sorted(funder_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "concept": concept_label,
        "papers_in_field": ce.get("paper_count", len(papers)),
        "field_citations": ce.get("total_field_citations", 0),
        "first_author_papers": ce.get("first_author_count", 0),
        "last_author_papers": ce.get("last_author_count", 0),
        "corresponding_author_papers": ce.get("corresponding_author_count", 0),
        "most_recent_year": ce.get("most_recent_year"),
        "top_venues": top_venues,
        "funding_sources": funding_sources,
    }


def _build_profile(
    author_id, field_data, oa_profile, s2_profile, coauthor_data, institution_cache
):
    """Merge every data source into a single researcher dict."""

    oa = oa_profile or {}
    s2 = s2_profile or {}
    coauth = coauthor_data or {}
    concepts = field_data.get("concepts", {})

    # --- Identity ---
    name = oa.get("display_name") or field_data.get("name", "")
    name_alternatives = oa.get("display_name_alternatives", [])
    orcid = oa.get("orcid")

    ids_obj = oa.get("ids", {})
    external_ids = {
        k: v
        for k, v in {
            "scopus": ids_obj.get("scopus"),
            "wikipedia": ids_obj.get("wikipedia"),
            "twitter": ids_obj.get("twitter"),
        }.items()
        if v
    }

    # --- Global Metrics ---
    ss = oa.get("summary_stats", {})
    global_metrics = {
        "total_works": oa.get("works_count"),
        "total_citations": oa.get("cited_by_count"),
        "h_index": ss.get("h_index"),
        "i10_index": ss.get("i10_index"),
        "two_year_mean_citedness": ss.get("2yr_mean_citedness"),
    }

    # --- Affiliation ---
    current_institutions = []
    for inst in oa.get("last_known_institutions") or []:
        inst_id = extract_institution_id(inst.get("id"))
        cached_inst = institution_cache.get(inst_id, {}) if inst_id else {}
        cached_geo = cached_inst.get("geo", {})
        current_institutions.append(
            {
                "name": inst.get("display_name"),
                "type": inst.get("type") or cached_inst.get("type"),
                "country": inst.get("country_code") or cached_geo.get("country"),
                "city": cached_geo.get("city"),
                "region": cached_geo.get("region"),
                "id": inst.get("id"),
            }
        )

    affiliation_history = []
    for aff in oa.get("affiliations") or []:
        inst = aff.get("institution", {})
        affiliation_history.append(
            {
                "name": inst.get("display_name"),
                "type": inst.get("type"),
                "country": inst.get("country_code"),
                "id": inst.get("id"),
                "years": aff.get("years", []),
            }
        )

    # --- Research Topics (broad, from x_concepts) ---
    research_topics_broad = [
        {"name": c.get("display_name"), "score": c.get("score")}
        for c in (oa.get("x_concepts") or [])[:15]
    ]

    # --- Research Topics (granular, aggregated across all concepts) ---
    topic_details: dict[str, dict] = {}
    all_papers = []
    for ce in concepts.values():
        for paper in ce.get("papers", []):
            all_papers.append(paper)
            pt = paper.get("primary_topic")
            if pt and pt.get("topic"):
                tname = pt["topic"]
                if tname not in topic_details:
                    topic_details[tname] = {
                        "topic": tname,
                        "subfield": pt.get("subfield"),
                        "field": pt.get("field"),
                        "domain": pt.get("domain"),
                        "paper_count": 0,
                    }
                topic_details[tname]["paper_count"] += 1

    research_topics_granular = sorted(
        topic_details.values(), key=lambda x: x["paper_count"], reverse=True
    )

    # --- Citation Trend ---
    citation_trend = [
        {
            "year": y.get("year"),
            "works": y.get("works_count"),
            "citations": y.get("cited_by_count"),
        }
        for y in oa.get("counts_by_year") or []
    ]

    # --- Field Relevance (one entry per concept) ---
    field_relevance = [
        _build_field_relevance(clabel, ce) for clabel, ce in concepts.items()
    ]
    # Sort by field citations descending
    field_relevance.sort(key=lambda x: x["field_citations"], reverse=True)

    # --- Lab & Mentorship ---
    all_years = []
    for aff in affiliation_history:
        all_years.extend(aff.get("years", []))
    career_start_year = min(all_years) if all_years else None
    years_active = (
        (datetime.now().year - career_start_year) if career_start_year else None
    )

    seniority_from_coauth = coauth.get("seniority_signals", {})
    total_field_papers = len(all_papers)

    # Aggregate last-author count across concepts
    total_last_author = sum(ce.get("last_author_count", 0) for ce in concepts.values())

    lab_and_mentorship = {
        "estimated_mentee_count": coauth.get("estimated_mentee_count", 0),
        "mentee_names": [m.get("name") for m in coauth.get("likely_mentees", [])],
        "total_unique_collaborators": coauth.get("total_unique_collaborators", 0),
        "top_collaborators": coauth.get("top_collaborators", []),
        "seniority_signals": {
            "career_start_year": career_start_year,
            "years_active": years_active,
            "last_author_ratio_recent": seniority_from_coauth.get(
                "last_author_ratio", 0
            ),
            "corresponding_author_ratio_recent": seniority_from_coauth.get(
                "corresponding_author_ratio", 0
            ),
            "last_author_ratio_field": (
                round(total_last_author / total_field_papers, 2)
                if total_field_papers > 0
                else 0
            ),
        },
    }

    # --- Institution Quality ---
    institution_quality = None
    if current_institutions:
        primary_inst = current_institutions[0]
        inst_id = extract_institution_id(primary_inst.get("id"))
        if inst_id and inst_id in institution_cache:
            idata = institution_cache[inst_id]
            ist = idata.get("summary_stats", {})
            geo = idata.get("geo", {})
            institution_quality = {
                "name": idata.get("display_name"),
                "h_index": ist.get("h_index"),
                "total_works": idata.get("works_count"),
                "total_citations": idata.get("cited_by_count"),
                "two_year_mean_citedness": ist.get("2yr_mean_citedness"),
                "country": geo.get("country"),
                "city": geo.get("city"),
                "region": geo.get("region"),
                "homepage": idata.get("homepage_url"),
            }

    # --- Papers in Field (grouped by concept) ---
    papers_by_concept = {}
    for clabel, ce in concepts.items():
        concept_papers = []
        for p in ce.get("papers", []):
            pt = p.get("primary_topic")
            concept_papers.append(
                {
                    "title": p.get("title"),
                    "doi": p.get("doi"),
                    "year": p.get("year"),
                    "citations": p.get("citations"),
                    "author_position": p.get("author_position"),
                    "abstract": p.get("abstract"),
                    "primary_topic": pt.get("topic") if pt else None,
                    "grants": p.get("grants", []),
                    "venue": p.get("venue"),
                }
            )
        concept_papers.sort(key=lambda x: x.get("citations") or 0, reverse=True)
        papers_by_concept[clabel] = concept_papers

    # --- Semantic Scholar ---
    semantic_scholar = None
    if s2:
        semantic_scholar = {
            "url": s2.get("url"),
            "homepage": s2.get("homepage"),
            "s2_affiliations": s2.get("affiliations", []),
            "s2_h_index": s2.get("hIndex"),
            "s2_citation_count": s2.get("citationCount"),
            "s2_paper_count": s2.get("paperCount"),
        }

    # --- Assemble ---
    return {
        "researcher_id": field_data.get("author_id_url"),
        "name": name,
        "name_alternatives": name_alternatives,
        "orcid": orcid,
        "external_ids": external_ids,
        "global_metrics": global_metrics,
        "affiliation": {
            "current": current_institutions,
            "history": affiliation_history,
        },
        "research_topics_broad": research_topics_broad,
        "research_topics_granular": research_topics_granular,
        "citation_trend": citation_trend,
        "field_relevance": field_relevance,
        "lab_and_mentorship": lab_and_mentorship,
        "institution_quality": institution_quality,
        "papers_by_concept": papers_by_concept,
        "semantic_scholar": semantic_scholar,
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
    }


def _upsert_researcher_bundle(cursor, researcher):
    researcher_id = (
        researcher.get("researcher_id").split("/")[-1]
        if researcher.get("researcher_id")
        else None
    )
    current_aff = researcher.get("affiliation", {}).get("current", [])
    inst = current_aff[0] if current_aff else None

    logging.info(
        "[Stage 4] Upserting researcher_id=%s name=%s current_affiliations=%s",
        researcher_id,
        researcher.get("name"),
        len(current_aff),
    )

    sanitized_institution = None
    if current_aff:
        institution_name = (inst or {}).get("name") or "Unknown institution"
        sanitized_institution = _sanitize_record(
            "institution",
            {
                "id": inst.get("id").split("/")[-1] if inst.get("id") else None,
                "name": inst.get("name"),
                "country": inst.get("country"),
                "city": inst.get("city"),
                "type": inst.get("type"),
                "region": inst.get("region"),
            },
            INSTITUTION_SANITIZATION_RULES,
            institution_name,
        )
        if sanitized_institution:
            upsert_institution(cursor, sanitized_institution)
            logging.info(
                "[Stage 4] Institution upserted for researcher_id=%s institution_id=%s",
                researcher_id,
                sanitized_institution.get("id"),
            )
    else:
        logging.warning(
            "[Stage 4] No current institution found for researcher_id=%s",
            researcher_id,
        )

    sanitized_researcher = _sanitize_record(
        "researcher",
        {
            "id": researcher_id,
            "name": researcher.get("name"),
            "total_works": researcher.get("global_metrics", {}).get("total_works"),
            "total_citations": researcher.get("global_metrics", {}).get(
                "total_citations"
            ),
            "h_index": researcher.get("global_metrics", {}).get("h_index"),
            "i10_index": researcher.get("global_metrics", {}).get("i10_index"),
            "career_start_year": researcher.get("lab_and_mentorship", {})
            .get("seniority_signals", {})
            .get("career_start_year"),
            "years_active": researcher.get("lab_and_mentorship", {})
            .get("seniority_signals", {})
            .get("years_active"),
            "last_author_ratio_recent": researcher.get("lab_and_mentorship", {})
            .get("seniority_signals", {})
            .get("last_author_ratio_recent"),
            "current_institution_id": (
                sanitized_institution.get("id") if sanitized_institution else None
            ),
            "country": (
                sanitized_institution.get("country") if sanitized_institution else None
            ),
            "last_updated": researcher.get("last_updated"),
        },
        RESEARCHER_SANITIZATION_RULES,
        researcher.get("name") or researcher_id or "unknown researcher",
    )
    if not sanitized_researcher:
        return False

    upsert_researcher(cursor, sanitized_researcher)
    logging.info("[Stage 4] Researcher row upserted for researcher_id=%s", researcher_id)

    upsert_papers(cursor, researcher_id, researcher.get("papers_by_concept", {}))
    upsert_topics(cursor, researcher_id, researcher.get("research_topics_granular", []))
    upsert_collaborations(
        cursor,
        researcher_id,
        researcher.get("lab_and_mentorship", {}).get("top_collaborators", []),
    )
    logging.info("[Stage 4] Related rows upserted for researcher_id=%s", researcher_id)
    return True


def _commit_transaction(conn):
    logging.info("[DB] Attempting commit")
    try:
        conn.commit()
        logging.info("[DB] Commit successful")
    except Exception as e:
        logging.error("[DB] Commit failed: %s", e)
        conn.rollback()
        logging.info("[DB] Rollback executed")
        raise


def _upsert_batch(cursor, batch, inserted_researchers, skipped_researchers):
    for batch_index, researcher in enumerate(batch, 1):
        savepoint_name = f"stage4_researcher_{batch_index}"
        cursor.execute(f"SAVEPOINT {savepoint_name}")
        try:
            if _upsert_researcher_bundle(cursor, researcher):
                inserted_researchers += 1
            else:
                skipped_researchers += 1
                cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        except Exception as record_error:
            skipped_researchers += 1
            cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            logging.exception(
                "[Stage 4] Skipping researcher due to upsert error: %s",
                record_error,
            )
        finally:
            cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")

    return inserted_researchers, skipped_researchers


# ================================================================
#  Run Stage 4
# ================================================================


def run(
    force=False,
    limit=None,
    region=None,
    author_map_override=None,
    export_artifacts=True,
):
    """
    Assemble final knowledge_base.json + summary Excel.
    Also upsert all researchers into MySQL in batches of 20.
    """
    ensure_dirs()
    if author_map_override is not None:
        author_map = author_map_override
        print("[Stage 4] Using incremental in-memory batch for Stage 4")
    else:
        author_map = load_json(FIELD_AUTHOR_MAP_FILE)
        if not author_map:
            print("[Stage 4] Error: field_author_map.json not found. Run Stage 2 first.")
            return
    author_items = list(author_map.items())
    if limit:
        author_items = author_items[:limit]
    institution_cache: dict[str, dict] = {}
    if os.path.isdir(INSTITUTIONS_DIR):
        for fname in os.listdir(INSTITUTIONS_DIR):
            if fname.endswith(".json"):
                inst_id = fname.replace(".json", "")
                idata = load_json(os.path.join(INSTITUTIONS_DIR, fname))
                if idata:
                    institution_cache[inst_id] = idata
    print(f"[Stage 4] Assembling knowledge base for {len(author_items)} researchers ...")
    print(f"  Loaded {len(institution_cache)} institution profiles.")
    if region:
        print(
            f"  Region parameter '{region}' received; Stage 4 writes are not region-filtered."
        )
    knowledge_base = []

    # --- MySQL batch upsert ---
    conn = None
    inserted_researchers = 0
    skipped_researchers = 0
    try:
        conn = get_connection()
        cursor = conn.cursor()
        logging.info("[Stage 4] MySQL cursor created. Starting batch upserts.")
        batch = []
        for idx, (author_id, field_data) in enumerate(author_items, 1):
            profile_data = load_json(os.path.join(PROFILES_DIR, f"{author_id}.json"))
            oa_profile = profile_data.get("openalex") if profile_data else None
            s2_profile = profile_data.get("semantic_scholar") if profile_data else None
            coauthor_data = load_json(os.path.join(COAUTHORS_DIR, f"{author_id}.json"))
            researcher = _build_profile(
                author_id,
                field_data,
                oa_profile,
                s2_profile,
                coauthor_data,
                institution_cache,
            )
            knowledge_base.append(researcher)
            batch.append(researcher)
            if len(batch) == 20:
                try:
                    logging.info(
                        "[Stage 4] Processing full batch ending at index=%s batch_size=%s",
                        idx,
                        len(batch),
                    )
                    inserted_researchers, skipped_researchers = _upsert_batch(
                        cursor, batch, inserted_researchers, skipped_researchers
                    )
                    _commit_transaction(conn)
                    print(
                        f"[Stage 4] Batch committed ({idx} researchers processed, "
                        f"{inserted_researchers} inserted, {skipped_researchers} skipped)"
                    )
                except Exception as e:
                    conn.rollback()
                    if isinstance(e, PineconeUpsertError):
                        logging.error("[Stage 4] Rolling back due to Pinecone failure")
                    else:
                        logging.error("[Stage 4] Rolling back due to DB failure")
                    logging.exception(
                        "[Stage 4] Batch rollback at researcher %s due to error: %s",
                        idx,
                        e,
                    )
                    raise
                batch = []
        # Final commit for any remaining researchers
        if batch:
            try:
                logging.info(
                    "[Stage 4] Processing final batch size=%s total_researchers=%s",
                    len(batch),
                    len(author_items),
                )
                inserted_researchers, skipped_researchers = _upsert_batch(
                    cursor, batch, inserted_researchers, skipped_researchers
                )
                _commit_transaction(conn)
                print(
                    f"[Stage 4] Final batch committed ({len(author_items)} researchers processed, "
                    f"{inserted_researchers} inserted, {skipped_researchers} skipped)"
                )
            except Exception as e:
                conn.rollback()
                if isinstance(e, PineconeUpsertError):
                    logging.error("[Stage 4] Rolling back due to Pinecone failure")
                else:
                    logging.error("[Stage 4] Rolling back due to DB failure")
                logging.exception("[Stage 4] Final batch rollback: %s", e)
                raise
    except Exception as e:
        logging.exception("[Stage 4] DB connection/setup error: %s", e)
        raise
    finally:
        if conn:
            conn.close()
            print("[Stage 4] MySQL connection closed.")

    rows = []
    if export_artifacts:
        # ----- Save JSON -----
        save_json(knowledge_base, KNOWLEDGE_BASE_FILE)
        print(
            f"  Saved knowledge base ({len(knowledge_base)} researchers) "
            f"to {KNOWLEDGE_BASE_FILE}"
        )

        # ----- Build summary Excel -----
        for r in knowledge_base:
            gm = r.get("global_metrics", {})
            fr_list = r.get("field_relevance", [])
            lm = r.get("lab_and_mentorship", {})
            sen = lm.get("seniority_signals", {})
            iq = r.get("institution_quality") or {}
            aff = r.get("affiliation", {})
            current = aff.get("current", [{}])
            cur_inst = current[0] if current else {}
            s2 = r.get("semantic_scholar") or {}

            # Summarise field relevance across concepts
            concepts_str = ", ".join(fr["concept"] for fr in fr_list)
            total_field_papers = sum(fr.get("papers_in_field", 0) for fr in fr_list)
            total_field_cites = sum(fr.get("field_citations", 0) for fr in fr_list)

            rows.append(
                {
                    "Name": r.get("name"),
                    "Current Institution": cur_inst.get("name"),
                    "Country": cur_inst.get("country"),
                    "Concepts": concepts_str,
                    "Total Citations": gm.get("total_citations"),
                    "h-index": gm.get("h_index"),
                    "Total Works": gm.get("total_works"),
                    "Field Papers (all concepts)": total_field_papers,
                    "Field Citations (all concepts)": total_field_cites,
                    "Estimated Mentees": lm.get("estimated_mentee_count"),
                    "Collaborators": lm.get("total_unique_collaborators"),
                    "Career Start": sen.get("career_start_year"),
                    "Years Active": sen.get("years_active"),
                    "Institution h-index": iq.get("h_index"),
                    "ORCID": r.get("orcid"),
                    "Homepage": s2.get("homepage"),
                }
            )

        df = pd.DataFrame(rows)
        df.to_excel(SUMMARY_EXCEL_FILE, index=False)
        print(f"  Saved summary Excel to {SUMMARY_EXCEL_FILE}")
        save_json(_build_summary_column_schema(rows), SUMMARY_SCHEMA_FILE)
        print(f"  Saved summary schema mapping to {SUMMARY_SCHEMA_FILE}")
    else:
        print("[Stage 4] Artifact exports disabled for incremental run.")
    print("[Stage 4] Done.")
    return {
        "inserted_researchers": inserted_researchers,
        "skipped_researchers": skipped_researchers,
        "knowledge_base_size": len(knowledge_base),
    }
