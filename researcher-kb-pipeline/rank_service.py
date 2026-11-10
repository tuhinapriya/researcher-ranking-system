import logging
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

import auth_db
import fallback_ingest
from auth_routes import router as auth_router
from search import default_mock_data_file, rank_researchers
from db import fetch_researcher_ranking_rows, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("rank_service")


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        auth_db.init_auth_tables()
    except Exception as exc:  # pragma: no cover
        logger.warning("auth table init failed (DB may not be configured): %s", exc)
    try:
        _init_fallback_job_table()
        _mark_stale_fallback_jobs_interrupted()
        _resume_interrupted_fallback_jobs()
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "fallback job table init failed; using in-memory jobs only: %s", exc
        )
    yield


app = FastAPI(title="Researcher Ranking Service", lifespan=lifespan)
app.include_router(auth_router)


class RankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    region: str | None = None
    institution_id: str | None = None
    # Text-based filters resolved at the DB layer (post-Pinecone).
    # author_name: LIKE filter on researcher.name (used when frontend search_type=author).
    # institution_name: LIKE filter on institution.name (used when frontend search_type=institution).
    author_name: str | None = None
    institution_name: str | None = None
    # Frontend aliases: some clients send these names
    author_query: str | None = None
    institution_query: str | None = None
    topic_query: str | None = None
    start_year: int | None = Field(default=None, ge=0)
    end_year: int | None = Field(default=None, ge=0)
    pareto_enabled: bool = False
    top_k: int | None = Field(default=None, ge=1)
    min_unique_researchers: int | None = Field(default=None, ge=1)
    max_top_k: int | None = Field(default=None, ge=1)
    target_papers_per_researcher: float | None = Field(default=None, ge=1.0)
    max_papers_per_researcher: int | None = Field(default=None, ge=1)
    q_weight: float | None = Field(default=None, ge=0.0)
    r_weight: float | None = Field(default=None, ge=0.0)
    use_mock_data: bool = False
    mock_data_file: str | None = None
    limit: int | None = None

    @model_validator(mode="after")
    def validate_year_range(self):
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.start_year > self.end_year
        ):
            raise ValueError("start_year must be less than or equal to end_year")
        return self

    @model_validator(mode="after")
    def normalize_aliases(self):
        # Normalize frontend alias fields into canonical names used by the backend
        if not self.author_name and getattr(self, "author_query", None):
            self.author_name = getattr(self, "author_query")
        if not self.institution_name and getattr(self, "institution_query", None):
            self.institution_name = getattr(self, "institution_query")
        # topic_query maps to the main `query` when present and more specific
        if getattr(self, "topic_query", None) and (not self.query or self.query == ""):
            self.query = getattr(self, "topic_query")
        return self


class HealthResponse(BaseModel):
    status: str
    service: str


class TopPaperResponse(BaseModel):
    paper_id: str | None = None
    title: str | None = None
    year: int | None = None
    similarity: float | None = None


class ReasonResponse(BaseModel):
    primary_driver: str
    summary: str
    highlights: list[str]
    top_papers: list[TopPaperResponse]


class ContributionPaperResponse(BaseModel):
    paper_id: str | None = None
    title: str | None = None
    year: int | None = None
    similarity: float | None = None
    citations: int | None = None


class ContributionResponse(BaseModel):
    matched_paper_count: int
    top_paper_share: float
    top_3_paper_share: float
    top_5_paper_share: float
    paper_contributions: list[ContributionPaperResponse]


class ComponentsResponse(BaseModel):
    R_raw: float | None = None
    matched_paper_count: int


class RankResultResponse(BaseModel):
    researcher_id: str
    name: str | None = None
    institution: str | None = None
    region: str | None = None
    R: float
    Q: float
    final_score: float
    reason: ReasonResponse
    contribution: ContributionResponse
    components: ComponentsResponse


class ParetoResponse(BaseModel):
    enabled: bool
    dominated_ids: list[str]
    dominated_by: dict[str, str]


class RankResponse(BaseModel):
    results: list[RankResultResponse]
    pareto: ParetoResponse
    debug: dict[str, Any]
    results_found: bool | None = None
    fallback_available: bool | None = None
    fallback_type: str | None = None
    original_query: str | None = None
    search_type: str | None = None


class ErrorResponse(BaseModel):
    detail: str


class FallbackIngestRequest(BaseModel):
    query: str = Field(..., min_length=1)
    search_type: Literal["researcher", "institution", "topic"]


