"""Migration tool to detect and optionally fix non-ASCII/unsafe paper and embedding IDs.

Usage:
  python3 scripts/migrate_sanitize_ids.py --dry-run
  python3 scripts/migrate_sanitize_ids.py --apply  # requires DB and PINECONE creds

This script performs a dry-run scan by default and will only modify data
when run with `--apply`. It logs original -> sanitized mappings and is
conservative: it aborts if collisions are detected that could break references.
"""

import argparse
import importlib.util
import logging
import os
import sys
from typing import List, Dict, Tuple


def _load_module_from_repo(path_parts, mod_name: str):
    base = os.path.dirname(__file__)
    full = os.path.normpath(os.path.join(base, "..", *path_parts))
    spec = importlib.util.spec_from_file_location(mod_name, full)
    mod = importlib.util.module_from_spec(spec)
    # Temporarily ensure the module's directory on sys.path so internal imports like `config` resolve
    module_dir = os.path.dirname(full)
    inserted = False
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
        inserted = True
    try:
        spec.loader.exec_module(mod)
    finally:
        if inserted:
            try:
                sys.path.remove(module_dir)
            except ValueError:
                pass
    return mod


# Load project modules by path so this script can run from repo root
try:
    db_mod = _load_module_from_repo(["researcher-kb-pipeline", "db.py"], "db_mod")
except Exception as e:
    db_mod = None
    logging.warning("Could not load DB module: %s", e)

try:
    pinecone_mod = _load_module_from_repo(
        ["researcher-kb-pipeline", "pinecone_client.py"], "pinecone_mod"
    )
except Exception as e:
    pinecone_mod = None
    logging.warning("Could not load Pinecone client module: %s", e)

try:
    utils_mod = _load_module_from_repo(
        ["researcher-kb-pipeline", "utils.py"], "utils_mod"
    )
except Exception as e:
    utils_mod = None
    logging.error("Could not load utils module: %s", e)
    raise

logging.basicConfig(level=logging.INFO)


def scan_papers(cursor) -> List[Dict]:
    """Return list of paper rows as dicts from DB."""
    sql = "SELECT id, researcher_id, title, year, venue, abstract, embedding_id FROM papers"
    cursor.execute(sql)
    rows = []
    for r in cursor.fetchall():
        rows.append(
            {
                "id": r[0],
                "researcher_id": r[1],
                "title": r[2],
                "year": r[3],
                "venue": r[4],
                "abstract": r[5],
                "embedding_id": r[6],
            }
        )
    return rows


def find_unsafe(rows: List[Dict]) -> List[Dict]:
    """Return subset of rows where id or embedding_id is not ASCII-safe."""
    affected = []
    for r in rows:
        id_ok = utils_mod.is_ascii_safe_identifier(r.get("id") or "")
        emb_ok = utils_mod.is_ascii_safe_identifier(r.get("embedding_id") or "")
        if not id_ok or not emb_ok:
            affected.append(r)
    return affected


def compute_sanitized_mapping(row: Dict) -> Tuple[str, str]:
    """Return (new_paper_id, new_embedding_id) derived from row.

    Uses central sanitizer functions. Deterministic mapping is:
    - paper id -> sanitize_identifier(old_id, fallback_prefix=researcher_id)
    - embedding id -> safe_embedding_id(researcher_id, new_paper_id)
    """
    old_id = row.get("id") or ""
    researcher_id = row.get("researcher_id") or ""
    new_paper_id = utils_mod.sanitize_identifier(old_id, fallback_prefix=researcher_id)
    new_embedding_id = utils_mod.safe_embedding_id(researcher_id, new_paper_id)
    return new_paper_id, new_embedding_id


def dry_run_report(affected: List[Dict]):
    count = len(affected)
    logging.info("Dry-run: %d affected paper rows", count)
    for sample in affected[:20]:
        new_pid, new_eid = compute_sanitized_mapping(sample)
        logging.info(
            "Affected: researcher=%s old_id=%r old_embedding=%r -> new_id=%r new_embedding=%r title=%r",
            sample.get("researcher_id"),
            sample.get("id"),
            sample.get("embedding_id"),
            new_pid,
            new_eid,
            (sample.get("title") or "")[:80],
        )


