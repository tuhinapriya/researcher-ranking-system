"""Generate embeddings for papers and upsert to Pinecone.

Usage:
  python scripts/enrich.py

This script will:
 - find papers with non-empty abstract and missing `embedding_id`
 - batch the abstracts, call OpenAI embeddings, upsert to Pinecone
 - set `embedding_id` to the paper id after successful upsert

Requires `OPENAI_API_KEY` and Pinecone env vars in `researcher-kb-pipeline/config.py`.
"""

import os
import importlib.util
from typing import List, Tuple, Dict


def load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore
    return module


def main():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pkg_dir = os.path.join(base, "researcher-kb-pipeline")

    db_mod = load_module(os.path.join(pkg_dir, "db.py"), "phase1_db")
    models_mod = load_module(os.path.join(pkg_dir, "models.py"), "phase1_models")
    cfg = load_module(os.path.join(pkg_dir, "config.py"), "phase1_config")
    embeds = load_module(os.path.join(pkg_dir, "embeddings.py"), "phase1_embeds")

    engine = db_mod.get_engine(echo=False)
    Session = db_mod.get_session_factory(engine)

    batch_sz = cfg.EMBED_BATCH_SIZE

    with Session() as session:
        # simple query: papers with abstract and no embedding_id
        papers = (
            session.query(models_mod.Paper)
            .filter(models_mod.Paper.abstract != None)
            .filter(models_mod.Paper.embedding_id == None)
            .limit(1000)
            .all()
        )

        if not papers:
            print("No papers found needing embeddings.")
            return

        print(f"Found {len(papers)} papers needing embeddings; batching {batch_sz}.")

        for i in range(0, len(papers), batch_sz):
            batch = papers[i : i + batch_sz]
            texts = [p.abstract for p in batch]
            ids = [p.id for p in batch]

            vectors = embeds.embed_texts(texts, model=cfg.EMBED_MODEL)

            # prepare upsert tuples (id, vector, metadata)
            upsert_items: List[Tuple[str, List[float], Dict]] = []
            for pid, vec, paper in zip(ids, vectors, batch):
                meta = {"title": paper.title or "", "year": paper.year or ""}
                upsert_items.append((pid, vec, meta))

            embeds.pinecone_upsert(upsert_items, index_name=cfg.PINECONE_INDEX)

            # mark embedding_id on success
            for pid in ids:
                p = session.get(models_mod.Paper, pid)
                p.embedding_id = pid
                session.merge(p)
            session.commit()
            print(f"Upserted batch {i // batch_sz + 1} ({len(upsert_items)} vectors)")


if __name__ == "__main__":
    main()