class FallbackIngestResponse(RankResponse):
    fallback_ingested: bool
    ingestion_status: str
    matched_openalex_entity: dict[str, Any] | None = None
    works_ingested: int = 0
    researchers_discovered: int = 0
    inserted_researchers: int = 0
    skipped_researchers: int = 0


class FallbackJobStartResponse(BaseModel):
    job_id: str
    status: str
    current_step: str
    message: str


class FallbackJobStatusResponse(BaseModel):
    job_id: str
    status: str
    current_step: str
    message: str
    steps: list[dict[str, Any]]
    query: str
    search_type: str
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


class FallbackJobCancelResponse(BaseModel):
    job_id: str
    status: str
    message: str


def _error_status_code(exc: Exception) -> int:
    message = str(exc)
    if isinstance(exc, ValueError):
        return 400
    if "Missing required database environment variables" in message:
        return 503
    if "Missing PINECONE_API_KEY" in message:
        return 503
    if "Unable to compute query embedding" in message:
        return 503
    return 500


def _search_type_from_rank_request(request: RankRequest) -> str | None:
    if request.author_name:
        return "researcher"
    if request.institution_name:
        return "institution"
    return "topic" if request.query else None


def _apply_empty_result_fallback_metadata(
    result: dict[str, Any],
    request: RankRequest,
) -> dict[str, Any]:
    if result.get("results"):
        return result
    result["results_found"] = False
    result["fallback_available"] = True
    result["fallback_type"] = "openalex_ingest"
    result["original_query"] = request.query
    result["search_type"] = _search_type_from_rank_request(request)
    return result


def _rank_kwargs_for_fallback(
    query: str,
    search_type: str,
    matched_entity_name: str | None = None,
    matched_entity_id: str | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"query_text": query}
    if search_type == "researcher":
        kwargs["author_name"] = matched_entity_name or query
        if matched_entity_id:
            kwargs["fallback_researcher_ids"] = [matched_entity_id]
    elif search_type == "institution":
        kwargs["institution_name"] = matched_entity_name or query
    return kwargs


FALLBACK_STEPS = [
    {"id": "queued", "label": "Preparing fallback search"},
    {
        "id": "fetching_entity",
        "label": "Fetching researcher/institution/topic information",
    },
    {"id": "fetching_works", "label": "Fetching publications and metadata"},
    {"id": "importing_metadata", "label": "Importing publications and metadata"},
    {"id": "processing_ranking", "label": "Processing and ranking results"},
    {"id": "complete", "label": "Done. Showing updated results."},
]
_fallback_jobs: dict[str, dict[str, Any]] = {}
_fallback_jobs_lock = Lock()


def _fallback_stale_seconds() -> int:
    raw_value = os.environ.get("FALLBACK_JOB_STALE_SECONDS", "3600")
    try:
        value = int(raw_value)
    except ValueError:
        value = 3600
    return max(300, min(value, 24 * 60 * 60))


def _fallback_auto_retry_enabled() -> bool:
    return os.environ.get(
        "FALLBACK_AUTO_RETRY_INTERRUPTED", "true"
    ).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _fallback_auto_retry_limit() -> int:
    raw_value = os.environ.get("FALLBACK_AUTO_RETRY_LIMIT", "3")
    try:
        value = int(raw_value)
    except ValueError:
        value = 3
    return max(0, min(value, 20))


def _init_fallback_job_table() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fallback_ingest_jobs (
                job_id           VARCHAR(64) PRIMARY KEY,
                query_text       TEXT        NOT NULL,
                search_type      VARCHAR(32) NOT NULL,
                status           VARCHAR(32) NOT NULL,
                current_step     VARCHAR(64) NOT NULL,
                message          TEXT        NOT NULL,
                steps_json       LONGTEXT    NOT NULL,
                checkpoint_json  LONGTEXT,
                result_json      LONGTEXT,
                error            TEXT,
                cancel_requested TINYINT(1)  NOT NULL DEFAULT 0,
                created_at       VARCHAR(32) NOT NULL,
                updated_at       VARCHAR(32) NOT NULL,
                INDEX idx_fallback_ingest_status (status),
                INDEX idx_fallback_ingest_updated (updated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        try:
            cursor.execute(
                "ALTER TABLE fallback_ingest_jobs ADD COLUMN checkpoint_json LONGTEXT"
            )
        except Exception as exc:
            if "Duplicate column" not in str(exc) and "1060" not in str(exc):
                raise
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _job_for_storage(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"thread"}}


def _persist_fallback_job(job: dict[str, Any]) -> None:
    try:
        stored_job = _job_for_storage(job)
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                REPLACE INTO fallback_ingest_jobs (
                    job_id, query_text, search_type, status, current_step, message,
                    steps_json, checkpoint_json, result_json, error, cancel_requested,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    stored_job["job_id"],
                    stored_job["query"],
                    stored_job["search_type"],
                    stored_job["status"],
                    stored_job["current_step"],
                    stored_job["message"],
                    json.dumps(stored_job["steps"]),
                    json.dumps(stored_job.get("checkpoint") or {}),
                    (
                        json.dumps(stored_job.get("result"))
                        if stored_job.get("result") is not None
                        else None
                    ),
                    stored_job.get("error"),
                    1 if stored_job.get("cancel_requested") else 0,
                    stored_job["created_at"],
                    stored_job["updated_at"],
                ),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "fallback_job_persist_failed job_id=%s: %s", job.get("job_id"), exc
        )


