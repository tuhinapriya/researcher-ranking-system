#!/usr/bin/env python3
import sys
import os
import importlib.util
import json
from pathlib import Path

base = Path(__file__).resolve().parent.parent
pkg_dir = base / "researcher-kb-pipeline"

sys.path.insert(0, str(pkg_dir))


def load_module(name, fname):
    path = pkg_dir / fname
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_db():
    print("[DB] Loading db module...")
    try:
        db = load_module("db", "db.py")
    except Exception as e:
        print("[DB] Failed to load db module:", e)
        return None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        print("[DB] Connected. Querying for author_name LIKE 'David Schuster'...")
        rows = db.fetch_researcher_ranking_rows(cursor, author_name="David Schuster")
        print(f"[DB] Found {len(rows)} rows")
        if rows:
            print(json.dumps(rows[:5], indent=2))
        conn.close()
        return rows
    except Exception as e:
        print("[DB] DB query failed:", e)
        return None


def check_pinecone(db_rows):
    print("[PINECONE] Attempting to load pinecone_client module...")
    try:
        pine = load_module("pinecone_client", "pinecone_client.py")
    except Exception as e:
        print("[PINECONE] Failed to load pinecone_client:", e)
        return None
    # If no DB rows, we may still try a name-based metadata filter if possible
    ids = [row.get("id") for row in (db_rows or []) if row.get("id")]
    if not ids:
        print(
            "[PINECONE] No researcher IDs from DB to check. Skipping researcher-id checks."
        )
        return None
    results = {}
    for rid in ids:
        print(f"[PINECONE] Checking for researcher_id={rid}")
        try:
            vec = [0.0] * getattr(pine, "DIMENSION", 768)
            # Try query with filter on metadata researcher_id
            try:
                res = pine.index.query(
                    vector=vec, top_k=1, filter={"researcher_id": {"$eq": rid}}
                )
                results[rid] = res
                print(f"[PINECONE] Query result keys: {list(res.keys())}")
            except Exception as qerr:
                # Try without $eq
                try:
                    res = pine.index.query(
                        vector=vec, top_k=1, filter={"researcher_id": rid}
                    )
                    results[rid] = res
                    print(f"[PINECONE] Query result keys (alt): {list(res.keys())}")
                except Exception as qerr2:
                    print(f"[PINECONE] Query failed for {rid}:", qerr, qerr2)
                    results[rid] = None
        except Exception as e:
            print("[PINECONE] Error building/querying vector:", e)
            results[rid] = None
    return results


if __name__ == "__main__":
    print("Diagnostic started for David Schuster")
    db_rows = check_db()
    pine_results = check_pinecone(db_rows)
    print("\n--- SUMMARY ---")
    print("DB rows:", len(db_rows) if isinstance(db_rows, list) else db_rows)
    if pine_results is None:
        print("Pinecone: not checked or unavailable")
    else:
        for k, v in pine_results.items():
            print(f"Pinecone researcher_id={k} -> present={'yes' if v else 'no'}")
