import requests
import pandas as pd
import time
from urllib.parse import quote

OPENALEX_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"

HEADERS = {
    "User-Agent": "openalex-semantic-scholar-enrichment/0.1 (contact: your_email@example.com)"
}


def openalex_get(url, params=None, timeout=30):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def reconstruct_abstract(abstract_inverted_index):
    """
    OpenAlex stores abstracts as an inverted index. This reconstructs the full text.
    Returns None if missing.
    """
    if not abstract_inverted_index:
        return None

    # Build position -> word map
    position_to_word = {}
    for word, positions in abstract_inverted_index.items():
        for pos in positions:
            position_to_word[pos] = word

    # Reconstruct in order
    if not position_to_word:
        return None

    max_pos = max(position_to_word.keys())
    words = [position_to_word.get(i, "") for i in range(max_pos + 1)]
    text = " ".join([w for w in words if w]).strip()
    return text if text else None


def fetch_s2_abstract(doi=None, title=None, sleep_s=0.2):
    """
    Try Semantic Scholar for abstract.
    1) DOI lookup (best)
    2) title search fallback
    """
    # 1) DOI lookup
    if doi:
        doi_clean = doi.replace("https://doi.org/", "").strip()
        url = f"{S2_BASE}/paper/DOI:{quote(doi_clean)}"
        params = {"fields": "title,abstract,year"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        time.sleep(sleep_s)
        if r.status_code == 200:
            data = r.json()
            return data.get("abstract")

    # 2) Title search fallback
    if title:
        url = f"{S2_BASE}/paper/search"
        params = {"query": title, "limit": 1, "fields": "title,abstract,year"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        time.sleep(sleep_s)
        if r.status_code == 200:
            data = r.json()
            hits = data.get("data", [])
            if hits:
                return hits[0].get("abstract")

    return None


def is_education_inst(inst):
    """
    inst is an OpenAlex institution object (can be None).
    We keep only education institutions.
    """
    if not inst:
        return False
    return inst.get("type") == "education"


def main():
    # Your OpenAlex query (AI concept)
    # Note: OpenAlex expects per_page not per-page (some endpoints accept both but per_page is standard)
    works_url = f"{OPENALEX_BASE}/works"
    params = {
        "filter": "concept.id:C154945302",
        "per_page": 25,
        "sort": "cited_by_count:desc",
    }

    data = openalex_get(works_url, params=params)
    works = data.get("results", [])

    rows = []

    for work in works:
        paper_title = work.get("title")
        work_id = work.get("id")
        doi = work.get("doi")
        pub_year = work.get("publication_year")
        cited_by = work.get("cited_by_count")

        # OpenAlex abstract (inverted index)
        openalex_abs = reconstruct_abstract(work.get("abstract_inverted_index"))

        # We’ll fetch Semantic Scholar abstract only if OA doesn’t have it
        s2_abs = None
        if not openalex_abs:
            s2_abs = fetch_s2_abstract(doi=doi, title=paper_title)

        final_abs = openalex_abs or s2_abs

        authorships = work.get("authorships", [])
        total_authors = len(authorships)

        for idx, auth in enumerate(authorships, start=1):
            author = auth.get("author") or {}
            author_name = author.get("display_name")
            author_position_text = auth.get(
                "author_position"
            )  # first/middle/last from OpenAlex
            author_position_num = idx  # numeric order in the authorship list

            corresponding = bool(auth.get("is_corresponding"))

            # Institutions list inside each authorship
            insts = auth.get("institutions") or []

            # Keep only education institutions
            edu_insts = [i for i in insts if is_education_inst(i)]

            # If none are education, skip this author row entirely
            if not edu_insts:
                continue

            # If multiple education institutions, you can either:
            # A) create one row per institution (current)
            # B) join them into one cell
            for inst in edu_insts:
                inst_name = inst.get("display_name")
                inst_type = inst.get("type")
                country = inst.get("country_code")

                rows.append(
                    {
                        "Paper Title": paper_title,
                        "OpenAlex Work ID": work_id,
                        "DOI": doi,
                        "Publication Year": pub_year,
                        "Citation Count": cited_by,
                        "Author Name": author_name,
                        "Author Position (text)": author_position_text,  # first/middle/last from OpenAlex
                        "Author Position (num)": f"{author_position_num}/{total_authors}",  # 1/4 etc
                        "Corresponding Author": corresponding,
                        "Institution": inst_name,
                        "Institution Type": inst_type,
                        "Country": country,
                        "Abstract": final_abs,
                    }
                )

    df = pd.DataFrame(rows)

    # Print all columns (no truncation)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 120)

    if df.empty:
        print("No rows found after filtering to education institutions.")
        return

    print(df.to_string(index=False))

    # Save output
    out = "openalex_education_authors_with_abstracts.xlsx"
    df.to_excel(out, index=False)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
