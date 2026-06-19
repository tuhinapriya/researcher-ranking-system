import pytest

import db


class FakeCursor:
    def __init__(self):
        self.exec_calls = []
        self.executemany_calls = []

    def execute(self, sql, params=None):
        self.exec_calls.append((sql, params))

    def executemany(self, sql, rows):
        self.executemany_calls.append((sql, rows))

    def fetchall(self):
        return []

    @property
    def description(self):
        return []


def test_upsert_papers_handles_missing_embeddings():
    cursor = FakeCursor()
    researcher_id = "A_TEST"
    # Single paper without abstract -> no embeddings produced
    papers_by_concept = {
        "physics": [
            {
                "id": "https://openalex.org/W1",
                "title": "Test Paper",
                "abstract": None,
                "year": 2020,
                "venue": "Journal",
                "citations": 0,
                "counts_by_year": [],
            }
        ]
    }

    # Should not raise
    db.upsert_papers(cursor, researcher_id, papers_by_concept)

    # At least one execute call for inserting the paper should have happened
    assert any("INSERT INTO papers" in (call[0] or "") for call in cursor.exec_calls)