def apply_changes(conn, cursor, affected: List[Dict]):
    # Pre-check collisions
    # Build maps and check for collisions in target ids
    target_paper_ids = {compute_sanitized_mapping(r)[0]: r for r in affected}
    # Check whether any target id already exists in DB for a DIFFERENT paper
    existing_targets = []
    if target_paper_ids:
        placeholders = ", ".join(["%s"] * len(target_paper_ids))
        sql = f"SELECT id FROM papers WHERE id IN ({placeholders})"
        cursor.execute(sql, tuple(target_paper_ids.keys()))
        existing = {row[0] for row in cursor.fetchall()}
        for eid in existing:
            # If existing id is in target set, it's a collision unless it's the same original
            original = target_paper_ids.get(eid)
            if original and original.get("id") != eid:
                existing_targets.append(eid)

    if existing_targets:
        logging.error(
            "Aborting: sanitized target paper ids already exist (would collide): %s",
            existing_targets,
        )
        raise RuntimeError(
            "Sanitized id collision detected; aborting to avoid breaking refs"
        )

    # Proceed to apply per-row changes
    for r in affected:
        old_id = r.get("id")
        researcher_id = r.get("researcher_id")
        new_pid, new_eid = compute_sanitized_mapping(r)

        if new_pid == old_id:
            # Nothing to do for paper id; but may need to update embedding_id
            cursor.execute(
                "UPDATE papers SET embedding_id=%s WHERE id=%s",
                (new_eid, old_id),
            )
            logging.info("Updated embedding_id for paper %s -> %s", old_id, new_eid)
        else:
            # Insert new row, copy data, set new ids
            # Read detail columns to avoid losing data
            cursor.execute(
                "SELECT title, year, venue, venue_type, citations, concept, abstract FROM papers WHERE id=%s",
                (old_id,),
            )
            row = cursor.fetchone()
            if not row:
                logging.warning(
                    "Original paper row disappeared for id=%s; skipping", old_id
                )
                continue
            title, year, venue, venue_type, citations, concept, abstract = row

            # Insert new paper row
            insert_sql = "INSERT INTO papers (id, researcher_id, title, year, venue, venue_type, citations, concept, abstract, embedding_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            cursor.execute(
                insert_sql,
                (
                    new_pid,
                    researcher_id,
                    title,
                    year,
                    venue,
                    venue_type,
                    citations,
                    concept,
                    abstract,
                    new_eid,
                ),
            )

            # Update referencing tables to point to new paper id
            cursor.execute(
                "UPDATE co_authors SET paper_id=%s WHERE paper_id=%s", (new_pid, old_id)
            )
            cursor.execute(
                "UPDATE paper_citations_by_year SET paper_id=%s WHERE paper_id=%s",
                (new_pid, old_id),
            )

            # Delete old paper row only after references moved
            cursor.execute("DELETE FROM papers WHERE id=%s", (old_id,))

            logging.info("Rekeyed paper %s -> %s and updated refs", old_id, new_pid)

        # Attempt to re-upsert vector in Pinecone
        old_eid = r.get("embedding_id")
        try:
            idx = getattr(pinecone_mod, "index", None)
            vector_values = None
            if idx is not None:
                # Try fetching by original embedding id, then sanitized original
                candidate_ids = [old_eid]
                sanitized_old_eid = utils_mod.sanitize_identifier(
                    old_eid or "", fallback_prefix=None
                )
                if sanitized_old_eid and sanitized_old_eid != old_eid:
                    candidate_ids.append(sanitized_old_eid)

                for cid in candidate_ids:
                    if not cid:
                        continue
                    try:
                        resp = idx.fetch(ids=[cid])
                        vects = (
                            resp.get("vectors")
                            if isinstance(resp, dict)
                            else getattr(resp, "vectors", None)
                        )
                        if vects:
                            # vects is a dict of id->vector
                            vec_entry = list(vects.values())[0]
                            values = (
                                vec_entry.get("values")
                                if isinstance(vec_entry, dict)
                                else None
                            )
                            metadata = (
                                vec_entry.get("metadata")
                                if isinstance(vec_entry, dict)
                                else {}
                            )
                            if values:
                                vector_values = {
                                    "id": new_eid,
                                    "values": values,
                                    "metadata": metadata,
                                }
                                break
                    except Exception:
                        # fetch may fail for non-ascii ids; continue
                        continue

            if vector_values:
                pinecone_mod.upsert_vectors([vector_values])
                logging.info(
                    "Upserted sanitized vector %s for paper %s", new_eid, new_pid
                )
            else:
                logging.warning(
                    "Could not find existing Pinecone vector for old_embedding=%r; skipping upsert for paper=%s",
                    old_eid,
                    new_pid,
                )
        except Exception as e:
            logging.error(
                "Pinecone migration/upsert failed for paper=%s: %s", new_pid, e
            )

    # Commit all DB changes
    conn.commit()
    logging.info("Migration apply completed and committed.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scan and optionally fix unsafe paper/embedding ids."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply fixes (destructive). Requires DB + Pinecone creds.",
    )
    args = parser.parse_args(argv)

    conn = None
    if db_mod is None:
        logging.error(
            "Database support not available in this environment (missing mysql connector or DB module).\n"
            "Set up the environment with the project's DB dependencies and re-run on the host that can reach the DB."
        )
        sys.exit(1)
    try:
        conn = db_mod.get_connection()
        cursor = conn.cursor()
    except Exception as e:
        logging.error("Database connection failed: %s", e)
        sys.exit(1)

    rows = scan_papers(cursor)
    affected = find_unsafe(rows)

    # Targeted check for David Schuster researcher A5087556046
    ds_affected = [r for r in affected if r.get("researcher_id") == "A5087556046"]
    if ds_affected:
        logging.info("David Schuster affected rows: %d", len(ds_affected))
        for r in ds_affected:
            logging.info(
                "  ds: old_id=%r embedding=%r title=%r",
                r.get("id"),
                r.get("embedding_id"),
                (r.get("title") or "")[:80],
            )
    else:
        logging.info("No unsafe ids detected for David Schuster (A5087556046).")

    dry_run_report(affected)

    if args.apply:
        logging.warning(
            "Apply flag provided — running migration. This will modify DB and may upsert to Pinecone."
        )
        confirm = input("Type 'YES' to proceed with destructive apply: ")
        if confirm != "YES":
            logging.error("Apply not confirmed. Exiting without changes.")
            sys.exit(1)
        try:
            apply_changes(conn, cursor, affected)
        except Exception as e:
            logging.error("Migration aborted: %s", e)
            conn.rollback()
            sys.exit(1)
    else:
        logging.info(
            "Dry-run complete. No changes applied. Rerun with --apply to perform migration (interactive confirmation required)."
        )


if __name__ == "__main__":
    main()
