"""Simple ingestion script for Phase 1.

Reads JSON files from `researcher-kb-pipeline/data/raw/` and upserts into the
database defined by `DATABASE_URL` (falls back to local sqlite).

Outputs a list of `paper_id`s whose abstract changed or are new (these need embeddings).
"""

import os
import json
import glob
import hashlib
from typing import List, Set


def compute_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def load_module(path: str, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore
    return module


def main():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pkg_dir = os.path.join(base, "researcher-kb-pipeline")

    db_mod = load_module(os.path.join(pkg_dir, "db.py"), "phase1_db")
    models_mod = load_module(os.path.join(pkg_dir, "models.py"), "phase1_models")

    engine = db_mod.get_engine(echo=False)
    Session = db_mod.get_session_factory(engine)

    data_dir = os.path.join(pkg_dir, "data", "raw")
    profiles_dir = os.path.join(data_dir, "profiles")
    papers_dir = os.path.join(data_dir, "papers")

    new_or_changed_papers: Set[str] = set()

    with Session() as session:
        # Load profiles (researchers)
        for pfile in glob.glob(os.path.join(profiles_dir, "*.json")):
            try:
                with open(pfile, "r", encoding="utf-8") as fh:
                    pj = json.load(fh)
            except Exception:
                continue

            # Map some common fields; adopt defensive access
            author_id = pj.get("id") or pj.get("author_id") or pj.get("id")
            if not author_id:
                continue

            # Upsert Institution if present
            inst = None
            inst_data = pj.get("current_institution") or pj.get("institution")
            if inst_data and isinstance(inst_data, dict):
                inst_id = inst_data.get("id") or inst_data.get("institution_id")
                if inst_id:
                    inst = session.get(models_mod.Institution, inst_id)
                    if not inst:
                        inst = models_mod.Institution(id=inst_id)
                    inst.name = inst_data.get("name") or inst.name
                    inst.country = inst_data.get("country") or inst.country
                    inst.region = inst_data.get("region") or inst.region
                    session.merge(inst)

            # Upsert Researcher
            r = session.get(models_mod.Researcher, author_id)
            if not r:
                r = models_mod.Researcher(id=author_id)
            r.name = pj.get("display_name") or pj.get("name") or r.name
            r.total_works = (
                pj.get("works_count") or pj.get("total_works") or r.total_works
            )
            r.total_citations = pj.get("cited_by_count") or r.total_citations
            r.h_index = pj.get("h_index") or r.h_index
            r.current_institution_id = inst.id if inst else r.current_institution_id
            session.merge(r)

        session.commit()

        # Load papers from jsonl (each line is a JSON object)
        for pfile in glob.glob(os.path.join(papers_dir, "*.jsonl")):
            try:
                with open(pfile, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            pj = json.loads(line)
                        except Exception:
                            continue

                        paper_id = pj.get("id") or pj.get("paper_id")
                        if not paper_id:
                            continue

                        existing = session.get(models_mod.Paper, paper_id)
                        abstract = (
                            pj.get("abstract")
                            or pj.get("abstract_text")
                            or pj.get("summary")
                        )
                        needs_embedding = False

                        if not existing:
                            # create
                            paper = models_mod.Paper(id=paper_id)
                            paper.title = pj.get("title") or paper.title
                            paper.year = pj.get("year") or pj.get("publication_year")
                            paper.venue = pj.get("venue") or pj.get("journal")
                            paper.citations = pj.get("cited_by_count") or pj.get(
                                "citations"
                            )
                            paper.abstract = abstract
                            # try to find a primary author id
                            authors = pj.get("authors") or []
                            if isinstance(authors, list) and authors:
                                first = authors[0]
                                aid = None
                                if isinstance(first, dict):
                                    aid = first.get("id") or first.get("author_id")
                                elif isinstance(first, str):
                                    aid = first
                                if aid:
                                    paper.researcher_id = aid
                            session.add(paper)
                            needs_embedding = True if abstract else False
                        else:
                            # update if abstract changed or other fields updated
                            if abstract and (existing.abstract or "") != abstract:
                                existing.abstract = abstract
                                needs_embedding = True
                            # update simple metadata
                            existing.title = pj.get("title") or existing.title
                            existing.year = pj.get("year") or existing.year
                            existing.venue = pj.get("venue") or existing.venue
                            existing.citations = (
                                pj.get("cited_by_count") or existing.citations
                            )
                            session.merge(existing)

                        if needs_embedding:
                            new_or_changed_papers.add(paper_id)

                session.commit()
            except Exception:
                # keep going on file errors
                continue

    print("Ingestion complete.")
    print(f"Papers needing embeddings: {len(new_or_changed_papers)}")
    for pid in sorted(new_or_changed_papers):
        print(pid)


if __name__ == "__main__":
    main()
