import logging
import os

import mysql.connector
from mysql.connector import Error


class PineconeUpsertError(RuntimeError):
    pass


class DatabaseUpsertError(RuntimeError):
    pass


def get_connection():
    """
    Return a MySQL connection.

    Cloud Run (Cloud SQL Proxy via --add-cloudsql-instances):
        DB_HOST=/cloudsql/<PROJECT>:<REGION>:<INSTANCE>
        The leading '/' triggers Unix socket mode.

    Direct TCP (e.g., Cloud SQL public IP or private IP):
        DB_HOST=<ip-or-hostname>
    """
    required_env_vars = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [name for name in required_env_vars if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing required database environment variables: {', '.join(missing)}"
        )

    host = os.environ["DB_HOST"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    db_name = os.environ["DB_NAME"]

    logging.info("MySQL env resolved: host=%s db=%s user=%s", host, db_name, user)

    connect_kwargs = dict(user=user, password=password, database=db_name)

    if host.startswith("/"):
        # Unix socket — Cloud SQL Proxy socket directory
        connect_kwargs["unix_socket"] = host
        logging.debug("MySQL: connecting via Unix socket %s", host)
    else:
        connect_kwargs["host"] = host
        connect_kwargs["port"] = int(os.environ.get("DB_PORT", "3306"))
        logging.debug("MySQL: connecting via TCP to %s", host)

    try:
        conn = mysql.connector.connect(
            **connect_kwargs,
            auth_plugin=os.environ.get("DB_AUTH_PLUGIN", "mysql_native_password"),
            connection_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "15")),
        )
        conn.ping(reconnect=False, attempts=1, delay=0)
        logging.info("MySQL connection established successfully.")
        return conn
    except Error as exc:
        logging.exception("MySQL connection failed: %s", exc)
        raise


def upsert_institution(cursor, institution):
    sql = """
        INSERT INTO institutions (id, name, country, region)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE name=VALUES(name), country=VALUES(country), region=VALUES(region)
    """
    cursor.execute(
        sql,
        (
            institution.get("id"),
            institution.get("name"),
            institution.get("country"),
            institution.get("region"),
        ),
    )


def upsert_researcher(cursor, researcher):
    sql = """
        INSERT INTO researchers (
            id, name, total_works, total_citations, h_index, i10_index, career_start_year, years_active, last_author_ratio_recent, current_institution_id, country, last_updated
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), total_works=VALUES(total_works), total_citations=VALUES(total_citations),
            h_index=VALUES(h_index), i10_index=VALUES(i10_index), career_start_year=VALUES(career_start_year),
            years_active=VALUES(years_active), last_author_ratio_recent=VALUES(last_author_ratio_recent),
            current_institution_id=VALUES(current_institution_id), country=VALUES(country), last_updated=VALUES(last_updated)
    """
    cursor.execute(
        sql,
        (
            researcher.get("id"),
            researcher.get("name"),
            researcher.get("total_works", 0),
            researcher.get("total_citations", 0),
            researcher.get("h_index", 0),
            researcher.get("i10_index", 0),
            researcher.get("career_start_year"),
            researcher.get("years_active"),
            researcher.get("last_author_ratio_recent"),
            researcher.get("current_institution_id"),
            researcher.get("country"),
            researcher.get("last_updated"),
        ),
    )


def fetch_existing_researcher_ids(cursor, researcher_ids):
    """
    Return the subset of researcher_ids already present in researchers table.
    """
    ids = [rid for rid in researcher_ids if rid]
    if not ids:
        return set()

    placeholders = ", ".join(["%s"] * len(ids))
    sql = f"SELECT id FROM researchers WHERE id IN ({placeholders})"
    cursor.execute(sql, tuple(ids))
    return {row[0] for row in cursor.fetchall()}


def fetch_existing_institution_ids(cursor, institution_ids):
    """
    Return the subset of institution_ids already present in institutions table.
    """
    ids = [iid for iid in institution_ids if iid]
    if not ids:
        return set()

    placeholders = ", ".join(["%s"] * len(ids))
    sql = f"SELECT id FROM institutions WHERE id IN ({placeholders})"
    cursor.execute(sql, tuple(ids))
    return {row[0] for row in cursor.fetchall()}


