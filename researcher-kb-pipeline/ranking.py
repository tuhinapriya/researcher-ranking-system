import json
import logging
import math
from collections import defaultdict
from pathlib import Path

import embeddings
from config import (
    MAX_TOP_K_PINECONE,
    MIN_UNIQUE_RESEARCHERS,
    PARETO_EPSILON,
    PARETO_REQUIRE_K,
    Q_MAX_PAPERS_PER_RESEARCHER,
    Q_TOP_PAPERS,
    Q_WEIGHT,
    TARGET_PAPERS_PER_RESEARCHER,
    TOP_K_PINECONE,
)
from db import fetch_papers_by_ids

try:
    from config import R_WEIGHT
except ImportError:
    from config import H_WEIGHT as R_WEIGHT


def _normalize_dict(values):
    if not values:
        return {}

    minimum = min(values.values())
    maximum = max(values.values())
    if math.isclose(minimum, maximum):
        return {key: 1.0 for key in values}

    denominator = maximum - minimum
    return {key: (value - minimum) / denominator for key, value in values.items()}


def _coerce_match_value(match, field, default=None):
    if isinstance(match, dict):
        return match.get(field, default)
    return getattr(match, field, default)


def _coerce_match_metadata(match):
    metadata = _coerce_match_value(match, "metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _is_in_selected_year_range(year, start_year=None, end_year=None):
    if year is None:
        return start_year is None and end_year is None
    if start_year is not None and year < start_year:
        return False
    if end_year is not None and year > end_year:
        return False
    return True


def _summarize_match_depth(ranked_matches):
    counts = defaultdict(int)
    for match in ranked_matches:
        researcher_id = match.get("researcher_id")
        if researcher_id:
            counts[researcher_id] += 1

    unique_researcher_count = len(counts)
    total_matches = len(ranked_matches)
    average = (
        total_matches / unique_researcher_count if unique_researcher_count else 0.0
    )
    return {
        "average_papers_per_researcher": average,
        "researchers_with_multiple_matches": sum(
            1 for count in counts.values() if count >= 2
        ),
        "max_papers_for_any_researcher": max(counts.values(), default=0),
    }


def _sort_ranked_matches(ranked_matches):
    return sorted(
        ranked_matches,
        key=lambda match: match.get("similarity", 0.0),
        reverse=True,
    )


def _select_researchers_for_depth_enrichment(ranked_matches, limit):
    researcher_ids = []
    seen = set()
    for match in ranked_matches:
        researcher_id = match.get("researcher_id")
        if not researcher_id or researcher_id in seen:
            continue
        researcher_ids.append(researcher_id)
        seen.add(researcher_id)
        if len(researcher_ids) >= limit:
            break
    return researcher_ids


def _enrich_ranked_matches_for_researchers(
    query_embedding,
    cursor,
    ranked_matches,
    researcher_ids,
    max_papers_per_researcher,
):
    import pinecone_client

    combined_matches = {
        match["paper_id"]: match for match in ranked_matches if match.get("paper_id")
    }
    raw_enriched_match_count = 0

    for researcher_id in researcher_ids:
        result = pinecone_client.index.query(
            vector=query_embedding,
            top_k=max_papers_per_researcher,
            include_metadata=True,
            filter={"researcher_id": {"$eq": researcher_id}},
        )
        matches = _coerce_match_value(result, "matches", [])
        enriched_matches, _ = _extract_ranked_matches(matches, cursor)
        raw_enriched_match_count += len(enriched_matches)
        for match in enriched_matches:
            if match.get("paper_id"):
                combined_matches[match["paper_id"]] = match

    enriched_ranked_matches = _sort_ranked_matches(list(combined_matches.values()))
    return enriched_ranked_matches, {
        "depth_enrichment_enabled": bool(researcher_ids),
        "depth_enriched_researcher_count": len(researcher_ids),
        "depth_enriched_researcher_ids": researcher_ids,
        "depth_enrichment_raw_match_count": raw_enriched_match_count,
        "depth_enrichment_added_unique_matches": max(
            len(enriched_ranked_matches) - len(ranked_matches), 0
        ),
    }


def _extract_ranked_matches(matches, cursor):
    paper_ids = [
        _coerce_match_value(match, "id")
        for match in matches
        if _coerce_match_value(match, "id")
    ]
    paper_details = fetch_papers_by_ids(cursor, paper_ids)

    ranked_matches = []
    unique_researchers = set()
    for match in matches:
        metadata = _coerce_match_metadata(match)
        paper_id = _coerce_match_value(match, "id")
        paper_row = paper_details.get(paper_id, {})
        researcher_id = metadata.get("researcher_id") or paper_row.get("researcher_id")
        if not researcher_id:
            continue

        unique_researchers.add(researcher_id)
        ranked_matches.append(
            {
                "paper_id": paper_id,
                "researcher_id": researcher_id,
                "title": paper_row.get("title"),
                "year": metadata.get("year") or paper_row.get("year"),
                "citations": metadata.get("citations", paper_row.get("citations")),
                "similarity": float(_coerce_match_value(match, "score", 0.0) or 0.0),
            }
        )

    return ranked_matches, unique_researchers


def _fetch_diverse_ranked_matches(
    query_embedding,
    cursor,
    top_k,
    min_unique_researchers,
    max_top_k,
    target_papers_per_researcher,
):
    import pinecone_client

    current_top_k = min(top_k, max_top_k)
    final_ranked_matches = []
    unique_researchers = set()
    rounds = 0

    while True:
        rounds += 1
        result = pinecone_client.index.query(
            vector=query_embedding,
            top_k=current_top_k,
            include_metadata=True,
        )
        matches = _coerce_match_value(result, "matches", [])
        final_ranked_matches, unique_researchers = _extract_ranked_matches(
            matches, cursor
        )

        depth_summary = _summarize_match_depth(final_ranked_matches)
        has_enough_unique_researchers = (
            len(unique_researchers) >= min_unique_researchers
        )
        has_enough_depth = (
            depth_summary["average_papers_per_researcher"]
            >= target_papers_per_researcher
        )

        if has_enough_unique_researchers and has_enough_depth:
            break
        if current_top_k >= max_top_k:
            break
        if len(matches) < current_top_k:
            break

        current_top_k = min(current_top_k * 2, max_top_k)

    debug_metadata = {
        "initial_top_k": top_k,
        "final_top_k": current_top_k,
        "pinecone_match_count": len(final_ranked_matches),
        "unique_researchers_found": len(unique_researchers),
        "expansion_rounds": rounds,
        "min_unique_researchers_target": min_unique_researchers,
        "target_papers_per_researcher": target_papers_per_researcher,
        **depth_summary,
    }
    logging.info(
        "[Ranking] Pinecone candidate expansion initial_top_k=%s final_top_k=%s unique_researchers=%s matches=%s avg_papers_per_researcher=%.3f rounds=%s",
        top_k,
        current_top_k,
        len(unique_researchers),
        len(final_ranked_matches),
        depth_summary["average_papers_per_researcher"],
        rounds,
    )

    return final_ranked_matches, debug_metadata


def _build_qr_details(
    ranked_matches,
    candidate_researcher_ids=None,
    top_n=Q_TOP_PAPERS,
    start_year=None,
    end_year=None,
):
    """Q = avg(top-N similarity. R = total citations from query-matched papers in the selected time range."""
    allowed_ids = set(candidate_researcher_ids or [])
    per_researcher = defaultdict(list)

    for match in ranked_matches:
        researcher_id = match.get("researcher_id")
        if not researcher_id:
            continue
        if allowed_ids and researcher_id not in allowed_ids:
            continue
        per_researcher[researcher_id].append(
            {
                "paper_id": match.get("paper_id"),
                "title": match.get("title"),
                "year": match.get("year"),
                "citations": match.get("citations"),
                "similarity": float(match.get("similarity", 0.0) or 0.0),
            }
        )

    researcher_q_raw = {}
    researcher_r_raw = {}
    per_researcher_top_matches = {}

    for researcher_id, paper_matches in per_researcher.items():
        sorted_matches = sorted(
            paper_matches, key=lambda m: m["similarity"], reverse=True
        )
        top_matches = sorted_matches[:top_n]

        scores = [m["similarity"] for m in top_matches]
        # Pad with zeros when fewer than top_n papers are available
        while len(scores) < top_n:
            scores.append(0.0)

        q_value = sum(scores) / top_n

        range_matches = [
            match
            for match in sorted_matches
            if _is_in_selected_year_range(match.get("year"), start_year, end_year)
        ]
        r_raw = sum(float(match.get("citations") or 0.0) for match in range_matches)

        researcher_q_raw[researcher_id] = q_value
        researcher_r_raw[researcher_id] = r_raw
        per_researcher_top_matches[researcher_id] = {
            "all_matches": sorted_matches,
            "top_matches": top_matches,
        }

    q_norm = _normalize_dict(researcher_q_raw)
    r_norm = _normalize_dict(researcher_r_raw)

    qr_details = {}
    for researcher_id, values in per_researcher_top_matches.items():
        sorted_matches = values["all_matches"]
        top_matches = values["top_matches"]
        q_value = researcher_q_raw[researcher_id]
        r_value = researcher_r_raw[researcher_id]

        paper_contributions = [
            {
                "paper_id": m["paper_id"],
                "title": m["title"],
                "year": m["year"],
                "similarity": round(m["similarity"], 6),
                "citations": int(float(m.get("citations") or 0.0)),
            }
            for m in top_matches
        ]

        top_1_share = (
            round(top_matches[0]["similarity"] / top_n, 6) if top_matches else 0.0
        )
        top_3_share = round(sum(m["similarity"] for m in top_matches[:3]) / top_n, 6)
        top_5_share = round(sum(m["similarity"] for m in top_matches[:5]) / top_n, 6)

        qr_details[researcher_id] = {
            "Q_raw": q_value,
            "Q_norm": q_norm.get(researcher_id, 0.0),
            "paper_matches": sorted_matches,
            "top_papers": top_matches[:3],
            "paper_count": len(sorted_matches),
            "R_raw": r_value,
            "R_norm": r_norm.get(researcher_id, 0.0),
            "contribution": {
                "paper_contributions": paper_contributions,
                "top_paper_share": top_1_share,
                "top_3_paper_share": top_3_share,
                "top_5_paper_share": top_5_share,
            },
        }

    return qr_details


def compute_q_weighted(
    query_text,
    cursor,
    candidate_researcher_ids=None,
    top_k=TOP_K_PINECONE,
    min_unique_researchers=MIN_UNIQUE_RESEARCHERS,
    max_top_k=MAX_TOP_K_PINECONE,
    target_papers_per_researcher=TARGET_PAPERS_PER_RESEARCHER,
    max_papers_per_researcher=Q_MAX_PAPERS_PER_RESEARCHER,
    top_n_papers=Q_TOP_PAPERS,
    start_year=None,
    end_year=None,
):
    if not query_text or not query_text.strip():
        return {}

    top_k = top_k if top_k is not None else TOP_K_PINECONE
    max_papers_per_researcher = (
        max_papers_per_researcher
        if max_papers_per_researcher is not None
        else Q_MAX_PAPERS_PER_RESEARCHER
    )

    query_embedding = embeddings.get_embeddings_batch([query_text])[0]
    if query_embedding is None:
        raise RuntimeError("Unable to compute query embedding for ranking")

    min_unique_researchers = (
        min_unique_researchers
        if min_unique_researchers is not None
        else MIN_UNIQUE_RESEARCHERS
    )
    max_top_k = max_top_k if max_top_k is not None else MAX_TOP_K_PINECONE
    target_papers_per_researcher = (
        target_papers_per_researcher
        if target_papers_per_researcher is not None
        else TARGET_PAPERS_PER_RESEARCHER
    )

    ranked_matches, debug_metadata = _fetch_diverse_ranked_matches(
        query_embedding=query_embedding,
        cursor=cursor,
        top_k=top_k,
        min_unique_researchers=min_unique_researchers,
        max_top_k=max_top_k,
        target_papers_per_researcher=target_papers_per_researcher,
    )

    pre_enrichment_depth = _summarize_match_depth(ranked_matches)
    debug_metadata.update(
        {
            "average_papers_per_researcher_before_enrichment": pre_enrichment_depth[
                "average_papers_per_researcher"
            ],
            "researchers_with_multiple_matches_before_enrichment": pre_enrichment_depth[
                "researchers_with_multiple_matches"
            ],
            "max_papers_for_any_researcher_before_enrichment": pre_enrichment_depth[
                "max_papers_for_any_researcher"
            ],
        }
    )

    researcher_ids_for_enrichment = []
    if target_papers_per_researcher > 1 and max_papers_per_researcher > 1:
        researcher_ids_for_enrichment = _select_researchers_for_depth_enrichment(
            ranked_matches=ranked_matches,
            limit=min_unique_researchers,
        )

    if researcher_ids_for_enrichment:
        ranked_matches, enrichment_metadata = _enrich_ranked_matches_for_researchers(
            query_embedding=query_embedding,
            cursor=cursor,
            ranked_matches=ranked_matches,
            researcher_ids=researcher_ids_for_enrichment,
            max_papers_per_researcher=max_papers_per_researcher,
        )
        debug_metadata.update(enrichment_metadata)
        debug_metadata["pinecone_match_count"] = len(ranked_matches)
        enriched_depth = _summarize_match_depth(ranked_matches)
        debug_metadata.update(enriched_depth)
    else:
        debug_metadata.update(
            {
                "depth_enrichment_enabled": False,
                "depth_enriched_researcher_count": 0,
                "depth_enriched_researcher_ids": [],
                "depth_enrichment_raw_match_count": 0,
                "depth_enrichment_added_unique_matches": 0,
            }
        )

    qr_details = _build_qr_details(
        ranked_matches=ranked_matches,
        candidate_researcher_ids=candidate_researcher_ids,
        top_n=top_n_papers,
        start_year=start_year,
        end_year=end_year,
    )
    debug_metadata["q_scored_researchers"] = len(qr_details)
    return qr_details, debug_metadata


def compute_r_from_q_details(q_details):
    """Build normalized R entries from Q details (R_raw already precomputed there)."""
    return {
        researcher_id: {
            "R_raw": entry.get("R_raw", 0.0),
            "R_norm": entry.get("R_norm", 0.0),
        }
        for researcher_id, entry in q_details.items()
    }


def load_mock_ranking_dataset(file_path):
    data = json.loads(Path(file_path).read_text())
    return {
        "researchers": data.get("researchers", []),
        "queries": data.get("queries", {}),
    }


def compute_q_weighted_from_mock(
    query_text,
    mock_dataset,
    candidate_researcher_ids=None,
    top_n_papers=Q_TOP_PAPERS,
    start_year=None,
    end_year=None,
):
    queries = mock_dataset.get("queries", {})
    ranked_matches = list(queries.get(query_text, []))

    q_details = _build_qr_details(
        ranked_matches=ranked_matches,
        candidate_researcher_ids=candidate_researcher_ids,
        top_n=top_n_papers,
        start_year=start_year,
        end_year=end_year,
    )
    debug_metadata = {
        "initial_top_k": len(ranked_matches),
        "final_top_k": len(ranked_matches),
        "pinecone_match_count": len(ranked_matches),
        "unique_researchers_found": len(
            {
                match.get("researcher_id")
                for match in ranked_matches
                if match.get("researcher_id")
            }
        ),
        "expansion_rounds": 1,
        "min_unique_researchers_target": None,
        "q_scored_researchers": len(q_details),
        "source": "mock",
    }
    return q_details, debug_metadata


def epsilon_pareto(
    candidate_metrics,
    epsilon=PARETO_EPSILON,
    require_k=PARETO_REQUIRE_K,
):
    if not candidate_metrics:
        return {"kept_ids": set(), "dominated_ids": set(), "dominated_by": {}}

    metric_names = list(next(iter(candidate_metrics.values())).keys())
    kept_ids = set(candidate_metrics.keys())
    dominated_by = {}

    for researcher_id in list(candidate_metrics.keys()):
        for challenger_id in candidate_metrics.keys():
            if researcher_id == challenger_id:
                continue

            researcher_values = candidate_metrics[researcher_id]
            challenger_values = candidate_metrics[challenger_id]
            weakly_better_all = True
            strongly_better_count = 0

            for metric_name in metric_names:
                challenger_value = challenger_values.get(metric_name, 0.0)
                researcher_value = researcher_values.get(metric_name, 0.0)
                if challenger_value < researcher_value:
                    weakly_better_all = False
                    break
                if challenger_value >= (1.0 + epsilon) * researcher_value:
                    strongly_better_count += 1

            if weakly_better_all and strongly_better_count >= require_k:
                kept_ids.discard(researcher_id)
                dominated_by[researcher_id] = challenger_id
                break

    dominated_ids = set(candidate_metrics.keys()) - kept_ids
    return {
        "kept_ids": kept_ids,
        "dominated_ids": dominated_ids,
        "dominated_by": dominated_by,
    }


def _driver_label(r_value, q_value):
    if r_value >= 0.7 and q_value >= 0.7:
        return "balanced"
    if q_value - r_value >= 0.15:
        return "relevance"
    if r_value - q_value >= 0.15:
        return "citation_activity"
    return "balanced"


def build_reason(researcher_row, h_entry, q_entry):
    r_value = h_entry.get("R_norm", 0.0)
    q_value = q_entry.get("Q_raw", 0.0)
    driver = _driver_label(r_value, q_value)

    highlights = []
    if q_value >= 0.7:
        highlights.append("strong semantic match to the query")
    elif q_value <= 0.3:
        highlights.append("weaker semantic match to the query")

    if r_value >= 0.7:
        highlights.append("strong citation activity during the selected time range")

    if not highlights:
        highlights.append("balanced impact and relevance signals")

    if driver == "balanced":
        summary = "Ranks well because both query relevance and citation activity during the selected time range are strong."
    elif driver == "relevance":
        summary = (
            "Ranks well mainly because the papers are a strong match to the query."
        )
    elif driver == "citation_activity":
        summary = "Ranks well mainly because citation impact is strong during the selected time range."
    else:
        summary = "Ranks well because query relevance and citation activity during the selected time range are balanced."

    top_papers = []
    for paper in q_entry.get("top_papers", []):
        top_papers.append(
            {
                "paper_id": paper.get("paper_id"),
                "title": paper.get("title"),
                "year": paper.get("year"),
                "similarity": round(paper.get("similarity", 0.0), 4),
            }
        )

    return {
        "primary_driver": driver,
        "summary": summary,
        "highlights": highlights,
        "top_papers": top_papers,
    }


def build_contribution_summary(q_entry):
    # Return a compact contribution summary: keep IDs, year and similarity only
    contribution = q_entry.get("contribution", {})
    paper_contributions = contribution.get("paper_contributions", [])
    return {
        "matched_paper_count": q_entry.get("paper_count", 0),
        "top_paper_share": round(contribution.get("top_paper_share", 0.0), 6),
        "top_3_paper_share": round(contribution.get("top_3_paper_share", 0.0), 6),
        "top_5_paper_share": round(contribution.get("top_5_paper_share", 0.0), 6),
        "paper_contributions": [
            {
                "paper_id": contribution_row.get("paper_id"),
                "title": contribution_row.get("title"),
                "year": contribution_row.get("year"),
                "similarity": round(contribution_row.get("similarity", 0.0), 6),
                "citations": contribution_row.get("citations"),
            }
            for contribution_row in paper_contributions[:10]
        ],
    }


def final_score(
    researcher_rows,
    r_scores,
    q_scores,
    r_weight=R_WEIGHT,
    q_weight=Q_WEIGHT,
    pareto_enabled=False,
    limit=None,
):
    r_weight = R_WEIGHT if r_weight is None else r_weight
    q_weight = Q_WEIGHT if q_weight is None else q_weight

    candidate_ids = {
        row["id"]
        for row in researcher_rows
        if row["id"] in r_scores and row["id"] in q_scores
    }
    row_by_id = {
        row["id"]: row for row in researcher_rows if row["id"] in candidate_ids
    }

    candidate_metrics = {
        researcher_id: {
            "R": r_scores[researcher_id]["R_norm"],
            "Q": q_scores[researcher_id].get("Q_norm", 0.0),
        }
        for researcher_id in candidate_ids
    }

    pareto_result = epsilon_pareto(candidate_metrics) if pareto_enabled else None
    kept_ids = pareto_result["kept_ids"] if pareto_result else candidate_ids

    ranked_results = []
    for researcher_id in kept_ids:
        researcher_row = row_by_id[researcher_id]
        r_entry = r_scores[researcher_id]
        q_entry = q_scores[researcher_id]
        r_value = r_entry.get("R_norm", 0.0)
        q_value = q_entry.get("Q_raw", 0.0)
        q_norm_value = q_entry.get("Q_norm", 0.0)
        score = r_weight * r_value + q_weight * q_norm_value

        ranked_results.append(
            {
                "researcher_id": researcher_id,
                "name": researcher_row.get("name"),
                "institution": researcher_row.get("institution_name"),
                "region": researcher_row.get("institution_region")
                or researcher_row.get("country"),
                "R": round(r_value, 6),
                "Q": round(q_value, 6),
                "final_score": round(score, 6),
                "reason": build_reason(researcher_row, r_entry, q_entry),
                "contribution": build_contribution_summary(q_entry),
                "components": {
                    "R_raw": round(r_entry.get("R_raw", 0.0), 6),
                    "matched_paper_count": q_entry.get("paper_count", 0),
                },
            }
        )

    ranked_results.sort(key=lambda row: row["final_score"], reverse=True)

    # Default cap: if no explicit limit provided, return only top 25 researchers
    if limit is None:
        effective_limit = 25
    else:
        effective_limit = limit

    if isinstance(effective_limit, int) and effective_limit >= 0:
        limited_results = ranked_results[:effective_limit]
    else:
        limited_results = ranked_results

    return {
        "results": limited_results,
        "pareto": {
            "enabled": pareto_enabled,
            "dominated_ids": (
                sorted(pareto_result["dominated_ids"]) if pareto_result else []
            ),
            "dominated_by": pareto_result["dominated_by"] if pareto_result else {},
        },
    }
