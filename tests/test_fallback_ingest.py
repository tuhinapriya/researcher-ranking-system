import importlib.util
import sys
import types
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = PROJECT_ROOT / "researcher-kb-pipeline"
sys.path.insert(0, str(PKG_DIR))


fastapi = types.ModuleType("fastapi")


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def include_router(self, router):
        pass

    def get(self, *args, **kwargs):
        return lambda fn: fn

    def post(self, *args, **kwargs):
        return lambda fn: fn


fastapi.FastAPI = _FastAPI
fastapi.HTTPException = _HTTPException
sys.modules["fastapi"] = fastapi


def _load_module(name):
    path = PKG_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


auth_db = types.ModuleType("auth_db")
auth_db.init_auth_tables = lambda: None
sys.modules["auth_db"] = auth_db

auth_routes = types.ModuleType("auth_routes")
auth_routes.router = None
sys.modules["auth_routes"] = auth_routes

rank_service = _load_module("rank_service")
fallback_ingest = sys.modules["fallback_ingest"]


def _rank_result(results):
    return {
        "results": results,
        "pareto": {"enabled": False, "dominated_ids": [], "dominated_by": {}},
        "debug": {},
    }


def test_local_search_returns_results_no_fallback(monkeypatch):
    monkeypatch.setattr(
        rank_service,
        "rank_researchers",
        lambda **kwargs: _rank_result(
            [
                {
                    "researcher_id": "A1",
                    "name": "Ada Lovelace",
                    "institution": "Example University",
                    "region": "US",
                    "R": 0.4,
                    "Q": 0.8,
                    "final_score": 0.66,
                    "reason": {
                        "primary_driver": "query match",
                        "summary": "matched",
                        "highlights": [],
                        "top_papers": [],
                    },
                    "contribution": {
                        "matched_paper_count": 1,
                        "top_paper_share": 1.0,
                        "top_3_paper_share": 1.0,
                        "top_5_paper_share": 1.0,
                        "paper_contributions": [],
                    },
                    "components": {"R_raw": 1.0, "matched_paper_count": 1},
                }
            ]
        ),
    )

    response = rank_service.rank(rank_service.RankRequest(query="Ada", author_name="Ada"))

    assert len(response.results) == 1
    assert response.fallback_available is None


def test_local_search_empty_marks_fallback_available(monkeypatch):
    monkeypatch.setattr(rank_service, "rank_researchers", lambda **kwargs: _rank_result([]))

    response = rank_service.rank(
        rank_service.RankRequest(query="Missing Lab", institution_name="Missing Lab")
    )

    assert response.results == []
    assert response.results_found is False
    assert response.fallback_available is True
    assert response.fallback_type == "openalex_ingest"
    assert response.original_query == "Missing Lab"
    assert response.search_type == "institution"


def test_fallback_ingest_calls_openalex_and_ingestion_logic(monkeypatch):
    calls = []

    def fake_ingest_from_openalex(query, search_type):
        calls.append(("ingest", query, search_type))
        return fallback_ingest.FallbackIngestResult(
            query=query,
            search_type=search_type,
            matched_entity_id="A123",
            matched_entity_name="Grace Hopper",
            works_ingested=3,
            researchers_discovered=1,
            inserted_researchers=1,
            skipped_researchers=0,
        )

    def fake_rank_researchers(**kwargs):
        calls.append(("rank", kwargs))
        return _rank_result([])

    monkeypatch.setattr(
        rank_service.fallback_ingest,
        "ingest_from_openalex",
        fake_ingest_from_openalex,
    )
    monkeypatch.setattr(rank_service, "rank_researchers", fake_rank_researchers)

    response = rank_service.search_fallback_ingest(
        rank_service.FallbackIngestRequest(query="Grace Hopper", search_type="researcher")
    )

    assert calls[0] == ("ingest", "Grace Hopper", "researcher")
    assert calls[1] == (
        "rank",
        {
            "query_text": "Grace Hopper",
            "author_name": "Grace Hopper",
            "fallback_researcher_ids": ["A123"],
        },
    )
    assert response.fallback_ingested is True
    assert response.ingestion_status == "complete"
    assert response.works_ingested == 3
    assert response.matched_openalex_entity == {"id": "A123", "name": "Grace Hopper"}


