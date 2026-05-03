import logging
from pathlib import Path

from db import fetch_researcher_ranking_rows, get_connection
from ranking import (
    compute_h,
    compute_h_simple,
    compute_q_weighted,
    compute_q_weighted_from_mock,
    final_score,
    load_mock_ranking_dataset,
)
from config import USE_SIMPLE_RANKING


def rank_researchers(
    query_text,
    region=None,
    institution_id=None,
    pareto_enabled=False,
    top_k=None,
    min_unique_researchers=None,
    max_top_k=None,
    target_papers_per_researcher=None,
    decay_lambda=None,
    max_papers_per_researcher=None,
    recency_lambda=None,
    citation_beta=None,
    limit=None,
    mock_data_file=None,
    use_simple_ranking=None,
):
    if use_simple_ranking is None:
        use_simple_ranking = USE_SIMPLE_RANKING
    _compute_h = compute_h_simple if use_simple_ranking else compute_h
    if mock_data_file:
        mock_dataset = load_mock_ranking_dataset(mock_data_file)
        researcher_rows = list(mock_dataset.get("researchers", []))
        if region:
            researcher_rows = [
                row
                for row in researcher_rows
                if (row.get("institution_region") or row.get("country") or "").lower()
                == region.lower()
            ]
        if institution_id:
            researcher_rows = [
                row
                for row in researcher_rows
                if row.get("current_institution_id") == institution_id
            ]
        candidate_ids = [row["id"] for row in researcher_rows]
        q_scores, q_debug = compute_q_weighted_from_mock(
            query_text=query_text,
            mock_dataset=mock_dataset,
            candidate_researcher_ids=candidate_ids,
            decay_lambda=decay_lambda,
            max_papers_per_researcher=max_papers_per_researcher,
            recency_lambda=recency_lambda,
            citation_beta=citation_beta,
            use_simple_ranking=use_simple_ranking,
        )
        filtered_rows = [row for row in researcher_rows if row["id"] in q_scores]
        h_scores = _compute_h(filtered_rows)
        result = final_score(
            researcher_rows=filtered_rows,
            h_scores=h_scores,
            q_scores=q_scores,
            pareto_enabled=pareto_enabled,
            limit=limit,
        )
        result["debug"] = {
            **q_debug,
            "filters": {
                "region": region,
                "institution_id": institution_id,
            },
            "candidate_researchers_before_filter": len(candidate_ids),
            "candidate_researchers_after_filter": len(filtered_rows),
            "returned_researchers": len(result["results"]),
        }
        return result

    conn = get_connection()
    try:
        cursor = conn.cursor()
        q_scores, q_debug = compute_q_weighted(
            query_text=query_text,
            cursor=cursor,
            top_k=top_k if top_k is not None else None,
            min_unique_researchers=(
                min_unique_researchers if min_unique_researchers is not None else None
            ),
            max_top_k=max_top_k if max_top_k is not None else None,
            target_papers_per_researcher=(
                target_papers_per_researcher
                if target_papers_per_researcher is not None
                else None
            ),
            decay_lambda=decay_lambda if decay_lambda is not None else None,
            max_papers_per_researcher=(
                max_papers_per_researcher
                if max_papers_per_researcher is not None
                else None
            ),
            recency_lambda=recency_lambda if recency_lambda is not None else None,
            citation_beta=citation_beta if citation_beta is not None else None,
            use_simple_ranking=use_simple_ranking,
        )
        candidate_ids = list(q_scores.keys())
        researcher_rows = fetch_researcher_ranking_rows(
            cursor,
            researcher_ids=candidate_ids,
            region=region,
            institution_id=institution_id,
        )
        filtered_ids = {row["id"] for row in researcher_rows}
        q_scores = {
            researcher_id: entry
            for researcher_id, entry in q_scores.items()
            if researcher_id in filtered_ids
        }
        h_scores = _compute_h(researcher_rows)
        result = final_score(
            researcher_rows=researcher_rows,
            h_scores=h_scores,
            q_scores=q_scores,
            pareto_enabled=pareto_enabled,
            limit=limit,
        )
        result["debug"] = {
            **q_debug,
            "filters": {
                "region": region,
                "institution_id": institution_id,
            },
            "candidate_researchers_before_filter": len(candidate_ids),
            "candidate_researchers_after_filter": len(filtered_ids),
            "returned_researchers": len(result["results"]),
            "filtered_out_researchers": len(candidate_ids) - len(filtered_ids),
        }
        logging.info(
            "[Search] query=%s before_filter=%s after_filter=%s returned=%s region=%s institution_id=%s",
            query_text,
            len(candidate_ids),
            len(filtered_ids),
            len(result["results"]),
            region,
            institution_id,
        )
        return result
    finally:
        conn.close()


def default_mock_data_file():
    return str(Path(__file__).resolve().parent / "data" / "mock_ranking_data.json")
