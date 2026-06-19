import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Literal

import stage3_enrich
import stage4_assemble
from config import INSTITUTIONS_DIR, OPENALEX_BASE, ensure_dirs
from stage2_extract import _finalize_author_map, _process_papers
from utils import (
    extract_id,
    fetch_s2_abstract,
    openalex_get,
    reconstruct_abstract,
    save_json,
)

logger = logging.getLogger("fallback_ingest")

SearchType = Literal["researcher", "institution", "topic"]


class OpenAlexNoMatchError(RuntimeError):
    pass


class OpenAlexApiError(RuntimeError):
    pass


class FallbackIngestionError(RuntimeError):
    pass


class FallbackIngestionCancelled(RuntimeError):
    pass


@dataclass
class FallbackIngestResult:
    query: str
    search_type: SearchType
    matched_entity_id: str
    matched_entity_name: str | None
    works_ingested: int
    researchers_discovered: int
    inserted_researchers: int
    skipped_researchers: int
    partial: bool = False


ProgressCallback = Callable[[str, str], None]
CancelCheck = Callable[[], bool]
CheckpointCallback = Callable[[dict[str, Any]], None]


def _max_works() -> int:
    raw_value = os.environ.get("FALLBACK_INGEST_MAX_WORKS", "50")
    try:
        value = int(raw_value)
    except ValueError:
        value = 50
    return max(1, min(value, 200))


def _works_batch_size() -> int:
    raw_value = os.environ.get("FALLBACK_INGEST_BATCH_SIZE", "25")
    try:
        value = int(raw_value)
    except ValueError:
        value = 25
    return max(1, min(value, 100))


def _openalex_timeout() -> int:
    raw_value = os.environ.get("FALLBACK_OPENALEX_TIMEOUT_SECONDS", "15")
    try:
        value = int(raw_value)
    except ValueError:
        value = 15
    return max(3, min(value, 30))


def _s2_timeout() -> int:
    raw_value = os.environ.get("FALLBACK_S2_TIMEOUT_SECONDS", "10")
    try:
        value = int(raw_value)
    except ValueError:
        value = 10
    return max(3, min(value, 20))


def _normalize_search_type(search_type: str) -> SearchType:
    normalized = (search_type or "").strip().lower()
    aliases = {"author": "researcher"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"researcher", "institution", "topic"}:
        raise ValueError("search_type must be researcher, institution, or topic")
    return normalized  # type: ignore[return-value]


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise FallbackIngestionCancelled("Fallback ingestion was cancelled")


