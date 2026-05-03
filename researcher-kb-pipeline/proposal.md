# Researcher Intelligence Platform

## Phase 1 & Phase 2 Implementation Proposal

---

# 1. Executive Summary

This document defines the implementation plan for a Researcher Intelligence Platform that enables intelligent search over academic researchers.

The system will:

- Build a structured researcher knowledge base from OpenAlex and Semantic Scholar.
- Store structured researcher, institution, and paper data in a relational database.
- Store semantic embeddings of abstracts in a vector database.
- Support free-text user queries using an LLM-driven query interpretation layer.
- Combine structured filtering and semantic similarity into a hybrid ranking pipeline.
- Be deployable to Google Cloud after local validation.

The system is divided into:

- **Phase 1 — Knowledge Base Construction (Offline Pipeline)**
- **Phase 2 — Intelligent Retrieval & Ranking (Online Query Engine)**

---

# 2. Goals & Design Principles

## Primary Goals

- Support structured and unstructured queries.
- Provide high-quality, explainable rankings.
- Minimize LLM token usage per query.
- Allow incremental updates (upsert behavior).
- Be scalable to thousands of researchers.

## Design Principles

- Separation of concerns.
- Structured data handled by SQL.
- Semantic similarity handled by vector database.
- LLM used only for interpretation and explanation.
- Precompute expensive metrics offline.

---

# 3. Phase 1 — Knowledge Base Construction

Phase 1 is an offline pipeline responsible for building and maintaining the dataset.

This phase must be idempotent, incremental, and safe to re-run.

---

## 3.1 Data Sources

- OpenAlex (works, authors, institutions)
- Semantic Scholar (abstract fallback, author cross-reference)

---

## 3.2 Storage Architecture (Production Schema)

Phase 1 will store structured data in a relational database (MySQL or PostgreSQL) and semantic embeddings in a vector database.

The schema is designed to support hybrid structured + semantic queries efficiently.

---

### Researchers Table

Primary entity representing each academic researcher.

Fields:

- id (Primary Key, OpenAlex author id)
- name
- total_works
- total_citations
- h_index
- i10_index
- career_start_year
- years_active
- last_author_ratio_recent
- industry_collaboration_score
- quality_score (precomputed)
- recency_score (precomputed)
- seniority_score (precomputed)
- current_institution_id (Foreign Key → institutions.id)
- country
- last_updated

Indexes:

- h_index
- total_citations
- quality_score
- current_institution_id

Supports:

- Seniority filtering
- Citation thresholds
- Quality-based ranking
- Institution filtering

---

### Institutions Table

Represents academic institutions.

Fields:

- id (Primary Key)
- name
- country
- region
- h_index
- total_citations
- prestige_tier (numeric or categorical)
- is_ivy_league (boolean)

Indexes:

- country
- prestige_tier
- is_ivy_league

Supports:

- Ivy League filtering
- Prestige filtering
- Geographic filtering

---

### Papers Table

Stores paper-level data.

Fields:

- id (Primary Key, OpenAlex work id)
- researcher_id (Foreign Key → researchers.id)
- title
- year
- venue
- venue_type (conference / journal / other)
- citations
- concept
- abstract
- embedding_id (used in vector DB)

Indexes:

- researcher_id
- year
- venue_type
- concept

Supports:

- Year filtering
- Venue filtering
- Field filtering
- Citation-based paper ranking

---

### Researcher Topics Table

Flattened representation of topic hierarchy for structured querying.

Fields:

- researcher_id (Foreign Key → researchers.id)
- topic
- subfield
- field
- domain
- paper_count

Indexes:

- field
- subfield
- topic

Supports:

- Filtering by domain or field
- Structured topic queries
- Cross-field analysis

---

### Researcher Collaborations Table (Optional but Recommended)

Stores collaboration signals including industry partnerships.

Fields:

- researcher_id
- collaborator_name
- collaborator_type (industry / academia)
- shared_papers

Supports:

- Industry collaboration filtering
- Network-based signals

---

### Vector Database (Pinecone)

The system will use Pinecone as the dedicated vector database for semantic search.

Pinecone will:

- Store embeddings of paper abstracts.
- Perform cosine similarity search.
- Support metadata filtering.
- Return top-K similar papers efficiently.

Each vector entry will contain:

- id = paper_id
- vector = embedding
- metadata:
  - researcher_id
  - year
  - concept
  - venue_type

Pinecone will be used strictly for semantic similarity search. All structured filtering will be handled by SQL.

---

This schema enables:

