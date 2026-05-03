# Architecture Document: Researcher Knowledge Base Pipeline

## 1. Overview

The Researcher Knowledge Base Pipeline is an offline data engineering system designed to build and maintain a structured knowledge base of academic researchers. By aggregating data from open scholarly APIs, the pipeline constructs rich, multi-dimensional profiles for researchers across specific domains (e.g., Quantum Computing, Artificial Intelligence). The system extracts publication history, calculates derived signals (such as mentee counts and seniority), and pushes the consolidated data into both relational and vector databases to support hybrid (semantic + structured) AI-driven queries.

## 2. High-Level Architecture

The system is architected in two primary phases (as outlined in the project proposals):

- **Phase 1 (Offline ETL Pipeline):** The current codebase. It discovers, extracts, enriches, and assembles data into local files, a MySQL database, and a Pinecone vector index.
- **Phase 2 (Online Retrieval System):** A planned query engine that will use an LLM to parse natural language into SQL for structured filtering and vector search for semantic similarity.

## 3. System Components

### 3.1 Data Sources

- **OpenAlex API:** The primary source of truth for concepts, works (papers), author profiles, and institutional data.
- **Semantic Scholar API:** Used as a fallback to retrieve missing abstract texts, author homepages, and cross-referenced citation metrics.

### 3.2 Offline ETL Pipeline (`pipeline.py`)

The pipeline runs in distinct stages. It is designed to be idempotent—caching raw responses locally so that interrupted runs can be resumed and monthly updates only fetch stale data (default: older than 30 days).

- **Stage 1: Discover (`stage1_discover.py`)**
  Queries the OpenAlex `/works` API for highly cited papers matching defined concepts (configured in `config.py`). It pages through results and falls back to Semantic Scholar if an abstract is missing.
  _Output:_ `data/raw/papers/papers_{concept}.jsonl`
- **Stage 2: Extract (`stage2_extract.py`)**
  Parses the discovered papers to extract unique authors affiliated with educational institutions. It computes per-concept statistics (e.g., first/last author ratios, venues, funding).
  _Output:_ `data/intermediate/field_author_map.json`
- **Stage 3: Enrich (`stage3_enrich.py`)**
  - **3a (Profiles):** Fetches lifetime metrics (h-index, total citations, career trajectory) for authors from OpenAlex and Semantic Scholar.
  - **3b (Mentee/Co-author Analysis):** Evaluates recent papers (last 5 years) to infer mentees (based on co-authors at the same institution with low publication counts) and calculates seniority signals.
  - **3c (Institutions):** Retrieves institutional profiles (h-index, geography) to enrich researcher profiles.
    _Outputs:_ `data/raw/profiles/`, `data/raw/coauthors/`, `data/raw/institutions/`
- **Stage 4: Assemble & Upsert (`stage4_assemble.py`, `db.py`, `pinecone_client.py`)**
  Merges all extracted and enriched data. It writes a compiled JSON file and an Excel summary. Simultaneously, it generates text embeddings for paper abstracts and performs UPSERT operations into the MySQL database and Pinecone vector database.

### 3.3 Storage Layer

#### Local File System (Cache)

- The `data/` directory acts as a staging and caching layer. It stores raw API responses to prevent redundant network calls, making the pipeline cost-effective and faster on subsequent runs.

#### Relational Database (MySQL)

Stores structured metadata for fast, SQL-based filtering. The schema (`schema.sql`) and ORM models (`models.py`) include:

- **`institutions`:** University/lab details, h-index, and prestige metrics.
- **`researchers`:** Core profile data, derived metrics (seniority score, last-author ratio).
- **`papers`:** Paper metadata (year, venue, concept) linked via `embedding_id` to the Vector DB.
- **`researcher_topics` & `researcher_collaborations`:** Flattened tables supporting complex structured queries (e.g., "Find researchers collaborating with industry").

#### Vector Database (Pinecone)

Handles the semantic search capabilities.

- Abstracts and titles are converted into embeddings (via `embeddings.py`, e.g., using `text-embedding-3-small` or Vertex AI).
- Vectors are stored with metadata (researcher_id, year, concept) to allow pre-filtering during cosine similarity searches.

## 4. Codebase Structure

- **`pipeline.py`**: The CLI entry point orchestrating the execution of pipeline stages.
- **`config.py`**: Central configuration (concepts, rate limits, file paths, embedding models).
- **`stage1_discover.py` ... `stage4_assemble.py`**: Business logic for the respective ETL stages.
- **`utils.py`**: Helper functions for API requests, caching logic, and JSON parsing.
- **`db.py`**: MySQL connection management and raw SQL upsert operations.
- **`models.py`**: SQLAlchemy ORM definitions.
- **`embeddings.py` & `pinecone_client.py`**: Integration with embedding providers and the Pinecone vector index.
- **`schema.sql`**: Production database DDL scripts.

## 5. Deployment and Operations

- **Rate Limiting:** The pipeline utilizes OpenAlex's "polite pool" by injecting a contact email in the `User-Agent`, achieving ~10 requests per second.
- **Cloud Readiness:** The system is designed to run in Google Cloud (e.g., Cloud Run Jobs triggered by Cloud Scheduler). `db.py` natively supports connecting to Cloud SQL via Unix sockets (`/cloudsql/...`).
- **Batching:** Database and vector upserts are batched (`EMBED_BATCH_SIZE`, `PINECONE_UPSERT_BATCH`) to optimize network I/O and reduce memory overhead during Stage 4.

## 7. Potential Improvements

For beginners to data pipelines, think of this system like a factory assembly line. Here are a few ways we could upgrade the factory to make it faster, safer, and more reliable:

1. **Parallel Processing (Doing things at the same time):** Currently, the pipeline looks up one researcher after another. We could use "asynchronous programming" or "multithreading" to look up 10 or 20 researchers at the exact same time, speeding up the process massively.
2. **Error Handling & Retries:** Sometimes websites (APIs) temporarily break or reject our requests. Instead of the pipeline crashing, we can add "retry logic" so it waits 5 seconds and tries again automatically.
3. **Data Quality Checks:** Before saving to our database, we could add a step that double-checks the data (e.g., making sure a researcher's name isn't blank, or their citation count isn't negative) to prevent bad data from polluting our system.
4. **Using a Pipeline Orchestrator:** Instead of running everything from a single Python script (`pipeline.py`), we could use a professional tool like Apache Airflow or Prefect. These tools give you a visual dashboard, automatically retry failed steps, and send you an email if something goes wrong.
5. **API Cost & Rate Limit Optimization (Saving Free Credits):** Since the pipeline uses AI models (like the free version of Gemini) to generate embeddings or process text, it's crucial to conserve your free API credits. We can improve the pipeline by ensuring we *strictly* only send new or modified paper abstracts to the AI, skipping anything we've already processed. Alternatively, we could switch to running a small, free open-source AI model directly on your computer (known as "local embeddings"), meaning you wouldn't have to worry about API limits or burning through free tier credits at all!

## 8. Changelog

- **2026-03-28:** Added API Cost & Rate Limit Optimization to the improvements section, focusing on conserving free Gemini credits.
- **2026-03-28:** Added "Potential Improvements" section to explain future enhancements for beginners.
- **2026-03-28:** Initial creation of the architecture document.