def _row_to_fallback_job(row: dict[str, Any]) -> dict[str, Any]:
    result_raw = row.get("result_json")
    return {
        "job_id": row["job_id"],
        "query": row["query_text"],
        "search_type": row["search_type"],
        "status": row["status"],
        "current_step": row["current_step"],
        "message": row["message"],
        "steps": json.loads(row.get("steps_json") or "[]"),
        "checkpoint": json.loads(row.get("checkpoint_json") or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "result": json.loads(result_raw) if result_raw else None,
        "error": row.get("error"),
        "cancel_requested": bool(row.get("cancel_requested")),
    }


def _load_persisted_fallback_job(job_id: str) -> dict[str, Any] | None:
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM fallback_ingest_jobs WHERE job_id = %s",
                (job_id,),
            )
            row = cursor.fetchone()
            return _row_to_fallback_job(row) if row else None
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:  # pragma: no cover
        logger.warning("fallback_job_load_failed job_id=%s: %s", job_id, exc)
        return None


def _set_persisted_cancel_requested(job_id: str) -> None:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE fallback_ingest_jobs
                SET cancel_requested = 1,
                    updated_at = %s,
                    status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                    message = CASE WHEN status = 'queued' THEN 'Search expansion cancelled.' ELSE message END
                WHERE job_id = %s
                """,
                (_utc_now(), job_id),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:  # pragma: no cover
        logger.warning("fallback_job_cancel_persist_failed job_id=%s: %s", job_id, exc)


def _mark_stale_fallback_jobs_interrupted() -> None:
    cutoff = (
        datetime.utcnow() - timedelta(seconds=_fallback_stale_seconds())
    ).isoformat(timespec="seconds") + "Z"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE fallback_ingest_jobs
            SET status = 'interrupted',
                message = 'Search expansion was interrupted. You can retry it.',
                error = 'Fallback job interrupted',
                updated_at = %s
            WHERE status IN ('queued', 'running')
              AND updated_at < %s
            """,
            (_utc_now(), cutoff),
        )
        conn.commit()
        if cursor.rowcount:
            logger.info("fallback_jobs_marked_interrupted count=%s", cursor.rowcount)
    finally:
        cursor.close()
        conn.close()


def _mark_fallback_job_interrupted(job_id: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE fallback_ingest_jobs
            SET status = 'interrupted',
                message = 'Search expansion was interrupted. You can retry it.',
                error = 'Fallback job interrupted',
                updated_at = %s
            WHERE job_id = %s
              AND status IN ('queued', 'running')
              AND cancel_requested = 0
            """,
            (_utc_now(), job_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _fresh_fallback_steps() -> list[dict[str, str]]:
    return [
        {
            **step,
            "status": "active" if step["id"] == "queued" else "pending",
        }
        for step in FALLBACK_STEPS
    ]


def _interrupted_fallback_job_ids(limit: int) -> list[str]:
    if limit <= 0:
        return []
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT job_id
            FROM fallback_ingest_jobs
            WHERE status = 'interrupted'
              AND cancel_requested = 0
            ORDER BY updated_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [row["job_id"] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def _claim_interrupted_fallback_job(job_id: str) -> dict[str, Any] | None:
    now = _utc_now()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE fallback_ingest_jobs
            SET status = 'queued',
                message = 'Resuming search expansion...',
                result_json = NULL,
                error = NULL,
                cancel_requested = 0,
                updated_at = %s
            WHERE job_id = %s
              AND status = 'interrupted'
              AND cancel_requested = 0
            """,
            (now, job_id),
        )
        conn.commit()
        if cursor.rowcount != 1:
            return None
    finally:
        cursor.close()
        conn.close()
    return _load_persisted_fallback_job(job_id)


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_fallback_job(query: str, search_type: str) -> dict[str, Any]:
    now = _utc_now()
    return {
        "job_id": str(uuid4()),
        "query": query,
        "search_type": search_type,
        "status": "queued",
        "current_step": "queued",
        "message": "Preparing fallback search...",
        "steps": _fresh_fallback_steps(),
        "created_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
        "cancel_requested": False,
        "checkpoint": {},
    }


