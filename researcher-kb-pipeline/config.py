"""
Configuration for the Researcher Knowledge Base Pipeline.
Edit the constants below to change the field/concept, pagination limits, etc.
"""

import os

# ============================================================
# API Endpoints
# ============================================================


OPENALEX_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"


# ============================================================
# User-Agent  (required by OpenAlex polite pool for faster limits)
# Replace with your actual email to get ~10 req/s instead of ~1 req/s
# ============================================================


CONTACT_EMAIL = "your_email@example.com"


HEADERS = {"User-Agent": f"researcher-kb-pipeline/0.1 (contact: {CONTACT_EMAIL})"}


# ============================================================
# Retrieval Target Configuration
# ============================================================
# Add or remove entries to query multiple fields in one pipeline run.
# Each dict needs an "id" and a "label".
#
# Preferred IDs (Topic IDs):
#   Quantum Computing Topic  : T10682
#   Computer Vision Topic    : T10017
#
# Legacy IDs (OpenAlex concept IDs) are still supported by Stage 1:
#   Artificial Intelligence  : C154945302
#   Semiconductors           : C205649164
#   Machine Learning         : C119857082
#
# NOTE: Variable name `CONCEPTS` is kept for backward compatibility with
# existing stages, but entries may contain either topic IDs (preferred)
# or legacy concept IDs.


CONCEPTS = [
    {"id": "T10682", "label": "Quantum Computing"},
    # {"id": "C205649164", "label": "Semiconductors"},
    # {"id": "C119857082", "label": "Machine Learning"},
]


# ============================================================
# Pagination & Limits
# ============================================================


MAX_WORKS_PAGES = 10  # Unused for Stage 1 full cursor backfill
WORKS_PER_PAGE = 100  # Stage 1 full backfill default
MAX_COAUTHOR_WORKS_PAGES = (
    4  # Pages of recent works to fetch per author for co-author analysis
)
MAX_COAUTHORS_TO_CHECK = 50  # Max co-authors to profile per researcher


# ============================================================
# Rate Limiting (seconds between requests)
# ============================================================


OPENALEX_SLEEP = 0.11  # ~9 req/s with polite pool
S2_SLEEP = 1.1  # ~1 req/s without API key


# ============================================================
# Staleness Window (days)
# ============================================================
# Cached profiles older than this are re-fetched on the next run.


STALENESS_DAYS = 30


# ============================================================
# Mentee Classification Thresholds
# ============================================================


MENTEE_MAX_WORKS = 20  # works_count <= this => likely student/postdoc


# ============================================================
# Data Paths
# ============================================================


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
INTERMEDIATE_DIR = os.path.join(DATA_DIR, "intermediate")


PAPERS_DIR = os.path.join(RAW_DIR, "papers")
FIELD_AUTHOR_MAP_FILE = os.path.join(INTERMEDIATE_DIR, "field_author_map.json")


def papers_file_for(concept_label):
    """Return the papers.jsonl path for a given concept label."""
    slug = concept_label.lower().replace(" ", "_")
    return os.path.join(PAPERS_DIR, f"papers_{slug}.jsonl")


PROFILES_DIR = os.path.join(RAW_DIR, "profiles")
COAUTHORS_DIR = os.path.join(RAW_DIR, "coauthors")
INSTITUTIONS_DIR = os.path.join(RAW_DIR, "institutions")


KNOWLEDGE_BASE_FILE = os.path.join(DATA_DIR, "knowledge_base.json")
SUMMARY_EXCEL_FILE = os.path.join(DATA_DIR, "knowledge_base_summary.xlsx")
SUMMARY_SCHEMA_FILE = os.path.join(DATA_DIR, "knowledge_base_summary_schema.json")


def ensure_dirs():
    """Create all output directories if they don't exist."""
    for d in [
        DATA_DIR,
        RAW_DIR,
        INTERMEDIATE_DIR,
        PAPERS_DIR,
        PROFILES_DIR,
        COAUTHORS_DIR,
        INSTITUTIONS_DIR,
    ]:
        os.makedirs(d, exist_ok=True)


# ============================================================
# Embedding / Vector DB / LLM Configuration
# ============================================================

# OpenAI (for embeddings) or other provider API key. If empty, embedding
# functions will raise until configured.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# Embedding model to use (OpenAI example). Change to your model.
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")

# Pinecone configuration (optional). If not using Pinecone, leave unset.
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "researcher-papers")

# Batch sizes for embedding/upsert
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "64"))
PINECONE_UPSERT_BATCH = int(os.environ.get("PINECONE_UPSERT_BATCH", "100"))


# ============================================================
# Ranking / Search Configuration
# ============================================================

TOP_K_PINECONE = int(os.environ.get("TOP_K_PINECONE", "500"))
MIN_UNIQUE_RESEARCHERS = int(os.environ.get("MIN_UNIQUE_RESEARCHERS", "25"))
MAX_TOP_K_PINECONE = int(os.environ.get("MAX_TOP_K_PINECONE", "2000"))
TARGET_PAPERS_PER_RESEARCHER = float(
    os.environ.get("TARGET_PAPERS_PER_RESEARCHER", "2.0")
)
Q_DECAY_HALF_LIFE = float(os.environ.get("Q_DECAY_HALF_LIFE", "5"))
Q_DECAY_LAMBDA = float(
    os.environ.get("Q_DECAY_LAMBDA", str(0.6931471805599453 / Q_DECAY_HALF_LIFE))
)
Q_MAX_PAPERS_PER_RESEARCHER = int(os.environ.get("Q_MAX_PAPERS_PER_RESEARCHER", "200"))
Q_RECENCY_LAMBDA = float(os.environ.get("Q_RECENCY_LAMBDA", "0.08"))
Q_CITATION_BETA = float(os.environ.get("Q_CITATION_BETA", "0.10"))

H_WEIGHT = float(os.environ.get("H_WEIGHT", "0.5"))
Q_WEIGHT = float(os.environ.get("Q_WEIGHT", "0.5"))
PARETO_EPSILON = float(os.environ.get("PARETO_EPSILON", "0.05"))
PARETO_REQUIRE_K = int(os.environ.get("PARETO_REQUIRE_K", "1"))

H_COMPONENT_WEIGHTS = {
    "h_index": 0.45,
    "total_citations": 0.25,
    "quality_score": 0.15,
    "recency_score": 0.10,
    "seniority_score": 0.05,
}

# ============================================================
# Simple Ranking Mode (professor's feedback)
# ============================================================
# When True: Q = avg(top-20 similarity scores, zero-padded);
#            H = min(h_index / 100, 1.0)
# When False: legacy weighted/decay scoring is used instead.
USE_SIMPLE_RANKING = os.environ.get("USE_SIMPLE_RANKING", "true").lower() != "false"
# Number of top paper similarity scores to average for simple Q
Q_TOP_PAPERS = int(os.environ.get("Q_TOP_PAPERS", "20"))
