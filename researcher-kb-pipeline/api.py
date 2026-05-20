from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from search import default_mock_data_file, rank_researchers

app = FastAPI(title="Researcher Ranking API")


class RankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    region: str | None = None
    institution_id: str | None = None
    start_year: int | None = Field(default=None, ge=0)
    end_year: int | None = Field(default=None, ge=0)
    pareto_enabled: bool = False
    top_k: int | None = None
    min_unique_researchers: int | None = None
    max_top_k: int | None = None
    target_papers_per_researcher: float | None = None
    max_papers_per_researcher: int | None = None
    q_weight: float | None = None
    r_weight: float | None = None
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
