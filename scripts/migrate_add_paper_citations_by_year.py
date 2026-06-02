"""
Migration: create paper_citations_by_year table if it does not exist.

Usage (from researcher-kb-pipeline/ with Cloud SQL Proxy running):
    DB_HOST=127.0.0.1 DB_USER=... DB_PASSWORD=... DB_NAME=... \
        python ../scripts/migrate_add_paper_citations_by_year.py
"""

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, "..", "researcher-kb-pipeline"))

from db import get_connection  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS paper_citations_by_year (
    paper_id VARCHAR(128) NOT NULL,
    year SMALLINT NOT NULL,
    cited_by_count INT DEFAULT 0 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (paper_id, year),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    INDEX idx_pcby_year (year),
    INDEX idx_pcby_paper_year (paper_id, year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def main():
    conn = get_connection()
    cursor = conn.cursor()
    print("Running migration: CREATE TABLE IF NOT EXISTS paper_citations_by_year …")
    cursor.execute(DDL)
    conn.commit()
    cursor.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
