import importlib
import sys
import types


def test_stage4_institutions_seen_fallback(monkeypatch):
    """When OA last_known_institutions is empty, institutions_seen should
    populate affiliation.current with non-empty name and country.
    """
    # Inject a lightweight fake `db` module to avoid MySQL / Pinecone deps
    fake_db = types.ModuleType("db")

    class PineconeUpsertError(Exception):
        pass

    fake_db.PineconeUpsertError = PineconeUpsertError
    fake_db.get_connection = lambda *a, **k: None
    fake_db.upsert_institution = lambda *a, **k: None
    fake_db.upsert_researcher = lambda *a, **k: None
    fake_db.upsert_papers = lambda *a, **k: None
    fake_db.upsert_topics = lambda *a, **k: None
    fake_db.upsert_collaborations = lambda *a, **k: None
    fake_db.fetch_papers_by_ids = lambda cursor, paper_ids: {}
    fake_db.fetch_windowed_citations_for_papers = (
        lambda cursor, paper_ids, start_year=None, end_year=None: {}
    )

    monkeypatch.setitem(sys.modules, "db", fake_db)

    # Import the module under test after injecting fake db
    stage4 = importlib.import_module("stage4_assemble")

    author_id = "A5087556046"
    field_data = {
        "name": "David Schuster",
        "concepts": {},
        "institutions_seen": {
            "https://openalex.org/I12345": {
                "id": "https://openalex.org/I12345",
                "name": "Test University",
                "type": "education",
                "country": "US",
            }
        },
    }

    # Empty OA and S2 profiles
    oa_profile = {}
    s2_profile = {}
    coauthor_data = {}
    institution_cache = {}

    researcher = stage4._build_profile(
        author_id, field_data, oa_profile, s2_profile, coauthor_data, institution_cache
    )

    aff = researcher.get("affiliation", {})
    current = aff.get("current")
    assert current and len(current) > 0, "affiliation.current must be populated"
    inst = current[0]
    assert inst.get("name"), "Institution name must not be empty"
    # country may be provided by institutions_seen; ensure non-empty if present
    assert inst.get("country") is not None and str(inst.get("country")).strip() != "", "Institution country must not be empty"
