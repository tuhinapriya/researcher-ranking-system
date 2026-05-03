"""Small helper to create Phase 1 tables locally.

Usage:
    python scripts/create_tables.py

Set `DATABASE_URL` to a Postgres/Cloud SQL URI to create in your DB.
"""

import os
import sys
import importlib.util


def load_db_module():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_path = os.path.join(base, "researcher-kb-pipeline", "db.py")
    spec = importlib.util.spec_from_file_location("phase1_db", db_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore
    return module


def main():
    db_module = load_db_module()
    engine = db_module.get_engine(echo=True)
    print("Creating tables using", engine.url)
    db_module.create_tables(engine)
    print("Done")


if __name__ == "__main__":
    main()