- Pure structured queries (SQL)
- Pure semantic queries (Vector DB)
- Hybrid queries (SQL → Vector → Python ranking)
- Efficient pre-filtering before LLM usage
- Scalable cloud deployment

---

## 3.3 Embedding Strategy

During Phase 1:

- Generate embeddings for all paper abstracts using Vertex AI (text-embedding-004).
- Store embeddings in Pinecone.
- Use paper_id as the stable upsert key.

Embeddings are generated once and reused for all future queries.

Authentication to Vertex AI is handled using Google Cloud Application Default Credentials. No API keys are stored in the codebase.

---

## 3.4 Upsert Logic

Phase 1 must support incremental updates:

For each entity:

If id does not exist → INSERT  
If id exists → UPDATE  
If abstract changes → regenerate embedding and upsert  
If new researchers found → insert

Use stable OpenAlex IDs as primary keys.

---

## 3.5 Precomputed Signals

To maximize retrieval efficiency, compute offline:

- Normalized quality_score
- Recency score
- Seniority score
- Industry collaboration score

This reduces runtime computation.

---

# 4. Phase 2 — Intelligent Retrieval & Ranking

Phase 2 handles user queries dynamically.

---

## 4.1 Query Flow

### Step 1 — User Query

User provides free-text query.

Example:
"Find senior researchers in GaN plasma etching from Ivy League schools with 2025 conference papers."

---

### Step 2 — LLM Query Interpretation

The LLM is provided full database schema and must return:

- A fully executable SQL query
- A semantic_query string
- A list of unsupported constraints

Expected format:

{
"sql_query": "...",
"semantic_query": "...",
"unsupported_constraints": []
}

The SQL must:

- Use only known tables and columns
- Avoid unsafe operations
- Be executable without modification

---

### Step 3 — Structured Filtering (SQL)

Execute SQL to reduce dataset.

Example:
1000 researchers → 150 after filtering

---

### Step 4 — Semantic Ranking (Vector DB)

- Embed semantic_query
- Perform vector similarity search
- Optionally restrict using metadata filter (researcher_id subset)
- Retrieve similarity scores

Reduce:
150 → top 30–50

---

### Step 5 — Hybrid Ranking (Python Layer)

Compute:

final_score =
0.5 \* semantic_similarity

- 0.3 \* quality_score
- 0.2 \* recency_score

Sort in Python.

Return top 20–30.

---

### Step 6 — Optional LLM Explanation

Send top results to LLM for:

- Explanation
- Comparative reasoning
- Human-readable output

---

# 5. Query Relevance

The "query_relevance" score refers to runtime semantic similarity.

Important:

- It is computed per query.
- It is NOT stored permanently in the database.
- It is added temporarily to result sets for ranking and inspection.

---

# 6. Retrieval Strategy

Adaptive strategy:

If structured filters exist → SQL first → Vector second  
If mostly semantic → Vector first → SQL filter second

Final ranking always happens in Python.

---

# 7. Deployment Plan (Google Cloud)

After local validation:

## Components

- Cloud SQL (MySQL or PostgreSQL)
- Pinecone (external vector database)
- Cloud Run (API layer)
- Secret Manager (keys)
- Cloud Scheduler (to trigger Phase 1 jobs)
- Cloud Storage (logs and backups)

---

## Phase 1 in Cloud

- Run as Cloud Run Job
- Trigger monthly via Cloud Scheduler
- Update SQL and vector DB

---

## Phase 2 in Cloud

- Deploy FastAPI service to Cloud Run
- Handle:
  - LLM calls
  - SQL execution
  - Vector retrieval
  - Hybrid ranking

---

# 8. Cost Expectations

Estimated per query:

- 8k–10k tokens
- ~$0.05–$0.08 per query (mid-tier LLM)

Estimated during build:

- ~$50 per month

Pinecone cost is minimal for datasets under 10k abstracts and scales linearly with vector count.

---

# 9. Immediate Next Steps

1. Finalize relational schema
2. Implement JSON → SQL ingestion
3. Implement embedding pipeline
4. Implement upsert logic
5. Build minimal Phase 2 retrieval script
6. Integrate LLM query interpreter
7. Validate ranking on 20+ query examples
8. Deploy to Cloud Run

---

# 10. Success Criteria

The system is successful if:

- It handles both structured and semantic queries.
- It reduces dataset before LLM usage.
- It scales without architectural changes.
- It keeps query cost below $0.10.
- It supports incremental updates without rebuild.

---

End of Proposal