def _set_fallback_job_progress(job_id: str, step_id: str, message: str) -> None:
    job_to_persist = None
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["current_step"] = step_id
        job["message"] = message
        job["updated_at"] = _utc_now()
        seen_current = False
        for step in job["steps"]:
            if step["id"] == step_id:
                step["status"] = "active"
                seen_current = True
            elif not seen_current:
                step["status"] = "complete"
            elif step["status"] != "complete":
                step["status"] = "pending"
        job_to_persist = _job_for_storage(job)
    if job_to_persist:
        _persist_fallback_job(job_to_persist)


def _finish_fallback_job(
    job_id: str,
    status: str,
    message: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    job_to_persist = None
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        if not job:
            return
        job["status"] = status
        job["message"] = message
        job["updated_at"] = _utc_now()
        job["result"] = result
        job["error"] = error
        if status == "complete":
            job["current_step"] = "complete"
            for step in job["steps"]:
                step["status"] = "complete"
        elif status == "cancelled":
            for step in job["steps"]:
                if step["status"] == "active":
                    step["status"] = "cancelled"
        elif status == "failed":
            for step in job["steps"]:
                if step["status"] == "active":
                    step["status"] = "failed"
        job_to_persist = _job_for_storage(job)
    if job_to_persist:
        _persist_fallback_job(job_to_persist)


def _update_fallback_job_checkpoint(
    job_id: str, checkpoint_update: dict[str, Any]
) -> None:
    job_to_persist = None
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        if not job:
            return
        checkpoint = dict(job.get("checkpoint") or {})
        for key, value in checkpoint_update.items():
            if value is None:
                checkpoint.pop(key, None)
            else:
                checkpoint[key] = value
        job["checkpoint"] = checkpoint
        job["updated_at"] = _utc_now()
        job_to_persist = _job_for_storage(job)
    if job_to_persist:
        _persist_fallback_job(job_to_persist)


def _fallback_job_cancel_requested(job_id: str) -> bool:
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        memory_cancelled = bool(job and job.get("cancel_requested"))
    if memory_cancelled:
        return True
    persisted_job = _load_persisted_fallback_job(job_id)
    return bool(persisted_job and persisted_job.get("cancel_requested"))


def _fallback_job_public(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key not in {"cancel_requested", "checkpoint", "thread"}
    }


def _get_fallback_job(job_id: str) -> dict[str, Any] | None:
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        if job:
            return _fallback_job_public(job)
    persisted_job = _load_persisted_fallback_job(job_id)
    if persisted_job and _persisted_fallback_job_needs_retry(persisted_job):
        _mark_fallback_job_interrupted(job_id)
        retried_job = _claim_interrupted_fallback_job(job_id)
        if retried_job:
            _start_fallback_job_thread(retried_job)
            logger.info(
                "fallback_job_retry_started job_id=%s query=%s search_type=%s",
                retried_job["job_id"],
                retried_job["query"],
                retried_job["search_type"],
            )
            return _fallback_job_public(retried_job)
    return _fallback_job_public(persisted_job) if persisted_job else None


def _persisted_fallback_job_needs_retry(job: dict[str, Any]) -> bool:
    if not _fallback_auto_retry_enabled():
        return False
    if job.get("status") not in {"queued", "running"}:
        return False
    if job.get("cancel_requested"):
        return False
    updated_at = str(job.get("updated_at") or "").replace("Z", "")
    try:
        last_update = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    age_seconds = (datetime.utcnow() - last_update).total_seconds()
    return age_seconds >= _fallback_stale_seconds()


def _start_fallback_job_thread(job: dict[str, Any]) -> None:
    job_id = job["job_id"]
    thread = Thread(target=_run_fallback_job, args=(job_id,), daemon=True)
    with _fallback_jobs_lock:
        _fallback_jobs[job_id] = job
        _fallback_jobs[job_id]["thread"] = thread
    thread.start()


def _resume_interrupted_fallback_jobs() -> None:
    if not _fallback_auto_retry_enabled():
        return
    for job_id in _interrupted_fallback_job_ids(_fallback_auto_retry_limit()):
        claimed_job = _claim_interrupted_fallback_job(job_id)
        if not claimed_job:
            continue
        _start_fallback_job_thread(claimed_job)
        logger.info(
            "fallback_job_retry_started job_id=%s query=%s search_type=%s",
            claimed_job["job_id"],
            claimed_job["query"],
            claimed_job["search_type"],
        )


def _run_fallback_job(job_id: str) -> None:
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
    if not job:
        job = _load_persisted_fallback_job(job_id)
        if not job:
            return
        with _fallback_jobs_lock:
            _fallback_jobs[job_id] = job
    query = job["query"]
    search_type = job["search_type"]

    try:
        if _fallback_job_cancel_requested(job_id):
            raise fallback_ingest.FallbackIngestionCancelled(
                "Fallback ingestion was cancelled"
            )
        ingest_result = fallback_ingest.ingest_from_openalex(
            query=query,
            search_type=search_type,
            progress_callback=lambda step, message: _set_fallback_job_progress(
                job_id, step, message
            ),
            cancel_check=lambda: _fallback_job_cancel_requested(job_id),
            checkpoint=job.get("checkpoint") or {},
            checkpoint_callback=lambda update: _update_fallback_job_checkpoint(
                job_id, update
            ),
        )
        if _fallback_job_cancel_requested(job_id):
            raise fallback_ingest.FallbackIngestionCancelled(
                "Fallback ingestion was cancelled"
            )
        _set_fallback_job_progress(
            job_id,
            "processing_ranking",
            "Processing and ranking results...",
        )
        rerun_result = rank_researchers(
            **_rank_kwargs_for_fallback(
                query,
                search_type,
                ingest_result.matched_entity_name,
                ingest_result.matched_entity_id,
            )
        )
        rerun_result["results_found"] = bool(rerun_result.get("results"))
        rerun_result["fallback_available"] = False
        rerun_result["fallback_type"] = "openalex_ingest"
        rerun_result["original_query"] = query
        rerun_result["search_type"] = search_type
        rerun_result["fallback_ingested"] = True
        rerun_result["ingestion_status"] = (
            "partial" if ingest_result.partial else "complete"
        )
        rerun_result["matched_openalex_entity"] = {
            "id": ingest_result.matched_entity_id,
            "name": ingest_result.matched_entity_name,
        }
        rerun_result["works_ingested"] = ingest_result.works_ingested
        rerun_result["researchers_discovered"] = ingest_result.researchers_discovered
        rerun_result["inserted_researchers"] = ingest_result.inserted_researchers
        rerun_result["skipped_researchers"] = ingest_result.skipped_researchers
        if search_type in {"researcher", "institution"}:
            rerun_result["fallback_matched_name_used"] = (
                ingest_result.matched_entity_name
            )
        _finish_fallback_job(
            job_id,
            "complete",
            "Done. Showing updated results.",
            result=rerun_result,
        )
    except fallback_ingest.FallbackIngestionCancelled as exc:
        logger.info("fallback_job_cancelled job_id=%s query=%s", job_id, query)
        _finish_fallback_job(job_id, "cancelled", "Search expansion cancelled.")
    except fallback_ingest.OpenAlexNoMatchError as exc:
        if _fallback_job_cancel_requested(job_id):
            logger.info(
                "fallback_job_cancelled_after_no_match job_id=%s query=%s",
                job_id,
                query,
            )
            _finish_fallback_job(job_id, "cancelled", "Search expansion cancelled.")
            return
        logger.warning(
            "fallback_job_no_match job_id=%s query=%s: %s", job_id, query, exc
        )
        _finish_fallback_job(job_id, "failed", str(exc), error=str(exc))
    except fallback_ingest.OpenAlexApiError as exc:
        if _fallback_job_cancel_requested(job_id):
            logger.info(
                "fallback_job_cancelled_after_openalex_failure job_id=%s query=%s",
                job_id,
                query,
            )
            _finish_fallback_job(job_id, "cancelled", "Search expansion cancelled.")
            return
        logger.warning(
            "fallback_job_openalex_failure job_id=%s query=%s: %s", job_id, query, exc
        )
        _finish_fallback_job(
            job_id,
            "failed",
            "OpenAlex or Semantic Scholar could not be reached. Please try again.",
            error="OpenAlex lookup failed",
        )
    except fallback_ingest.FallbackIngestionError as exc:
        if _fallback_job_cancel_requested(job_id):
            logger.info(
                "fallback_job_cancelled_after_ingestion_failure job_id=%s query=%s",
                job_id,
                query,
            )
            _finish_fallback_job(job_id, "cancelled", "Search expansion cancelled.")
            return
        logger.warning(
            "fallback_job_ingestion_failure job_id=%s query=%s: %s", job_id, query, exc
        )
        _finish_fallback_job(
            job_id,
            "failed",
            "Ingestion failed while importing the matched records. Please try again.",
            error="Fallback ingestion failed",
        )
    except Exception as exc:
        if _fallback_job_cancel_requested(job_id):
            logger.info(
                "fallback_job_cancelled_after_unexpected_failure job_id=%s query=%s",
                job_id,
                query,
            )
            _finish_fallback_job(job_id, "cancelled", "Search expansion cancelled.")
            return
        logger.exception(
            "fallback_job_unexpected_failure job_id=%s query=%s", job_id, query
        )
        _finish_fallback_job(
            job_id,
            "failed",
            "Fallback ingestion failed. Please try again.",
            error="Fallback ingestion failed",
        )


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="ranking")


