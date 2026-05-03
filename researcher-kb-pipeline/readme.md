# Researcher Knowledge Base Pipeline

## What is this?

This pipeline builds a structured knowledge base of academic researchers in
one or more fields of interest (e.g. Artificial Intelligence, Semiconductors).
The output is a JSON file with rich per-researcher profiles -- citations,
h-index, affiliation history, research topics, mentorship signals, institution
quality, and more -- designed to be consumed by an AI agent that can answer
questions like _"who is the most relevant researcher in semiconductors?"_.

## Why not just use Google Scholar?

Google Scholar gives you a single page per person. This pipeline cross-references
**two open APIs** (OpenAlex and Semantic Scholar) and computes derived signals
that neither API provides alone:

- **Granular topic breakdown** per researcher (not just broad fields, but
  sub-topics like "Gallium Nitride Power Devices")
- **Mentee / student estimates** inferred from co-authorship patterns
- **Seniority signals** (last-author ratio, career length, corresponding-author
  ratio) that indicate whether someone is a PI or a junior researcher
- **Institution-level quality metrics** alongside the researcher's own metrics
- **Funding sources** aggregated from paper-level grant data
- **Multi-field relevance** -- a single researcher can appear across multiple
  queried concepts with separate relevance scores for each

## How it works

The pipeline runs in stages. Each stage saves its output to disk, so if it
crashes or you stop it, re-running skips the work already done.

```
OpenAlex /works (per concept)
      |
      v
[Stage 1] Discover papers  -->  data/raw/papers/papers_{concept}.jsonl
      |
      v
[Stage 2] Extract & merge authors across concepts
      |                         -->  data/intermediate/field_author_map.json
      v
[Stage 3a] Fetch full author profiles (OpenAlex + Semantic Scholar)
      |                         -->  data/raw/profiles/{id}.json
      v
[Stage 3b] Co-author & mentee analysis (recent works, same-institution check)
      |                         -->  data/raw/coauthors/{id}.json
      v
[Stage 3c] Institution enrichment (h-index, geo, homepage)
      |                         -->  data/raw/institutions/{id}.json
      v
[Stage 4] Assemble everything into one knowledge base
                                -->  data/knowledge_base.json
                                -->  data/knowledge_base_summary.xlsx
```

### Stage 1 -- Discover Papers

Queries the OpenAlex `/works` API for each concept listed in `config.py`.
Uses cursor-based pagination, sorted by citation count (most-cited first).
For papers missing an abstract in OpenAlex, falls back to Semantic Scholar.
Produces one JSONL file per concept.

### Stage 2 -- Extract & Deduplicate Authors

Parses all paper files from Stage 1. Builds a unified map of unique authors
who are affiliated with education institutions. Each author gets per-concept
stats: which papers they authored, their position (first / middle / last),
whether they were corresponding author, topic distribution, funding sources,
and publication venues. Authors appearing in multiple concepts get separate
entries for each.

### Stage 3a -- Author Profile Enrichment

For each unique author, fetches their full profile from OpenAlex
(`/authors/{id}`), which provides lifetime metrics that go far beyond the
papers we found in Stage 1:

- Total works count and total citations (lifetime, not just in-field)
- h-index, i10-index, 2-year mean citedness
- Full affiliation history with years (career trajectory)
- Research concept scores (breadth of expertise)
- Year-by-year citation trend

Also searches Semantic Scholar by author name to find their homepage URL and
cross-reference metrics.

### Stage 3b -- Co-author / Mentee Analysis

For each researcher, fetches their recent works (last 5 years) and identifies
co-authors at the same institution with low publication counts. These are
classified as likely mentees (students / postdocs). Also computes seniority
signals: last-author ratio and corresponding-author ratio from recent papers.

This is heuristic -- no API provides a "number of students" field -- but it
gives a useful approximation.

### Stage 3c -- Institution Enrichment

Fetches the OpenAlex institution profile for each unique institution in the
dataset. Provides institution-level h-index, total citation count, geographic
location, and homepage URL. Institutions are cached and shared across
researchers, so this stage is fast.

