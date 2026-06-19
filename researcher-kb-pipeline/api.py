from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from search import default_mock_data_file, rank_researchers
from auth_routes import router as auth_router

app = FastAPI(title="Researcher Ranking API")

# Include auth and related routes so the API exposes /auth/* and other endpoints
app.include_router(auth_router)


class RankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    region: str | None = None
    institution_id: str | None = None
    author_name: str | None = None
    institution_name: str | None = None
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
@app.post("/rank")
def api_rank(request: RankRequest):
    try:
        return rank_researchers(
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class RebuildRequest(BaseModel):
    author_id: str


@app.post("/admin/rebuild-researcher")
def admin_rebuild(req: RebuildRequest):
    """Admin-only: rebuild a single researcher profile and upsert into DB.

    This uses the existing profile JSON under data/raw/profiles and the
    field_author_map.json entry to reconstruct and upsert the researcher row.
    """
    try:
        import stage4_assemble as s4
        from config import PROFILES_DIR, FIELD_AUTHOR_MAP_FILE
        from utils import load_json
        from db import get_connection

        author_id = req.author_id
        author_key = author_id
        field_map = load_json(FIELD_AUTHOR_MAP_FILE) or {}
        field_data = field_map.get(author_key)
        if not field_data:
            raise HTTPException(status_code=404, detail="author field data missing")

        profile_path = PROFILES_DIR + f"/{author_key}.json"
        profile = load_json(profile_path) or {}
        oa_profile = profile.get("openalex")
        s2_profile = profile.get("semantic_scholar")
        coauth = load_json(s4.COAUTHORS_DIR + f"/{author_key}.json") or {}

        # Build profile and upsert using stage4 helpers
        institution_cache = {}
        researcher = s4._build_profile(author_key, field_data, oa_profile, s2_profile, coauth, institution_cache)

        conn = get_connection()
        cur = conn.cursor()
        try:
            # Use internal upsert bundle to persist researcher + related rows
            s4._upsert_researcher_bundle(cur, researcher)
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return {"status": "ok", "author_id": author_key}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