def _extract_openalex_id(openalex_url):
    if not openalex_url:
        return None
    return openalex_url.split("/")[-1]


def insert_coauthor_edges_for_papers(cursor, papers):
    """
    Add directed coauthor edges for each paper using INSERT IGNORE:
    A->B for all A != B from the paper authorship list.
    """
    sql = """
        INSERT IGNORE INTO co_authors (researcher_id, coauthor_id, paper_id)
        VALUES (%s, %s, %s)
    """
    total_edges = 0

    for paper in papers:
        paper_id = _extract_openalex_id(paper.get("id")) or paper.get("doi")
        if not paper_id:
            continue

        author_ids = []
        for auth in paper.get("authorships", []):
            aid = _extract_openalex_id((auth.get("author") or {}).get("id"))
            if aid and aid not in author_ids:
                author_ids.append(aid)

        if len(author_ids) < 2:
            continue

        edge_rows = []
        for researcher_id in author_ids:
            for coauthor_id in author_ids:
                if researcher_id != coauthor_id:
                    edge_rows.append((researcher_id, coauthor_id, paper_id))

        if not edge_rows:
            continue

        cursor.executemany(sql, edge_rows)
        total_edges += len(edge_rows)
        logging.info("Added coauthor edges for paper %s", paper_id)

    return total_edges


def upsert_papers(cursor, researcher_id, papers_by_concept):
    import logging
    import embeddings
    import pinecone_client

    sql = """
        INSERT INTO papers (
            id, researcher_id, title, year, venue, venue_type, citations, concept, abstract, embedding_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            title=VALUES(title), year=VALUES(year), venue=VALUES(venue), venue_type=VALUES(venue_type),
            citations=VALUES(citations), concept=VALUES(concept), abstract=VALUES(abstract), embedding_id=VALUES(embedding_id)
    """
    texts_to_embed = []
    embedding_ids = []
    metadata_list = []
    paper_rows = []
    total_papers = 0
    for concept, papers in papers_by_concept.items():
        for paper in papers:
            total_papers += 1
            paper_id = (
                paper.get("doi") or f"{researcher_id}_{paper.get('title','')[:32]}"
            )
            paper_id = paper_id.replace("https://doi.org/", "") if paper_id else None
            title = paper.get("title")
            abstract = paper.get("abstract")
            text_for_embed = None
            if abstract:
                text_for_embed = (title or "") + " " + abstract
                texts_to_embed.append(text_for_embed)
                embedding_ids.append(paper_id)
                metadata_list.append(
                    {
                        "researcher_id": researcher_id,
                        "concept": concept,
                        "year": paper.get("year"),
                    }
                )
            paper_rows.append(
                {
                    "paper_id": paper_id,
                    "researcher_id": researcher_id,
                    "title": title,
                    "year": paper.get("year"),
                    "venue": paper.get("venue"),
                    "venue_type": "other",
                    "citations": paper.get("citations", 0),
                    "concept": concept,
                    "abstract": abstract,
                    # embedding_id will be filled after embedding
                }
            )
    # Batch embed
    embeddings_list = (
        embeddings.get_embeddings_batch(texts_to_embed) if texts_to_embed else []
    )
    # Prepare Pinecone vectors
    pinecone_vectors = []
    for idx, emb in enumerate(embeddings_list):
        if emb is not None:
            pinecone_vectors.append(
                {
                    "id": embedding_ids[idx],
                    "values": emb,
                    "metadata": metadata_list[idx],
                }
            )
    # Upsert to Pinecone in batch
    if pinecone_vectors:
        try:
            pinecone_client.upsert_vectors(pinecone_vectors)
            logging.info(
                "Pinecone upsert succeeded for researcher=%s vectors=%s",
                researcher_id,
                len(pinecone_vectors),
            )
        except Exception as e:
            logging.error(f"Pinecone upsert failed: {e}")
            raise PineconeUpsertError(
                f"Pinecone upsert failed for researcher={researcher_id}"
            ) from e
    # Map paper_id to embedding_id for successful embeddings
    embedding_id_map = {
        embedding_ids[i]: embedding_ids[i]
        for i, emb in enumerate(embeddings_list)
        if emb is not None
    }
    # Insert all papers, set embedding_id if available
    for row in paper_rows:
        emb_id = embedding_id_map.get(row["paper_id"])
        try:
            cursor.execute(
                sql,
                (
                    row["paper_id"],
                    row["researcher_id"],
                    row["title"],
                    row["year"],
                    row["venue"],
                    row["venue_type"],
                    row["citations"],
                    row["concept"],
                    row["abstract"],
                    emb_id,
                ),
            )
        except Exception as e:
            logging.error(f"Paper upsert failed for {row['paper_id']}: {e}")
            raise DatabaseUpsertError(
                f"Paper upsert failed for paper_id={row['paper_id']}"
            ) from e
    logging.info(
        "Paper upsert loop finished for researcher=%s total_papers=%s embedded=%s",
        researcher_id,
        total_papers,
        len(embedding_id_map),
    )