### Stage 4 -- Assemble Knowledge Base

Merges everything into `knowledge_base.json`: a JSON array where each element
is one researcher with all their enrichment data. Also produces an Excel
summary spreadsheet. Researchers are sorted by total field citations across
all concepts.

## Quick Start

```bash
pip install -r requirements.txt


# Full run (all concepts, all authors)
python pipeline.py


# Quick test with 10 authors
python pipeline.py --limit 10


# Run only a specific stage
python pipeline.py --stage 3a


# Force re-fetch everything (ignore cache)
python pipeline.py --force
```

## Configuring Concepts

Edit the `CONCEPTS` list in `config.py`:

```python
CONCEPTS = [
   {"id": "C154945302", "label": "Artificial Intelligence"},
   {"id": "C205649164", "label": "Semiconductors"},
   {"id": "C119857082", "label": "Machine Learning"},
]
```

Find concept IDs at https://api.openalex.org/concepts?search=your+field

## CLI Options

```
python pipeline.py [OPTIONS]


--stage {all,1,2,3,3a,3b,3c,4}   Run a specific stage (default: all)
--force                            Re-fetch even if cached data exists
--limit N                          Process only top N authors (stages 2-4)
```

## Output

### knowledge_base.json

JSON array of researcher profiles. Each profile has the sections below.
The **Source** column shows which API each field comes from.

**1. Identity**

- `name` -- display name (OpenAlex /authors)
- `name_alternatives` -- alternate spellings (OpenAlex /authors)
- `orcid` -- ORCID identifier (OpenAlex /authors)
- `external_ids.scopus` -- Scopus author ID (OpenAlex /authors)
- `external_ids.wikipedia` -- Wikipedia page (OpenAlex /authors)
- `external_ids.twitter` -- Twitter handle (OpenAlex /authors)
- `semantic_scholar.url` -- Semantic Scholar profile URL (S2 /author/search)
- `semantic_scholar.homepage` -- personal / lab homepage (S2 /author/search)

**2. Global Metrics** (lifetime, not field-specific)

- `total_works` -- total publications (OpenAlex /authors)
- `total_citations` -- total lifetime citations (OpenAlex /authors)
- `h_index` -- h-index (OpenAlex /authors)
- `i10_index` -- i10-index (OpenAlex /authors)
- `two_year_mean_citedness` -- 2yr impact factor (OpenAlex /authors)

**3. Affiliation**

- `affiliation.current` -- current institution, type, country (OpenAlex /authors `last_known_institutions`)
- `affiliation.history` -- full list of institutions with years (OpenAlex /authors `affiliations`)
- `semantic_scholar.s2_affiliations` -- affiliations from S2 (S2 /author/search)

**4. Research Topics**

- `research_topics_broad` -- top concepts with relevance scores, e.g. "Computer Science: 97" (OpenAlex /authors `x_concepts`)
- `research_topics_granular` -- fine-grained topics aggregated from papers, with 4-level hierarchy: domain > field > subfield > topic (OpenAlex /works `primary_topic`, aggregated in Stage 2)

**5. Citation Trend**

- `citation_trend` -- year-by-year works count and citation count for the last 10 years (OpenAlex /authors `counts_by_year`)

**6. Field Relevance** (one entry per concept the researcher appears in)

- `concept` -- which concept this entry is for (config)
- `papers_in_field` -- number of papers in this concept (computed from OpenAlex /works)
- `field_citations` -- sum of citations on those papers (computed from OpenAlex /works)
- `first_author_papers` -- count where researcher is first author (OpenAlex /works `authorships`)
- `last_author_papers` -- count where researcher is last author (OpenAlex /works `authorships`)
- `corresponding_author_papers` -- count where researcher is corresponding author (OpenAlex /works `authorships`)
- `most_recent_year` -- latest publication year in this field (OpenAlex /works)
- `top_venues` -- journals they publish in for this field (OpenAlex /works `primary_location.source`)
- `funding_sources` -- funders and grant counts (OpenAlex /works `grants`)

