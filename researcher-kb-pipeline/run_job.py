#!/usr/bin/env python3
"""
Cloud Run Job entrypoint for the researcher ingestion pipeline.

Reads these environment variables before delegating to pipeline.main():
  TOPIC_IDS              Comma-separated OpenAlex topic IDs to process.
                         If unset, all CONCEPTS in config.py are processed.
  MAX_COAUTHORS_TO_CHECK Override config.MAX_COAUTHORS_TO_CHECK (int, default 50).
  LIMIT                  Max new researchers to process; 'all' means unlimited.
                         Handled natively by pipeline.main() via os.environ.

All CLI arguments (--start-date, --end-date, etc.) are forwarded
to pipeline.main() via sys.argv.

After pipeline.main() completes, prints a per-topic stats report
queried from Cloud SQL and Pinecone so the results appear in Cloud Logging.
"""

import os
import sys
import time

# ── 1. Patch config BEFORE any pipeline import reads it ──────────────────────
import config

_topic_ids_env = os.environ.get("TOPIC_IDS", "").strip()
if _topic_ids_env:
    _ids = {t.strip() for t in _topic_ids_env.split(",") if t.strip()}
    _original_count = len(config.CONCEPTS)
    config.CONCEPTS = [c for c in config.CONCEPTS if c["id"] in _ids]
    print(
        f"[Job] TOPIC_IDS filter: {len(config.CONCEPTS)} of {_original_count} topics selected.",
        flush=True,
    )
    for c in config.CONCEPTS:
        print(f"[Job]   {c['id']:8s}  {c['label']}", flush=True)
else:
    print(
        f"[Job] No TOPIC_IDS filter; running all {len(config.CONCEPTS)} topics.",
        flush=True,
    )

# Allow tuning coauthor depth per-execution without rebuilding the image.
_max_coauthors_env = os.environ.get("MAX_COAUTHORS_TO_CHECK")
if _max_coauthors_env is not None:
    try:
        config.MAX_COAUTHORS_TO_CHECK = int(_max_coauthors_env)
        print(
            f"[Job] MAX_COAUTHORS_TO_CHECK overridden to {config.MAX_COAUTHORS_TO_CHECK}",
            flush=True,
        )
    except ValueError:
        print(
            f"[Job] WARNING: ignoring invalid MAX_COAUTHORS_TO_CHECK={_max_coauthors_env!r}",
            flush=True,
        )

# ── 2. Run the pipeline ───────────────────────────────────────────────────────
print("[Job] Starting pipeline.main() ...", flush=True)
_pipeline_start = time.time()

import pipeline  # noqa: E402  (must come after config is patched)

pipeline.main()

_pipeline_elapsed = time.time() - _pipeline_start
print(
    f"[Job] pipeline.main() finished in {_pipeline_elapsed / 60:.1f} minutes.",
    flush=True,
)

# ── 3. Post-run stats report ──────────────────────────────────────────────────
print("\n" + "=" * 72, flush=True)
print("[Stats] Post-ingestion report", flush=True)
print("=" * 72, flush=True)

_topic_labels = [c["label"] for c in config.CONCEPTS]
_placeholders = ", ".join(["%s"] * len(_topic_labels))

try:
    from db import get_connection

    conn = get_connection()
    cur = conn.cursor()

    # ── Per-topic paper + researcher counts ──────────────────────────────────
    if _topic_labels:
        cur.execute(
            f"""
            SELECT
                p.concept                        AS topic,
                COUNT(DISTINCT p.researcher_id)  AS researchers,
                COUNT(*)                         AS papers
            FROM papers p
            WHERE p.concept IN ({_placeholders})
            GROUP BY p.concept
            ORDER BY papers DESC
            """,
            _topic_labels,
        )
        rows = cur.fetchall()

        total_papers = 0
        total_researchers = 0
        print(
            f"\n{'Topic':<50}  {'Researchers':>12}  {'Papers':>10}",
            flush=True,
        )
        print("-" * 76, flush=True)
        for topic, researchers, papers in rows:
            print(f"{topic:<50}  {researchers:>12,}  {papers:>10,}", flush=True)
            total_papers += papers
            total_researchers += researchers
        print("-" * 76, flush=True)
        print(
            f"{'TOTAL (new topics only)':<50}  {total_researchers:>12,}  {total_papers:>10,}",
            flush=True,
        )

    # ── Overall DB table sizes ────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM researchers")
    (total_db_researchers,) = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM papers")
    (total_db_papers,) = cur.fetchone()

    cur.execute("""
        SELECT
            ROUND(SUM(data_length + index_length) / 1024 / 1024, 1) AS size_mb
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        """)
    (db_size_mb,) = cur.fetchone()

    print(f"\n[Stats] Total researchers in DB : {total_db_researchers:,}", flush=True)
    print(f"[Stats] Total papers in DB      : {total_db_papers:,}", flush=True)
    print(f"[Stats] Cloud SQL DB size       : {db_size_mb} MB", flush=True)

    conn.close()

except Exception as e:
    print(f"[Stats] ERROR querying Cloud SQL: {e}", flush=True)

# ── Pinecone vector count ─────────────────────────────────────────────────────
try:
    from pinecone import Pinecone

    _pc = Pinecone(api_key=config.PINECONE_API_KEY)
    _idx = _pc.Index(config.PINECONE_INDEX)
    _stats = _idx.describe_index_stats()
    _total_vectors = _stats.total_vector_count
    print(f"[Stats] Pinecone total vectors  : {_total_vectors:,}", flush=True)
except Exception as e:
    print(f"[Stats] ERROR querying Pinecone: {e}", flush=True)

print("=" * 72, flush=True)
print("[Job] Done.", flush=True)
