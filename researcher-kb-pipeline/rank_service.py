import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from search import default_mock_data_file, rank_researchers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("rank_service")


app = FastAPI(title="Researcher Ranking Service")


class RankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    region: str | None = None
    institution_id: str | None = None
    pareto_enabled: bool = False
    top_k: int | None = Field(default=None, ge=1)
    min_unique_researchers: int | None = Field(default=None, ge=1)
    max_top_k: int | None = Field(default=None, ge=1)
    target_papers_per_researcher: float | None = Field(default=None, ge=1.0)
    decay_lambda: float | None = Field(default=None, ge=0.0)
    max_papers_per_researcher: int | None = Field(default=None, ge=1)
    recency_lambda: float | None = Field(default=None, ge=0.0)
    citation_beta: float | None = Field(default=None, ge=0.0)
    use_mock_data: bool = False
    mock_data_file: str | None = None
    limit: int | None = None
    use_simple_ranking: bool = True


class HealthResponse(BaseModel):
    status: str
    service: str


class TopPaperResponse(BaseModel):
    paper_id: str | None = None
    title: str | None = None
    year: int | None = None
    similarity: float | None = None
    weighted_contribution: float | None = None


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
    weighted_contribution: float | None = None
    share_of_q: float | None = None


class ContributionResponse(BaseModel):
    matched_paper_count: int
    top_paper_share: float
    top_3_paper_share: float
    top_5_paper_share: float
    paper_contributions: list[ContributionPaperResponse]


class ComponentsResponse(BaseModel):
    h_index: int | None = None
    total_citations: int | None = None
    quality_score: float | None = None
    recency_score: float | None = None
    seniority_score: float | None = None
    matched_paper_count: int


class RankResultResponse(BaseModel):
    researcher_id: str
    name: str | None = None
    institution: str | None = None
    region: str | None = None
    H: float
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


class ErrorResponse(BaseModel):
    detail: str


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


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="ranking")


@app.post(
    "/rank",
    response_model=RankResponse,
    responses={500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def rank(request: RankRequest) -> RankResponse:
    logger.info(
        "rank_request query=%s region=%s institution_id=%s use_mock_data=%s",
        request.query,
        request.region,
        request.institution_id,
        request.use_mock_data,
    )
    try:
        result = rank_researchers(
            query_text=request.query,
            region=request.region,
            institution_id=request.institution_id,
            pareto_enabled=request.pareto_enabled,
            top_k=request.top_k,
            min_unique_researchers=request.min_unique_researchers,
            max_top_k=request.max_top_k,
            target_papers_per_researcher=request.target_papers_per_researcher,
            decay_lambda=request.decay_lambda,
            max_papers_per_researcher=request.max_papers_per_researcher,
            recency_lambda=request.recency_lambda,
            citation_beta=request.citation_beta,
            limit=request.limit,
            mock_data_file=(
                request.mock_data_file or default_mock_data_file()
                if request.use_mock_data
                else None
            ),
            use_simple_ranking=request.use_simple_ranking,
        )
        logger.info(
            "rank_response query=%s returned=%s",
            request.query,
            len(result.get("results", [])),
        )
        return RankResponse.model_validate(result)
    except Exception as exc:
        logger.exception("rank_request_failed query=%s", request.query)
        raise HTTPException(
            status_code=_error_status_code(exc),
            detail=str(exc),
        ) from exc
