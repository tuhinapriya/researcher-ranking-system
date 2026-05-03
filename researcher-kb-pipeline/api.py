from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from search import default_mock_data_file, rank_researchers

app = FastAPI(title="Researcher Ranking API")


class RankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    region: str | None = None
    institution_id: str | None = None
    pareto_enabled: bool = False
    top_k: int | None = None
    min_unique_researchers: int | None = None
    max_top_k: int | None = None
    target_papers_per_researcher: float | None = None
    decay_lambda: float | None = None
    max_papers_per_researcher: int | None = None
    recency_lambda: float | None = None
    citation_beta: float | None = None
    use_mock_data: bool = False
    mock_data_file: str | None = None
    limit: int | None = None
    use_simple_ranking: bool = True


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/rank")
def api_rank(request: RankRequest):
    try:
        return rank_researchers(
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
