"""
Robust link verification utilities for researcher/institution/topic pages.

Provides a scoring-based verifier that combines multiple signals
to determine whether a candidate URL is highly likely to refer to
the requested `name` / `institution`.

Key signals:
- Known-provider patterns (ORCID, Google Scholar, Semantic Scholar, ResearchGate, Academia)
- Page title / meta tags matching the full name
- JSON-LD schema.org Person name
- URL path containing name tokens
- Presence of affiliation / institution tokens

Returns the top-ranked links that exceed a configurable confidence threshold.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Known provider regexes (highly indicative)
KNOWN_PROVIDERS = {
    "orcid": re.compile(r"orcid.org", re.I),
    "google_scholar": re.compile(r"scholar.google\.(com|[a-z]{2,3})/citations", re.I),
    "semantic_scholar": re.compile(r"semanticscholar.org/author", re.I),
    "researchgate": re.compile(r"researchgate.net/profile", re.I),
    "academia": re.compile(r"academia.edu", re.I),
    "university_profile": re.compile(r"/faculty|/people|/staff|/person/|/~", re.I),
}


def _clean(text: str) -> str:
    return (text or "").strip().lower()


def _extract_jsonld_person(soup: BeautifulSoup) -> Dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except Exception:
            continue
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get("@type") in ("Person", "PersonRole"):
                    return entry
        elif isinstance(data, dict) and data.get("@type") in ("Person", "PersonRole"):
            return data
    return None


def _title_and_meta(soup: BeautifulSoup) -> Tuple[str, str]:
    title = soup.title.string if soup.title and soup.title.string else ""
    desc = ""
    m = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if m and m.get("content"):
        desc = m.get("content")
    # also check og:title / twitter:title
    og = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "twitter:title"})
    if og and og.get("content"):
        title = title or og.get("content")
    return _clean(title), _clean(desc)


def _url_name_signal(url: str, name_tokens: List[str]) -> float:
    path = re.sub(r"^https?://", "", url, flags=re.I).split("/", 1)
    if len(path) < 2:
        return 0.0
    slug = path[1].lower()
    score = 0.0
    # require at least last name present
    last = name_tokens[-1] if name_tokens else ""
    if last and re.search(re.escape(last), slug):
        score += 0.12
    # first initial + last name patterns
    if len(name_tokens) >= 2:
        fi = name_tokens[0][0]
        if re.search(re.escape(fi) + ".*" + re.escape(last), slug):
            score += 0.08
    return score


def _provider_signal(url: str) -> float:
    for name, rx in KNOWN_PROVIDERS.items():
        if rx.search(url):
            # ORCID / Google Scholar are very strong signals
            if name in ("orcid", "google_scholar"):
                return 0.5
            return 0.25
    return 0.0


def score_link(url: str, name: str | None, institution: str | None, timeout: int = 8) -> Tuple[float, Dict]:
    """Fetch the URL and compute a confidence score (0.0-1.0).

    Returns (score, details) where details explains contributing signals.
    """
    score = 0.0
    details: Dict = {"url": url, "signals": {}}

    try:
        headers = {"User-Agent": "ResearchAI-LinkVerifier/1.0 (+https://example.com)"}
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as e:
        details["error"] = f"fetch-failed: {e}"
        return 0.0, details

    if resp.status_code < 200 or resp.status_code >= 400:
        details["status_code"] = resp.status_code
        return 0.0, details

    html = resp.text or ""
    soup = BeautifulSoup(html, "html.parser")

    name_clean = _clean(name or "")
    inst_clean = _clean(institution or "")
    name_tokens = [t for t in re.split(r"\s+", name_clean) if t]

    # provider signal
    provider = _provider_signal(url)
    if provider:
        details["provider_signal"] = provider
        score += provider

    # title and meta
    title, desc = _title_and_meta(soup)
    details["title"] = title
    details["meta_desc"] = desc

    # exact full-name in title/meta
    if name_clean and name_clean in title:
        details.setdefault("signals", {})["title_fullname"] = True
        score += 0.2
    elif name_clean and name_clean in desc:
        details.setdefault("signals", {})["meta_fullname"] = True
        score += 0.12

    # loose name matching: require last name plus at least one other token
    if name_tokens and len(name_tokens) >= 2:
        last = name_tokens[-1]
        if last and last in title:
            details.setdefault("signals", {})["title_lastname"] = True
            score += 0.06

    # JSON-LD Person
    try:
        person = _extract_jsonld_person(soup)
        if person and isinstance(person, dict):
            pname = _clean(person.get("name", ""))
            if pname and name_clean and name_clean == pname:
                details.setdefault("signals", {})["jsonld_exact_name"] = True
                score += 0.25
            elif pname and name_tokens and all(t in pname for t in name_tokens[:2]):
                details.setdefault("signals", {})["jsonld_partial_name"] = True
                score += 0.12
            # affiliation in jsonld
            if person.get("affiliation"):
                aff = _clean(json.dumps(person.get("affiliation")))
                if inst_clean and inst_clean in aff:
                    details.setdefault("signals", {})["jsonld_affiliation"] = True
                    score += 0.08
    except Exception:
        pass

    # affiliation token anywhere in page
    if inst_clean and inst_clean and inst_clean in _clean(html):
        details.setdefault("signals", {})["page_affiliation"] = True
        score += 0.06

    # url pattern signals
    url_sig = _url_name_signal(url, name_tokens)
    if url_sig:
        details.setdefault("signals", {})["url_pattern"] = url_sig
        score += url_sig

    # clamp
    final = min(1.0, score)
    details["score_raw"] = score
    details["score"] = final
    return final, details


def verify_and_rank(links: List[str], name: str | None, institution: str | None, threshold: float = 0.75) -> List[Dict]:
    """Verify candidate links and return the top verified links above threshold.

    Strategy: score each candidate, sort by score desc, return only the top
    link(s) that meet the confidence `threshold`. Prefer returning a single
    high-quality link rather than many marginal ones.
    """
    scored: List[Tuple[float, str, Dict]] = []
    for url in links:
        u = (url or "").strip()
        if not u:
            continue
        if not re.match(r"^https?://", u, re.I):
            u = "https://" + u
        try:
            s, details = score_link(u, name, institution)
            scored.append((s, u, details))
        except Exception as e:
            logger.info("score_link error for %s: %s", u, e)

    scored.sort(key=lambda t: t[0], reverse=True)
    results: List[Dict] = []
    if not scored:
        return results

    # choose the top result if it exceeds threshold
    top_score, top_url, top_details = scored[0]
    if top_score >= threshold:
        label = re.sub(r"^https?://", "", top_url).split("/")[0]
        results.append({"url": top_url, "label": label, "score": round(top_score, 3), "details": top_details})
    return results