def upsert_topics(cursor, researcher_id, topics):
    sql = """
        INSERT INTO researcher_topics (
            researcher_id, topic, subfield, field, domain, paper_count
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            subfield=VALUES(subfield), field=VALUES(field), domain=VALUES(domain), paper_count=VALUES(paper_count)
    """
    for topic in topics:
        cursor.execute(
            sql,
            (
                researcher_id,
                topic.get("topic"),
                topic.get("subfield"),
                topic.get("field"),
                topic.get("domain"),
                topic.get("paper_count", 0),
            ),
        )


def upsert_collaborations(cursor, researcher_id, collaborators):
    sql = """
        INSERT INTO researcher_collaborations (
            researcher_id, collaborator_name, collaborator_type, shared_papers
        ) VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE shared_papers=VALUES(shared_papers)
    """
    for collab in collaborators:
        cursor.execute(
            sql,
            (
                researcher_id,
                collab.get("name"),
                "academia",  # No type in JSON, default to academia
                collab.get("shared_papers", 0),
            ),
        )


def fetch_researcher_ranking_rows(
    cursor,
    researcher_ids=None,
    region=None,
    institution_id=None,
):
    """
    Fetch researcher rows plus display-oriented institution fields for ranking.
    """
    sql = """
        SELECT
            r.id,
            r.name,
            r.total_works,
            r.total_citations,
            r.h_index,
            r.i10_index,
            r.years_active,
            COALESCE(r.quality_score, 0) AS quality_score,
            COALESCE(r.recency_score, 0) AS recency_score,
            COALESCE(r.seniority_score, r.years_active, 0) AS seniority_score,
            r.current_institution_id,
            r.country,
            i.name AS institution_name,
            i.region AS institution_region
        FROM researchers r
        LEFT JOIN institutions i ON i.id = r.current_institution_id
    """
    clauses = []
    params = []

    ids = [researcher_id for researcher_id in (researcher_ids or []) if researcher_id]
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        clauses.append(f"r.id IN ({placeholders})")
        params.extend(ids)

    if region:
        clauses.append(
            "(LOWER(COALESCE(i.region, '')) = LOWER(%s) OR LOWER(COALESCE(i.country, '')) = LOWER(%s) OR LOWER(COALESCE(r.country, '')) = LOWER(%s))"
        )
        params.extend([region, region, region])

    if institution_id:
        clauses.append("r.current_institution_id = %s")
        params.append(institution_id)

    if clauses:
        sql = f"{sql} WHERE {' AND '.join(clauses)}"

    cursor.execute(sql, tuple(params))
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_papers_by_ids(cursor, paper_ids):
    """
    Fetch paper rows keyed by paper id for explainability and optional score modifiers.
    """
    ids = [paper_id for paper_id in (paper_ids or []) if paper_id]
    if not ids:
        return {}

    placeholders = ", ".join(["%s"] * len(ids))
    sql = f"""
        SELECT id, researcher_id, title, year, citations, abstract, venue, concept
        FROM papers
        WHERE id IN ({placeholders})
    """
    cursor.execute(sql, tuple(ids))

    rows = {}
    for row in cursor.fetchall():
        rows[row[0]] = {
            "id": row[0],
            "researcher_id": row[1],
            "title": row[2],
            "year": row[3],
            "citations": row[4],
            "abstract": row[5],
            "venue": row[6],
            "concept": row[7],
        }
    return rows