def test_fallback_rerun_uses_matched_openalex_name_for_author_filter(monkeypatch):
    rank_calls = []

    monkeypatch.setattr(
        rank_service.fallback_ingest,
        "ingest_from_openalex",
        lambda query, search_type: fallback_ingest.FallbackIngestResult(
            query=query,
            search_type=search_type,
            matched_entity_id="A123",
            matched_entity_name="Li Fei-Fei",
            works_ingested=3,
            researchers_discovered=1,
            inserted_researchers=1,
            skipped_researchers=0,
        ),
    )

    def fake_rank_researchers(**kwargs):
        rank_calls.append(kwargs)
        return _rank_result([])

    monkeypatch.setattr(rank_service, "rank_researchers", fake_rank_researchers)

    rank_service.search_fallback_ingest(
        rank_service.FallbackIngestRequest(query="Fei-Fei Li", search_type="researcher")
    )

    assert rank_calls[0]["query_text"] == "Fei-Fei Li"
    assert rank_calls[0]["author_name"] == "Li Fei-Fei"
    assert rank_calls[0]["fallback_researcher_ids"] == ["A123"]


def test_duplicate_fallback_ingestion_uses_idempotent_stage4(monkeypatch):
    stage4_calls = []
    author_map = {
        "A123": {
            "author_id": "A123",
            "author_id_url": "https://openalex.org/A123",
            "name": "Grace Hopper",
            "institutions_seen": {},
            "concepts": {},
        }
    }

    monkeypatch.setattr(
        fallback_ingest,
        "_search_openalex_entity",
        lambda query, search_type: {
            "id": "https://openalex.org/A123",
            "display_name": "Grace Hopper",
        },
    )
    monkeypatch.setattr(fallback_ingest, "_fetch_relevant_works", lambda entity, search_type: [{"id": "W1"}])
    monkeypatch.setattr(fallback_ingest, "_build_author_map", lambda entity, search_type, works: author_map)
    monkeypatch.setattr(fallback_ingest.stage3_enrich, "run_3a", lambda **kwargs: None)
    monkeypatch.setattr(fallback_ingest.stage3_enrich, "run_3b", lambda **kwargs: None)
    monkeypatch.setattr(fallback_ingest.stage3_enrich, "run_3c", lambda **kwargs: None)

    def fake_stage4_run(**kwargs):
        stage4_calls.append(kwargs["author_map_override"])
        return {
            "inserted_researchers": 1,
            "skipped_researchers": 0,
            "knowledge_base_size": 1,
        }

    monkeypatch.setattr(fallback_ingest.stage4_assemble, "run", fake_stage4_run)

    first = fallback_ingest.ingest_from_openalex("Grace Hopper", "researcher")
    second = fallback_ingest.ingest_from_openalex("Grace Hopper", "researcher")

    assert first.matched_entity_id == "A123"
    assert second.matched_entity_id == "A123"
    assert len(stage4_calls) == 2
    assert stage4_calls[0] is author_map
    assert stage4_calls[1] is author_map


def test_resume_interrupted_fallback_jobs_retries_claimed_jobs(monkeypatch):
    started = []

    def fake_claim(job_id):
        return {
            "job_id": job_id,
            "query": "Grace Hopper",
            "search_type": "researcher",
            "status": "queued",
        }

    monkeypatch.setattr(rank_service, "_fallback_auto_retry_enabled", lambda: True)
    monkeypatch.setattr(rank_service, "_fallback_auto_retry_limit", lambda: 2)
    monkeypatch.setattr(rank_service, "_interrupted_fallback_job_ids", lambda limit: ["job-1", "job-2"])
    monkeypatch.setattr(rank_service, "_claim_interrupted_fallback_job", fake_claim)
    monkeypatch.setattr(rank_service, "_start_fallback_job_thread", lambda job: started.append(job["job_id"]))

    rank_service._resume_interrupted_fallback_jobs()

    assert started == ["job-1", "job-2"]


def test_get_fallback_job_retries_stale_persisted_running_job(monkeypatch):
    started = []
    marked = []
    stale_job = {
        "job_id": "job-3",
        "query": "Grace Hopper",
        "search_type": "researcher",
        "status": "running",
        "current_step": "fetching_works",
        "message": "Fetching publications and metadata...",
        "steps": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "result": None,
        "error": None,
        "cancel_requested": False,
    }
    claimed_job = {**stale_job, "status": "queued", "message": "Resuming search expansion..."}

    with rank_service._fallback_jobs_lock:
        rank_service._fallback_jobs.clear()

    monkeypatch.setattr(rank_service, "_fallback_auto_retry_enabled", lambda: True)
    monkeypatch.setattr(rank_service, "_fallback_stale_seconds", lambda: 30)
    monkeypatch.setattr(rank_service, "_load_persisted_fallback_job", lambda job_id: stale_job)
    monkeypatch.setattr(rank_service, "_mark_fallback_job_interrupted", lambda job_id: marked.append(job_id))
    monkeypatch.setattr(rank_service, "_claim_interrupted_fallback_job", lambda job_id: claimed_job)
    monkeypatch.setattr(rank_service, "_start_fallback_job_thread", lambda job: started.append(job["job_id"]))

    public_job = rank_service._get_fallback_job("job-3")

    assert marked == ["job-3"]
    assert started == ["job-3"]
    assert public_job["message"] == "Resuming search expansion..."