**7. Lab & Mentorship** (heuristic, computed in Stage 3b)

- `estimated_mentee_count` -- likely students/postdocs (inferred: co-authors at same institution with low works_count, via OpenAlex /works + OpenAlex /authors)
- `mentee_names` -- names of likely mentees (same source)
- `total_unique_collaborators` -- co-author network size (computed from OpenAlex /works)
- `top_collaborators` -- most frequent co-authors with shared paper counts (computed from OpenAlex /works)
- `seniority_signals.career_start_year` -- earliest year in affiliation history (OpenAlex /authors)
- `seniority_signals.years_active` -- career length (computed from OpenAlex /authors)
- `seniority_signals.last_author_ratio_recent` -- fraction of recent papers as last author (computed from OpenAlex /works)
- `seniority_signals.corresponding_author_ratio_recent` -- fraction as corresponding author (computed from OpenAlex /works)

**8. Institution Quality** (for the researcher's current institution)

- `name` -- institution name (OpenAlex /institutions)
- `h_index` -- institution-level h-index (OpenAlex /institutions `summary_stats`)
- `total_works` -- total research output (OpenAlex /institutions)
- `total_citations` -- total citations (OpenAlex /institutions)
- `two_year_mean_citedness` -- institution impact factor (OpenAlex /institutions `summary_stats`)
- `country`, `city`, `region` -- location (OpenAlex /institutions `geo`)
- `homepage` -- institution website (OpenAlex /institutions)

**9. Papers by Concept** (grouped by concept label)

Each paper includes:

- `title`, `doi`, `year`, `citations` (OpenAlex /works)
- `author_position` -- first/middle/last (OpenAlex /works `authorships`)
- `abstract` -- full text (OpenAlex /works, fallback: S2 /paper)
- `primary_topic` -- granular topic name (OpenAlex /works)
- `grants` -- funder and award ID (OpenAlex /works)
- `venue` -- journal/conference name (OpenAlex /works `primary_location`)

**10. Semantic Scholar Cross-Reference**

- `s2_h_index`, `s2_citation_count`, `s2_paper_count` -- S2's version of metrics (S2 /author/search)
- `s2_affiliations` -- S2's affiliations list (S2 /author/search)

### knowledge_base_summary.xlsx

One row per researcher with key metrics for quick scanning.

## Re-running Monthly

Profiles cached within the last 30 days (configurable: `STALENESS_DAYS` in
`config.py`) are skipped on re-run. So monthly runs only re-fetch stale data,
making incremental updates fast.

```bash
# Monthly update -- just re-run
python pipeline.py
```

## Limitations

- **"Number of students"** is an estimate based on co-authorship heuristics,
  not ground truth.
- **"Lab director" / PI status** is inferred from seniority signals (career
  length, last-author ratio), not from a structured field.
- **Semantic Scholar author matching** uses name search, which can produce
  false matches for common names. OpenAlex data is the primary source.
- **Rate limits** -- OpenAlex ~10 req/s (polite pool), Semantic Scholar ~1
  req/s without an API key. A full run of 300+ authors takes ~20-25 minutes.

## File Structure

```
researcher-kb-pipeline/
 config.py              # Concepts, API settings, rate limits, paths
 utils.py               # Shared helpers (API calls, caching, JSON I/O)
 stage1_discover.py     # Paper discovery
 stage2_extract.py      # Author extraction & merging
 stage3_enrich.py       # 3a: author profiles, 3b: mentees, 3c: institutions
 stage4_assemble.py     # Knowledge base assembly
 pipeline.py            # CLI entry point
 requirements.txt
 data/
   raw/papers/            # One JSONL per concept
   raw/profiles/          # One JSON per author
   raw/coauthors/         # One JSON per author
   raw/institutions/      # One JSON per institution (shared)
   intermediate/          # Merged author map
   knowledge_base.json    # Final output
   knowledge_base_summary.xlsx
```
