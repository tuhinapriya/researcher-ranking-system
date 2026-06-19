import types
import pytest

import stage4_assemble as s4


class FakeCursor:
    def __init__(self):
        self.commands = []

    def execute(self, sql):
        self.commands.append(sql)

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.committed = False
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        pass


def test_researcher_persisted_when_papers_fail(monkeypatch):
    # Prepare a minimal researcher bundle
    researcher = {
        "researcher_id": "A1",
        "name": "Test Researcher",
        "affiliation": {"current": [{"id": "I1", "name": "Inst"}]},
        "global_metrics": {},
        "lab_and_mentorship": {},
        "papers_by_concept": {},
    }

    # Track calls
    calls = {"upsert_institution": 0, "upsert_researcher": 0, "upsert_papers": 0}

    def fake_upsert_institution(cur, inst):
        calls["upsert_institution"] += 1

    def fake_upsert_researcher(cur, res):
        calls["upsert_researcher"] += 1

    def fake_upsert_papers(cur, researcher_id, papers_by_concept):
        calls["upsert_papers"] += 1
        raise RuntimeError("simulated paper upsert failure")

    fake_conn = FakeConn()

    # get_connection should return our fake connection for the separate commits
    monkeypatch.setattr(s4, "get_connection", lambda: fake_conn)
    monkeypatch.setattr(s4, "upsert_institution", fake_upsert_institution)
    monkeypatch.setattr(s4, "upsert_researcher", fake_upsert_researcher)
    monkeypatch.setattr(s4, "upsert_papers", fake_upsert_papers)
    monkeypatch.setattr(s4, "upsert_topics", lambda *a, **k: None)
    monkeypatch.setattr(s4, "upsert_collaborations", lambda *a, **k: None)

    main_cursor = FakeCursor()

    inserted, skipped = s4._upsert_batch(main_cursor, [researcher], 0, 0)

    # researcher upsert should have been called and committed on the separate conn
    assert calls["upsert_researcher"] == 1
    assert fake_conn.committed is True

    # Because paper upsert failed, the batch logic should mark this researcher as skipped
    assert inserted == 0
    assert skipped == 1


if __name__ == "__main__":
    print("Run with pytest")