def test_work_page_resume_continues_from_checkpoint_cursor(monkeypatch):
    requested_cursors = []
    checkpoint_updates = []

    def fake_openalex_get(url, params=None, timeout=None):
        requested_cursors.append(params["cursor"])
        return {
            "results": [{"id": "https://openalex.org/W2", "title": "Second"}],
            "meta": {"next_cursor": None},
        }

    def fake_process_papers(works, concept_label, author_map, allowed_author_ids=None):
        author_map["A2"] = {"name": works[0]["title"]}

    monkeypatch.setattr(fallback_ingest, "openalex_get", fake_openalex_get)
    monkeypatch.setattr(fallback_ingest, "_paper_record_from_work", lambda work, cancel_check=None: work)
    monkeypatch.setattr(fallback_ingest, "_process_papers", fake_process_papers)
    monkeypatch.setattr(fallback_ingest, "_finalize_author_map", lambda author_map: author_map)

    author_map, works_count = fallback_ingest._fetch_author_map_from_work_pages(
        {"id": "https://openalex.org/A1", "display_name": "Grace Hopper"},
        "researcher",
        checkpoint={
            "works_cursor": "cursor-2",
            "works_processed_count": 1,
            "completed_work_ids": ["W1"],
            "author_map": {"A1": {"name": "First"}},
        },
        checkpoint_callback=lambda update: checkpoint_updates.append(update),
    )

    assert requested_cursors == ["cursor-2"]
    assert works_count == 2
    assert set(author_map) == {"A1", "A2"}
    assert checkpoint_updates[-1]["stage"] == "author_map_complete"


def test_ingest_resume_starts_stage4_after_committed_author_index(monkeypatch):
    stage4_calls = []
    final_author_map = {
        f"A{i}": {"author_id": f"A{i}", "name": f"Researcher {i}"}
        for i in range(3)
    }

    monkeypatch.setattr(fallback_ingest.stage3_enrich, "run_3a", lambda **kwargs: None)
    monkeypatch.setattr(fallback_ingest.stage3_enrich, "run_3b", lambda **kwargs: None)
    monkeypatch.setattr(fallback_ingest.stage3_enrich, "run_3c", lambda **kwargs: None)

    def fake_stage4_run(**kwargs):
        stage4_calls.append(kwargs)
        kwargs["checkpoint_callback"](3, 3)
        return {
            "inserted_researchers": 1,
            "skipped_researchers": 0,
            "knowledge_base_size": 3,
        }

    monkeypatch.setattr(fallback_ingest.stage4_assemble, "run", fake_stage4_run)

    result = fallback_ingest.ingest_from_openalex(
        "Grace Hopper",
        "researcher",
        checkpoint={
            "entity": {
                "id": "https://openalex.org/A1",
                "display_name": "Grace Hopper",
            },
            "final_author_map": final_author_map,
            "works_processed_count": 3,
            "stage3_completed": ["cache_institution", "run_3a", "run_3b", "run_3c"],
            "stage4_completed_authors": 2,
        },
        checkpoint_callback=lambda update: None,
    )

    assert result.works_ingested == 3
    assert result.researchers_discovered == 3
    assert stage4_calls[0]["start_index"] == 2


def test_async_job_reports_cancelled_when_openalex_fails_after_cancel(monkeypatch):
    finishes = []
    cancel_checks = iter([False, True])

    with rank_service._fallback_jobs_lock:
        rank_service._fallback_jobs["job-cancel-race"] = {
            "job_id": "job-cancel-race",
            "query": "Chelsea Finn",
            "search_type": "researcher",
            "status": "running",
            "current_step": "fetching_entity",
            "message": "Fetching researcher information from OpenAlex...",
            "steps": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "result": None,
            "error": None,
            "cancel_requested": False,
            "checkpoint": {},
        }

    monkeypatch.setattr(rank_service, "_set_fallback_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(rank_service, "_update_fallback_job_checkpoint", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        rank_service,
        "_fallback_job_cancel_requested",
        lambda job_id: next(cancel_checks),
    )
    monkeypatch.setattr(
        rank_service.fallback_ingest,
        "ingest_from_openalex",
        lambda **kwargs: (_ for _ in ()).throw(
            fallback_ingest.OpenAlexApiError("OpenAlex lookup failed")
        ),
    )
    monkeypatch.setattr(
        rank_service,
        "_finish_fallback_job",
        lambda job_id, status, message, result=None, error=None: finishes.append(
            (job_id, status, message)
        ),
    )

    rank_service._run_fallback_job("job-cancel-race")

    assert finishes == [
        ("job-cancel-race", "cancelled", "Search expansion cancelled.")
    ]