@app.post(
    "/rank",
    response_model=RankResponse,
    responses={500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@app.post(
    "/api/rank",
    response_model=RankResponse,
    responses={500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def rank(request: RankRequest) -> RankResponse:
    logger.info(
        "rank_request query=%s region=%s institution_id=%s author_name=%s institution_name=%s use_mock_data=%s",
        request.query,
        request.region,
        request.institution_id,
        request.author_name,
        request.institution_name,
        request.use_mock_data,
    )
    try:
        result = rank_researchers(
            query_text=request.query,
            region=request.region,
            institution_id=request.institution_id,
            author_name=request.author_name,
            institution_name=request.institution_name,
            start_year=request.start_year,
            end_year=request.end_year,
            pareto_enabled=request.pareto_enabled,
            top_k=request.top_k,
            min_unique_researchers=request.min_unique_researchers,
            max_top_k=request.max_top_k,
            target_papers_per_researcher=request.target_papers_per_researcher,
            max_papers_per_researcher=request.max_papers_per_researcher,
            limit=request.limit,
            mock_data_file=(
                request.mock_data_file or default_mock_data_file()
                if request.use_mock_data
                else None
            ),
            q_weight=request.q_weight,
            r_weight=request.r_weight,
        )
        # Small, conservative safeguard: if the ranking pipeline returns
        # researchers but the top returned relevance (`Q`) is extremely low
        # we should prefer to surface the existing fallback flow rather than
        # show unrelated high-profile researchers. This is intentionally a
        # minimal change that does not touch the ranking algorithm itself.
        try:
            results_list = result.get("results") or []
            top_q = 0.0
            if results_list:
                top_q = max((r.get("Q") or 0.0) for r in results_list)
        except Exception:
            top_q = 0.0

        # Threshold is conservative: only trigger fallback for very low Q.
        MIN_TOP_Q_FOR_RESULTS = 0.05
        if results_list and top_q < MIN_TOP_Q_FOR_RESULTS:
            logger.info(
                "rank_response_low_relevance_trigger_fallback query=%s top_q=%.5f returned=%s",
                request.query,
                top_q,
                len(results_list),
            )
            # Clear results and mark fallback available so callers (frontend)
            # can run the existing fallback ingestion path.
            result["results"] = []
            return RankResponse.model_validate(_apply_empty_result_fallback_metadata(result, request))

        logger.info(
            "rank_response query=%s returned=%s",
            request.query,
            len(result.get("results", [])),
        )
        return RankResponse.model_validate(
            _apply_empty_result_fallback_metadata(result, request)
        )
    except Exception as exc:
        logger.exception("rank_request_failed query=%s", request.query)
        raise HTTPException(
            status_code=_error_status_code(exc),
            detail=str(exc),
        ) from exc


@app.post(
    "/search/fallback-ingest",
    response_model=FallbackIngestResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def search_fallback_ingest(
    request: FallbackIngestRequest,
) -> FallbackIngestResponse:
    logger.info(
        "fallback_ingest_request query=%s search_type=%s",
        request.query,
        request.search_type,
    )
    try:
        ingest_result = fallback_ingest.ingest_from_openalex(
            query=request.query,
            search_type=request.search_type,
        )
        rerun_result = rank_researchers(
            **_rank_kwargs_for_fallback(
                request.query,
                request.search_type,
                ingest_result.matched_entity_name,
                ingest_result.matched_entity_id,
            )
        )
        rerun_result["results_found"] = bool(rerun_result.get("results"))
        rerun_result["fallback_available"] = False
        rerun_result["fallback_type"] = "openalex_ingest"
        rerun_result["original_query"] = request.query
        rerun_result["search_type"] = request.search_type
        rerun_result["fallback_ingested"] = True
        rerun_result["ingestion_status"] = (
            "partial" if ingest_result.partial else "complete"
        )
        rerun_result["matched_openalex_entity"] = {
            "id": ingest_result.matched_entity_id,
            "name": ingest_result.matched_entity_name,
        }
        rerun_result["works_ingested"] = ingest_result.works_ingested
        rerun_result["researchers_discovered"] = ingest_result.researchers_discovered
        rerun_result["inserted_researchers"] = ingest_result.inserted_researchers
        rerun_result["skipped_researchers"] = ingest_result.skipped_researchers
        if request.search_type in {"researcher", "institution"}:
            rerun_result["fallback_matched_name_used"] = (
                ingest_result.matched_entity_name
            )
        logger.info(
            "fallback_ingest_response query=%s search_type=%s works_ingested=%s returned=%s status=%s",
            request.query,
            request.search_type,
            ingest_result.works_ingested,
            len(rerun_result.get("results", [])),
            rerun_result["ingestion_status"],
        )
        return FallbackIngestResponse.model_validate(rerun_result)
    except fallback_ingest.OpenAlexNoMatchError as exc:
        logger.warning(
            "fallback_ingest_no_match query=%s search_type=%s: %s",
            request.query,
            request.search_type,
            exc,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except fallback_ingest.OpenAlexApiError as exc:
        logger.warning(
            "fallback_ingest_openalex_failure query=%s search_type=%s: %s",
            request.query,
            request.search_type,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except fallback_ingest.FallbackIngestionError as exc:
        logger.warning(
            "fallback_ingest_internal_failure query=%s search_type=%s: %s",
            request.query,
            request.search_type,
            exc,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "fallback_ingest_unexpected_failure query=%s search_type=%s",
            request.query,
            request.search_type,
        )
        raise HTTPException(
            status_code=500, detail="Fallback ingestion failed"
        ) from exc


@app.post(
    "/search/fallback-ingest/jobs",
    response_model=FallbackJobStartResponse,
    responses={400: {"model": ErrorResponse}},
)
def start_fallback_ingest_job(
    request: FallbackIngestRequest,
) -> FallbackJobStartResponse:
    job = _new_fallback_job(request.query.strip(), request.search_type)
    job_id = job["job_id"]
    _persist_fallback_job(job)
    _start_fallback_job_thread(job)
    logger.info(
        "fallback_job_started job_id=%s query=%s search_type=%s",
        job_id,
        request.query,
        request.search_type,
    )
    return FallbackJobStartResponse(
        job_id=job_id,
        status=job["status"],
        current_step=job["current_step"],
        message=job["message"],
    )


@app.get(
    "/search/fallback-ingest/jobs/{job_id}",
    response_model=FallbackJobStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_fallback_ingest_job(job_id: str) -> FallbackJobStatusResponse:
    public_job = _get_fallback_job(job_id)
    if not public_job:
        raise HTTPException(status_code=404, detail="Fallback job not found")
    return FallbackJobStatusResponse.model_validate(public_job)


@app.post(
    "/search/fallback-ingest/jobs/{job_id}/cancel",
    response_model=FallbackJobCancelResponse,
    responses={404: {"model": ErrorResponse}},
)
def cancel_fallback_ingest_job(job_id: str) -> FallbackJobCancelResponse:
    response_status = "cancel_requested"
    response_message = "Search expansion cancelled."
    job_to_persist = None
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        if job:
            if job["status"] in {"complete", "failed", "cancelled"}:
                return FallbackJobCancelResponse(
                    job_id=job_id,
                    status=job["status"],
                    message=job["message"],
                )
            job["cancel_requested"] = True
            job["updated_at"] = _utc_now()
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["message"] = "Search expansion cancelled."
                response_status = "cancelled"
                response_message = job["message"]
            job_to_persist = _job_for_storage(job)
        else:
            persisted_job = _load_persisted_fallback_job(job_id)
            if not persisted_job:
                raise HTTPException(status_code=404, detail="Fallback job not found")
            if persisted_job["status"] in {"complete", "failed", "cancelled"}:
                return FallbackJobCancelResponse(
                    job_id=job_id,
                    status=persisted_job["status"],
                    message=persisted_job["message"],
                )
    logger.info("fallback_job_cancel_requested job_id=%s", job_id)
    if job_to_persist:
        _persist_fallback_job(job_to_persist)
    else:
        _set_persisted_cancel_requested(job_id)
    return FallbackJobCancelResponse(
        job_id=job_id,
        status=response_status,
        message=response_message,
    )


class ResearchersLookupRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=200)


class ResearcherProfileResponse(BaseModel):
    id: str
    name: str | None = None
    institution: str | None = None
    region: str | None = None
    total_works: int | None = None
    total_citations: int | None = None
    h_index: int | None = None
    i10_index: int | None = None
    years_active: int | None = None
    author_url: str | None = None
    country: str | None = None
    orcid_url: str | None = None
    semantic_scholar_url: str | None = None
    semantic_scholar_homepage: str | None = None
    institution_homepage: str | None = None
    trusted_links: list[dict[str, str]] | None = None


class ResearchersLookupResponse(BaseModel):
    researchers: list[ResearcherProfileResponse]


_RAW_PROFILE_DIR = Path(__file__).resolve().parent / "data" / "raw" / "profiles"


def _read_raw_profile(researcher_id: str) -> dict[str, Any]:
    if not researcher_id:
        return {}
    profile_path = _RAW_PROFILE_DIR / f"{researcher_id}.json"
    if not profile_path.exists():
        return {}
    try:
        with profile_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        logger.exception("failed_to_read_raw_profile researcher_id=%s", researcher_id)
        return {}


def _trusted_links_from_profile(row: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: str | None, label: str):
        clean = (url or "").strip()
        if not clean or clean in seen:
            return
        seen.add(clean)
        links.append({"url": clean, "label": label})

    add(row.get("author_url"), "Author Profile")
    add(row.get("orcid_url"), "ORCID")
    add(row.get("semantic_scholar_url"), "Semantic Scholar")
    add(row.get("semantic_scholar_homepage"), "Personal Website")
    add(row.get("institution_homepage"), "Institution Website")

    for link in row.get("trusted_links") or []:
        if isinstance(link, dict):
            add(link.get("url"), link.get("label") or "Website")

    return links


def _raw_profile_metadata(researcher_id: str) -> dict[str, Any]:
    profile = _read_raw_profile(researcher_id)
    openalex = profile.get("openalex") or {}
    semantic_scholar = profile.get("semantic_scholar") or {}

    author_url = openalex.get("id") or profile.get("author_id")
    orcid_url = openalex.get("orcid")
    semantic_scholar_url = semantic_scholar.get("url")
    semantic_scholar_homepage = semantic_scholar.get("homepage")

    metadata = {
        "author_url": author_url,
        "orcid_url": orcid_url,
        "semantic_scholar_url": semantic_scholar_url,
        "semantic_scholar_homepage": semantic_scholar_homepage,
        "trusted_links": _trusted_links_from_profile(
            {
                "author_url": author_url,
                "orcid_url": orcid_url,
                "semantic_scholar_url": semantic_scholar_url,
                "semantic_scholar_homepage": semantic_scholar_homepage,
                "institution_homepage": None,
            }
        ),
    }
    return {key: value for key, value in metadata.items() if value}


@app.post(
    "/researchers/lookup",
    response_model=ResearchersLookupResponse,
    responses={500: {"model": ErrorResponse}},
)
def researchers_lookup(request: ResearchersLookupRequest) -> ResearchersLookupResponse:
    """Return basic profile data for a list of researcher IDs (used for cross-device saved-researcher restoration)."""
    ids = request.ids[:100]  # Hard cap — defend against oversized requests
    conn = get_connection()
    try:
        cursor = conn.cursor()
        rows = fetch_researcher_ranking_rows(cursor, researcher_ids=ids)
        profiles = []
        for row in rows:
            raw_meta = _raw_profile_metadata(row.get("id"))
            merged = {**row, **raw_meta}
            profiles.append(
                ResearcherProfileResponse(
                    id=merged["id"],
                    name=merged.get("name"),
                    institution=merged.get("institution_name") or merged.get("institution"),
                    region=merged.get("institution_region") or merged.get("region"),
                    total_works=merged.get("total_works"),
                    total_citations=merged.get("total_citations"),
                    h_index=merged.get("h_index"),
                    i10_index=merged.get("i10_index"),
                    years_active=merged.get("years_active"),
                    author_url=merged.get("author_url"),
                    country=merged.get("country") or merged.get("institution_country"),
                    orcid_url=merged.get("orcid_url"),
                    semantic_scholar_url=merged.get("semantic_scholar_url"),
                    semantic_scholar_homepage=merged.get("semantic_scholar_homepage"),
                    institution_homepage=merged.get("institution_homepage"),
                    trusted_links=merged.get("trusted_links"),
                )
            )
        return ResearchersLookupResponse(researchers=profiles)
    except Exception as exc:
        logger.exception("researchers_lookup_failed ids_count=%s", len(ids))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()
