import json
import mysql.connector
from mysql.connector import Error
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "user": "root",  # Change as needed
    "password": "",  # Change as needed
    "database": "researcher_kb",  # Change as needed
}

JSON_PATH = "../researcher-kb-pipeline/data/knowledge_base.json"

# Helper to extract OpenAlex ID from URL


def extract_openalex_id(url):
    if url and url.startswith("https://openalex.org/"):
        return url.split("/")[-1]
    return url


def main():
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            print("No data found in JSON.")
            return
        researcher = data[0]
    except Exception as e:
        print(f"Failed to load JSON: {e}")
        return

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        conn.start_transaction()

        # Insert institution (current only)
        current_aff = researcher.get("affiliation", {}).get("current", [])
        if current_aff:
            inst = current_aff[0]
            inst_id = extract_openalex_id(inst.get("id"))
            inst_name = inst.get("name")
            inst_country = inst.get("country")
            # region, h_index, total_citations, prestige_tier, is_ivy_league are optional/unknown in JSON
            cursor.execute(
                """
                INSERT INTO institutions (id, name, country)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE name=VALUES(name), country=VALUES(country)
            """,
                (inst_id, inst_name, inst_country),
            )
        else:
            inst_id = None

        # Insert researcher
        researcher_id = extract_openalex_id(researcher.get("researcher_id"))
        name = researcher.get("name")
        metrics = researcher.get("global_metrics", {})
        total_works = metrics.get("total_works", 0)
        total_citations = metrics.get("total_citations", 0)
        h_index = metrics.get("h_index", 0)
        i10_index = metrics.get("i10_index", 0)
        # career_start_year, years_active, last_author_ratio_recent, industry_collaboration_score, quality_score, recency_score, seniority_score, country, last_updated
        seniority = researcher.get("lab_and_mentorship", {}).get(
            "seniority_signals", {}
        )
        career_start_year = seniority.get("career_start_year")
        years_active = seniority.get("years_active")
        last_author_ratio_recent = seniority.get("last_author_ratio_recent")
        country = None
        last_updated = researcher.get("last_updated")
        cursor.execute(
            """
            INSERT INTO researchers (
                id, name, total_works, total_citations, h_index, i10_index, career_start_year, years_active, last_author_ratio_recent, current_institution_id, country, last_updated
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name=VALUES(name), total_works=VALUES(total_works), total_citations=VALUES(total_citations),
                h_index=VALUES(h_index), i10_index=VALUES(i10_index), career_start_year=VALUES(career_start_year),
                years_active=VALUES(years_active), last_author_ratio_recent=VALUES(last_author_ratio_recent),
                current_institution_id=VALUES(current_institution_id), country=VALUES(country), last_updated=VALUES(last_updated)
        """,
            (
                researcher_id,
                name,
                total_works,
                total_citations,
                h_index,
                i10_index,
                career_start_year,
                years_active,
                last_author_ratio_recent,
                inst_id,
                country,
                last_updated,
            ),
        )

        # Insert papers
        papers_by_concept = researcher.get("papers_by_concept", {})
        for concept, papers in papers_by_concept.items():
            for paper in papers:
                paper_id = (
                    paper.get("doi") or f"{researcher_id}_{paper.get('title','')[:32]}"
                )
                paper_id = (
                    paper_id.replace("https://doi.org/", "") if paper_id else None
                )
                title = paper.get("title")
                year = paper.get("year")
                venue = paper.get("venue")
                venue_type = "other"  # Not in JSON, fallback
                citations = paper.get("citations", 0)
                abstract = paper.get("abstract")
                embedding_id = None
                cursor.execute(
                    """
                    INSERT INTO papers (
                        id, researcher_id, title, year, venue, venue_type, citations, concept, abstract, embedding_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        title=VALUES(title), year=VALUES(year), venue=VALUES(venue), venue_type=VALUES(venue_type),
                        citations=VALUES(citations), concept=VALUES(concept), abstract=VALUES(abstract)
                """,
                    (
                        paper_id,
                        researcher_id,
                        title,
                        year,
                        venue,
                        venue_type,
                        citations,
                        concept,
                        abstract,
                        embedding_id,
                    ),
                )

        # Insert research topics
        for topic in researcher.get("research_topics_granular", []):
            cursor.execute(
                """
                INSERT INTO researcher_topics (
                    researcher_id, topic, subfield, field, domain, paper_count
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    subfield=VALUES(subfield), field=VALUES(field), domain=VALUES(domain), paper_count=VALUES(paper_count)
            """,
                (
                    researcher_id,
                    topic.get("topic"),
                    topic.get("subfield"),
                    topic.get("field"),
                    topic.get("domain"),
                    topic.get("paper_count", 0),
                ),
            )

        # Insert collaborators
        for collab in researcher.get("lab_and_mentorship", {}).get(
            "top_collaborators", []
        ):
            cursor.execute(
                """
                INSERT INTO researcher_collaborations (
                    researcher_id, collaborator_name, collaborator_type, shared_papers
                ) VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE shared_papers=VALUES(shared_papers)
            """,
                (
                    researcher_id,
                    collab.get("name"),
                    "academia",  # No type in JSON, default to academia
                    collab.get("shared_papers", 0),
                ),
            )

        conn.commit()
        print("Seed data inserted successfully.")
    except Error as e:
        print(f"Error: {e}. Rolling back.")
        if conn:
            conn.rollback()
    finally:
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals() and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    main()
