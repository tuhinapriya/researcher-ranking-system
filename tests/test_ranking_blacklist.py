import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = PROJECT_ROOT / "researcher-kb-pipeline"
sys.path.insert(0, str(PKG_DIR))

import ranking


def test_final_score_filters_known_generic_ai_names():
    researcher_rows = [
        {"id": "good-1", "name": "Alice Cancer Imaging", "institution_name": "Cancer Center", "institution_region": "North America", "country": "US"},
        {"id": "bad-1", "name": "Alex Krizhevsky", "institution_name": "University of Toronto", "institution_region": "North America", "country": "CA"},
        {"id": "bad-2", "name": "Geoffrey E. Hinton", "institution_name": "University of Toronto", "institution_region": "North America", "country": "CA"},
        {"id": "bad-3", "name": "Raquel Urtasun", "institution_name": "University of Toronto", "institution_region": "North America", "country": "CA"},
    ]

    r_scores = {
        "good-1": {"R_raw": 0.8, "R_norm": 0.8},
        "bad-1": {"R_raw": 0.7, "R_norm": 0.7},
        "bad-2": {"R_raw": 0.6, "R_norm": 0.6},
        "bad-3": {"R_raw": 0.5, "R_norm": 0.5},
    }
    q_scores = {
        "good-1": {"Q_raw": 0.9, "Q_norm": 0.9, "paper_count": 2, "top_papers": [], "contribution": {}},
        "bad-1": {"Q_raw": 0.7, "Q_norm": 0.7, "paper_count": 2, "top_papers": [], "contribution": {}},
        "bad-2": {"Q_raw": 0.65, "Q_norm": 0.65, "paper_count": 2, "top_papers": [], "contribution": {}},
        "bad-3": {"Q_raw": 0.6, "Q_norm": 0.6, "paper_count": 2, "top_papers": [], "contribution": {}},
    }

    result = ranking.final_score(researcher_rows, r_scores, q_scores, limit=10)
    names = [item["name"] for item in result["results"]]

    assert "Alice Cancer Imaging" in names
    assert "Alex Krizhevsky" not in names
    assert "Geoffrey E. Hinton" not in names
    assert "Raquel Urtasun" not in names