def _report_progress(
    progress_callback: ProgressCallback | None,
    step: str,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(step, message)


def _save_checkpoint(
    checkpoint_callback: CheckpointCallback | None,
    **updates: Any,
) -> None:
    if checkpoint_callback is not None:
        checkpoint_callback(updates)


def _search_openalex_entity(
    query: str,
    search_type: SearchType,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    endpoint_by_type = {
        "researcher": "authors",
        "institution": "institutions",
        "topic": "topics",
    }
    endpoint = endpoint_by_type[search_type]
    url = f"{OPENALEX_BASE}/{endpoint}"
    _raise_if_cancelled(cancel_check)
    _report_progress(
        progress_callback,
        "fetching_entity",
        f"Fetching {search_type} information from OpenAlex...",
    )
    try:
        data = openalex_get(
            url,
            params={
                "search": query,
                "per_page": 1,
            },
            timeout=_openalex_timeout(),
        )
        _raise_if_cancelled(cancel_check)
    except Exception as exc:
        logger.exception(
            "fallback_openalex_entity_search_failed query=%s search_type=%s",
            query,
            search_type,
        )
        raise OpenAlexApiError("OpenAlex lookup failed") from exc

    matches = data.get("results") or []
    if not matches:
        raise OpenAlexNoMatchError("No matching OpenAlex entity found")
    return matches[0]


def _works_filter_for_entity(entity: dict[str, Any], search_type: SearchType) -> str:
    entity_id = extract_id(entity.get("id"))
    if not entity_id:
        raise OpenAlexNoMatchError("Matched OpenAlex entity is missing an id")
    if search_type == "researcher":
        return f"author.id:{entity_id}"
    if search_type == "institution":
        return f"institutions.id:{entity_id}"
    return f"primary_topic.id:{entity_id}"


def _paper_record_from_work(
    work: dict[str, Any],
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    _raise_if_cancelled(cancel_check)
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if not abstract:
        abstract = fetch_s2_abstract(
            doi=work.get("doi"),
            title=work.get("title"),
            timeout=_s2_timeout(),
        )
        _raise_if_cancelled(cancel_check)
    return {
        "id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title"),
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
        "counts_by_year": work.get("counts_by_year", []),
        "abstract": abstract,
        "authorships": work.get("authorships", []),
        "primary_topic": work.get("primary_topic"),
        "topics": work.get("topics", []),
        "grants": work.get("grants", []),
        "primary_location": work.get("primary_location"),
        "type": work.get("type"),
    }


def _fetch_relevant_works(
    entity: dict[str, Any],
    search_type: SearchType,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> list[dict[str, Any]]:
    works = []
    cursor = "*"
    max_works = _max_works()
    batch_size = _works_batch_size()
    filter_str = _works_filter_for_entity(entity, search_type)
    _report_progress(
        progress_callback,
        "fetching_works",
        "Fetching publications and metadata...",
    )
    while len(works) < max_works:
        _raise_if_cancelled(cancel_check)
        try:
            data = openalex_get(
                f"{OPENALEX_BASE}/works",
                params={
                    "filter": filter_str,
                    "per_page": min(batch_size, max_works - len(works)),
                    "sort": "cited_by_count:desc",
                    "cursor": cursor,
                },
                timeout=_openalex_timeout(),
            )
            _raise_if_cancelled(cancel_check)
        except Exception as exc:
            logger.exception(
                "fallback_openalex_works_fetch_failed entity_id=%s search_type=%s",
                extract_id(entity.get("id")),
                search_type,
            )
            raise OpenAlexApiError("OpenAlex works lookup failed") from exc

        batch = data.get("results") or []
        if not batch:
            break
        for work in batch:
            works.append(_paper_record_from_work(work, cancel_check=cancel_check))
            _raise_if_cancelled(cancel_check)
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
    return works


def _build_author_map(
    entity: dict[str, Any],
    search_type: SearchType,
    works: list[dict[str, Any]],
) -> dict[str, Any]:
    author_map: dict[str, Any] = {}
    allowed_author_ids = None
    if search_type == "researcher":
        allowed_author_ids = {extract_id(entity.get("id"))}

    concept_label = entity.get("display_name") or f"Fallback {search_type}"
    _process_papers(
        works,
        concept_label,
        author_map,
        allowed_author_ids=allowed_author_ids,
    )
    return _finalize_author_map(author_map)


def _fetch_author_map_from_work_pages(
    entity: dict[str, Any],
    search_type: SearchType,
    checkpoint: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    checkpoint_callback: CheckpointCallback | None = None,
) -> tuple[dict[str, Any], int]:
    checkpoint = checkpoint or {}
    raw_author_map: dict[str, Any] = checkpoint.get("author_map") or {}
    completed_work_ids = list(checkpoint.get("completed_work_ids") or [])
    completed_work_id_set = set(completed_work_ids)
    processed_count = int(checkpoint.get("works_processed_count") or len(completed_work_ids))
    cursor = checkpoint.get("works_cursor") or "*"
    max_works = _max_works()
    batch_size = _works_batch_size()
    filter_str = _works_filter_for_entity(entity, search_type)
    allowed_author_ids = None
    if search_type == "researcher":
        allowed_author_ids = {extract_id(entity.get("id"))}
    concept_label = entity.get("display_name") or f"Fallback {search_type}"

    _report_progress(
        progress_callback,
        "fetching_works",
        "Fetching publications and metadata...",
    )
    while processed_count < max_works:
        _raise_if_cancelled(cancel_check)
        try:
            data = openalex_get(
                f"{OPENALEX_BASE}/works",
                params={
                    "filter": filter_str,
                    "per_page": min(batch_size, max_works - processed_count),
                    "sort": "cited_by_count:desc",
                    "cursor": cursor,
                },
                timeout=_openalex_timeout(),
            )
            _raise_if_cancelled(cancel_check)
        except Exception as exc:
            logger.exception(
                "fallback_openalex_works_fetch_failed entity_id=%s search_type=%s",
                extract_id(entity.get("id")),
                search_type,
            )
            raise OpenAlexApiError("OpenAlex works lookup failed") from exc

        batch = data.get("results") or []
        if not batch:
            _save_checkpoint(
                checkpoint_callback,
                stage="works_complete",
                works_cursor=None,
                works_processed_count=processed_count,
                completed_work_ids=completed_work_ids,
                author_map=raw_author_map,
            )
            break

        batch_records = []
        batch_work_ids = []
        for work in batch:
            work_id = extract_id(work.get("id")) or work.get("id")
            if work_id and work_id in completed_work_id_set:
                continue
            batch_records.append(_paper_record_from_work(work, cancel_check=cancel_check))
            if work_id:
                batch_work_ids.append(work_id)
            _raise_if_cancelled(cancel_check)

        if batch_records:
            _process_papers(
                batch_records,
                concept_label,
                raw_author_map,
                allowed_author_ids=allowed_author_ids,
            )
            for work_id in batch_work_ids:
                if work_id not in completed_work_id_set:
                    completed_work_id_set.add(work_id)
                    completed_work_ids.append(work_id)
            processed_count += len(batch_records)

        cursor = data.get("meta", {}).get("next_cursor")
        _save_checkpoint(
            checkpoint_callback,
            stage="fetching_works",
            works_cursor=cursor,
            works_processed_count=processed_count,
            completed_work_ids=completed_work_ids,
            author_map=raw_author_map,
        )
        if not cursor:
            break

    final_author_map = _finalize_author_map(raw_author_map)
    _save_checkpoint(
        checkpoint_callback,
        stage="author_map_complete",
        final_author_map=final_author_map,
        works_cursor=cursor,
        works_processed_count=processed_count,
        completed_work_ids=completed_work_ids,
    )
    return final_author_map, processed_count


def _cache_matched_institution(entity: dict[str, Any], search_type: SearchType) -> None:
    if search_type != "institution":
        return
    institution_id = extract_id(entity.get("id"))
    if not institution_id:
        return
    ensure_dirs()
    save_json(entity, os.path.join(INSTITUTIONS_DIR, f"{institution_id}.json"))


def ingest_from_openalex(
    query: str,
    search_type: str,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    checkpoint: dict[str, Any] | None = None,
    checkpoint_callback: CheckpointCallback | None = None,
) -> FallbackIngestResult:
    normalized_type = _normalize_search_type(search_type)
    clean_query = query.strip()
    checkpoint = checkpoint or {}
    if not clean_query:
        raise ValueError("query is required")

    logger.info(
        "fallback_ingest_start query=%s search_type=%s", clean_query, normalized_type
    )
    _raise_if_cancelled(cancel_check)
    if checkpoint.get("entity"):
        entity = checkpoint["entity"]
    elif progress_callback is None and cancel_check is None and checkpoint_callback is None:
        entity = _search_openalex_entity(clean_query, normalized_type)
    else:
        entity = _search_openalex_entity(
            clean_query,
            normalized_type,
            progress_callback,
            cancel_check,
        )
        _save_checkpoint(
            checkpoint_callback,
            stage="entity_complete",
            entity=entity,
            entity_id=extract_id(entity.get("id")),
            entity_name=entity.get("display_name"),
        )
    entity_id = extract_id(entity.get("id")) or ""
    entity_name = entity.get("display_name")
    logger.info(
        "fallback_ingest_matched_entity query=%s search_type=%s entity_id=%s entity_name=%s",
        clean_query,
        normalized_type,
        entity_id,
        entity_name,
    )

    if checkpoint.get("final_author_map"):
        author_map = checkpoint["final_author_map"]
        works_count = int(checkpoint.get("works_processed_count") or 0)
        _report_progress(
            progress_callback,
            "importing_metadata",
            "Importing publications and metadata...",
        )
    elif progress_callback is None and cancel_check is None and checkpoint_callback is None:
        works = _fetch_relevant_works(entity, normalized_type)
        works_count = len(works)
        if not works:
            raise OpenAlexNoMatchError("No OpenAlex works found for matched entity")
        _raise_if_cancelled(cancel_check)
        _report_progress(
            progress_callback,
            "importing_metadata",
            "Importing publications and metadata...",
        )
        author_map = _build_author_map(entity, normalized_type, works)
    else:
        author_map, works_count = _fetch_author_map_from_work_pages(
            entity,
            normalized_type,
            checkpoint,
            progress_callback,
            cancel_check,
            checkpoint_callback,
        )
    if works_count <= 0:
        raise OpenAlexNoMatchError("No OpenAlex works found for matched entity")

    _raise_if_cancelled(cancel_check)
    if not author_map:
        raise OpenAlexNoMatchError("No eligible education-institution researchers found")

    try:
        _raise_if_cancelled(cancel_check)
        if "cache_institution" not in set(checkpoint.get("stage3_completed") or []):
            _cache_matched_institution(entity, normalized_type)
            completed = list(checkpoint.get("stage3_completed") or [])
            completed.append("cache_institution")
            checkpoint["stage3_completed"] = completed
            _save_checkpoint(
                checkpoint_callback,
                stage="importing_metadata",
                stage3_completed=completed,
            )
        _report_progress(
            progress_callback,
            "importing_metadata",
            "Importing author profiles and institution metadata...",
        )
        completed_stage3 = set(checkpoint.get("stage3_completed") or [])
        stage3_steps = [
            ("run_3a", stage3_enrich.run_3a),
            ("run_3b", stage3_enrich.run_3b),
            ("run_3c", stage3_enrich.run_3c),
        ]
        for stage_name, stage_func in stage3_steps:
            if stage_name in completed_stage3:
                continue
            stage_func(force=False, author_map_override=author_map)
            _raise_if_cancelled(cancel_check)
            completed_stage3.add(stage_name)
            _save_checkpoint(
                checkpoint_callback,
                stage="importing_metadata",
                stage3_completed=list(completed_stage3),
            )
        _report_progress(
            progress_callback,
            "importing_metadata",
            "Storing imported records and embeddings...",
        )
        stage4_start_index = int(checkpoint.get("stage4_completed_authors") or 0)
        stage4_cancel_check = None
        if cancel_check is not None:
            def stage4_cancel_check() -> bool:
                _raise_if_cancelled(cancel_check)
                return False
        if stage4_start_index >= len(author_map):
            stage4_summary = {
                "inserted_researchers": 0,
                "skipped_researchers": 0,
                "knowledge_base_size": len(author_map),
            }
        else:
            stage4_summary = stage4_assemble.run(
                force=False,
                author_map_override=author_map,
                export_artifacts=False,
                cancel_check=stage4_cancel_check,
                start_index=stage4_start_index,
                checkpoint_callback=lambda completed, total: _save_checkpoint(
                    checkpoint_callback,
                    stage="stage4_writing",
                    stage4_completed_authors=completed,
                    stage4_total_authors=total,
                ),
            )
        _save_checkpoint(
            checkpoint_callback,
            stage="stage4_complete",
            stage4_completed_authors=len(author_map),
            stage4_total_authors=len(author_map),
        )
    except FallbackIngestionCancelled:
        logger.info(
            "fallback_ingest_cancelled query=%s search_type=%s entity_id=%s",
            clean_query,
            normalized_type,
            entity_id,
        )
        raise
    except Exception as exc:
        logger.exception(
            "fallback_ingest_failed query=%s search_type=%s entity_id=%s",
            clean_query,
            normalized_type,
            entity_id,
        )
        raise FallbackIngestionError("Fallback ingestion failed") from exc

    inserted = int((stage4_summary or {}).get("inserted_researchers") or 0)
    skipped = int((stage4_summary or {}).get("skipped_researchers") or 0)
    partial = skipped > 0
    logger.info(
        "fallback_ingest_complete query=%s search_type=%s entity_id=%s works_ingested=%s researchers=%s inserted=%s skipped=%s partial=%s",
        clean_query,
        normalized_type,
        entity_id,
        works_count,
        len(author_map),
        inserted,
        skipped,
        partial,
    )
    return FallbackIngestResult(
        query=clean_query,
        search_type=normalized_type,
        matched_entity_id=entity_id,
        matched_entity_name=entity_name,
        works_ingested=works_count,
        researchers_discovered=len(author_map),
        inserted_researchers=inserted,
        skipped_researchers=skipped,
        partial=partial,
    )
