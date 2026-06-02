import logging
from pathlib import Path

from db import fetch_researcher_ranking_rows, get_connection
from ranking import (
    compute_r_from_q_details,
    compute_q_weighted,
    compute_q_weighted_from_mock,
    final_score,
    load_mock_ranking_dataset,
)


def rank_researchers(
    query_text,
    region=None,
    institution_id=None,
    author_name=None,
    institution_name=None,
    pareto_enabled=False,
    top_k=None,
    min_unique_researchers=None,
    max_top_k=None,
    target_papers_per_researcher=None,
    max_papers_per_researcher=None,
    limit=None,
    mock_data_file=None,
    q_weight=None,
    r_weight=None,
    start_year=None,
    end_year=None,
):
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
        # Author-name and institution-name text filters (mock data path).
        if author_name:
            author_name_lower = author_name.lower()
            researcher_rows = [
                row
                for row in researcher_rows
                if author_name_lower in (row.get("name") or "").lower()
            ]
        if institution_name:
            institution_name_lower = institution_name.lower()
            researcher_rows = [
                row
                for row in researcher_rows
                if institution_name_lower
                in (row.get("institution_name") or row.get("institution") or "").lower()
            ]
        candidate_ids = [row["id"] for row in researcher_rows]
        q_scores, q_debug = compute_q_weighted_from_mock(
            query_text=query_text,
            mock_dataset=mock_dataset,
            candidate_researcher_ids=candidate_ids,
            start_year=start_year,
            end_year=end_year,
        )
        filtered_rows = [row for row in researcher_rows if row["id"] in q_scores]
        r_scores = compute_r_from_q_details(q_scores)
        result = final_score(
            researcher_rows=filtered_rows,
            r_scores=r_scores,
            q_scores=q_scores,
            q_weight=q_weight,
            r_weight=r_weight,
            pareto_enabled=pareto_enabled,
            limit=limit,
        )
        result["debug"] = {
            **q_debug,
            "filters": {
                "region": region,
                "institution_id": institution_id,
                "author_name": author_name,
                "institution_name": institution_name,
                "start_year": start_year,
                "end_year": end_year,
            },
            "candidate_researchers_before_filter": len(candidate_ids),
            "candidate_researchers_after_filter": len(filtered_rows),
            "returned_researchers": len(result["results"]),
        }
        return result

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # ── DB-first candidate resolution for author/institution mode ───────────
        # When the user is searching by author name or institution name the query
        # text is not a semantic document — it is a person/organisation name.
        # Running it through Pinecone first means that only researchers whose paper
        # abstracts happen to be similar to the name string will survive, silently
        # dropping exact matches.  To fix this, fetch all matching researcher IDs
        # from MySQL first and pass them as forced_researcher_ids so their papers
        # are retrieved from Pinecone via per-researcher metadata-filter queries.
        forced_researcher_ids = None
        pre_fetched_researcher_rows = None
        if author_name or institution_name:
            pre_fetched_researcher_rows = fetch_researcher_ranking_rows(
                cursor,
                author_name=author_name,
                institution_name=institution_name,
                region=region,
                institution_id=institution_id,
            )
            forced_researcher_ids = [row["id"] for row in pre_fetched_researcher_rows]
            logging.info(
                "[Search] DB-first author/institution lookup: author_name=%s institution_name=%s found=%s",
                author_name,
                institution_name,
                len(forced_researcher_ids),
            )

        q_scores, q_debug = compute_q_weighted(
            query_text=query_text,
            cursor=cursor,
            forced_researcher_ids=forced_researcher_ids,
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
            max_papers_per_researcher=(
                max_papers_per_researcher
                if max_papers_per_researcher is not None
                else None
            ),
            start_year=start_year,
            end_year=end_year,
        )

        # For author/institution mode we already have the filtered DB rows; reuse
        # them to avoid a redundant query.  For topic mode run the standard DB
        # fetch constrained to whatever Pinecone returned.
        if pre_fetched_researcher_rows is not None:
            researcher_rows = [
                row for row in pre_fetched_researcher_rows if row["id"] in q_scores
            ]
            filtered_ids = {row["id"] for row in researcher_rows}
            q_scores = {
                researcher_id: entry
                for researcher_id, entry in q_scores.items()
                if researcher_id in filtered_ids
            }
        else:
            candidate_ids = list(q_scores.keys())
            researcher_rows = fetch_researcher_ranking_rows(
                cursor,
                researcher_ids=candidate_ids,
                region=region,
                institution_id=institution_id,
                author_name=author_name,
                institution_name=institution_name,
            )
            filtered_ids = {row["id"] for row in researcher_rows}
            q_scores = {
                researcher_id: entry
                for researcher_id, entry in q_scores.items()
                if researcher_id in filtered_ids
            }
        r_scores = compute_r_from_q_details(q_scores)
        result = final_score(
            researcher_rows=researcher_rows,
            r_scores=r_scores,
            q_scores=q_scores,
            q_weight=q_weight,
            r_weight=r_weight,
            pareto_enabled=pareto_enabled,
            limit=limit,
        )
        candidates_before = len(forced_researcher_ids or []) or len(q_scores)
        result["debug"] = {
            **q_debug,
            "filters": {
                "region": region,
                "institution_id": institution_id,
                "author_name": author_name,
                "institution_name": institution_name,
                "start_year": start_year,
                "end_year": end_year,
            },
            "candidate_researchers_before_filter": candidates_before,
            "candidate_researchers_after_filter": len(filtered_ids),
            "returned_researchers": len(result["results"]),
            "filtered_out_researchers": candidates_before - len(filtered_ids),
        }
        logging.info(
            "[Search] query=%s before_filter=%s after_filter=%s returned=%s region=%s institution_id=%s author_name=%s institution_name=%s",
            query_text,
            candidates_before,
            len(filtered_ids),
            len(result["results"]),
            region,
            institution_id,
            author_name,
            institution_name,
        )
        return result
    finally:
        conn.close()


def default_mock_data_file():
    return str(Path(__file__).resolve().parent / "data" / "mock_ranking_data.json")
