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
from urllib.parse import unquote_plus, urlsplit
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Known provider regexes (highly indicative)
KNOWN_PROVIDERS = {
    "paperlantern": re.compile(r"paperlantern\.ai", re.I),
    "openalex": re.compile(r"openalex\.org", re.I),
    "orcid": re.compile(r"orcid.org", re.I),
    "google_scholar": re.compile(r"scholar.google\.(com|[a-z]{2,3})/(citations|scholar)", re.I),
    "semantic_scholar": re.compile(r"semanticscholar.org/(author|search)", re.I),
    "base": re.compile(r"(base-search\.net|baseresearch\.org)", re.I),
    "core": re.compile(r"core\.ac\.uk", re.I),
    "science_gov": re.compile(r"science\.gov", re.I),
    "baidu_scholar": re.compile(r"xueshu\.baidu\.com", re.I),
    "wikipedia": re.compile(r"wikipedia\.org", re.I),
    "researchgate": re.compile(r"researchgate.net/profile", re.I),
    "academia": re.compile(r"academia.edu", re.I),
    "university_profile": re.compile(r"profiles\.stanford\.edu|slac\.stanford\.edu|\.stanford\.edu|/faculty|/people|/staff|/person/|/~", re.I),
}

# Trusted academic sources should clear the verifier without requiring the page
# to be richly annotated. We still require a live HTTP response, but we allow a
# much higher provider baseline so clean profile URLs do not get rejected.
PROVIDER_BASE_SCORES = {
    "paperlantern": 0.6,
    "openalex": 0.6,
    "orcid": 0.8,
    "google_scholar": 0.8,
    "semantic_scholar": 0.78,
    "base": 0.58,
    "core": 0.58,
    "science_gov": 0.55,
    "baidu_scholar": 0.55,
    "wikipedia": 0.52,
    "researchgate": 0.65,
    "academia": 0.6,
    "university_profile": 0.45,
}

NEGATIVE_PAGE_RE = re.compile(
    r"\b("
    r"no results|no result found|no matches found|no matches|nothing found|zero results|0 results|found 0 results|"
    r"not found|page not found|invalid profile|invalid author|couldn't find|could not find|unable to find|does not exist|404|"
    r"captcha|unusual traffic|access denied|security check|detector|human verification|verify you are human|"
    r"javascript required|enable javascript|one moment|please wait while we verify|challenge"
    r")\b",
    re.I,
)


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
    parsed = urlsplit(url)
    slug = " ".join(part for part in (parsed.path, unquote_plus(parsed.query), unquote_plus(parsed.fragment)) if part).lower()
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


def _provider_kind(url: str) -> str | None:
    for name, rx in KNOWN_PROVIDERS.items():
        if rx.search(url):
            return name
    return None


def _provider_signal(url: str) -> Tuple[float, str | None]:
    kind = _provider_kind(url)
    if not kind:
        return 0.0, None
    return PROVIDER_BASE_SCORES.get(kind, 0.0), kind


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

    final_url = getattr(resp, "url", url) or url
    details["final_url"] = final_url

    html = resp.text or ""
    soup = BeautifulSoup(html, "html.parser")

    name_clean = _clean(name or "")
    inst_clean = _clean(institution or "")
    name_tokens = [t for t in re.split(r"\s+", name_clean) if t]
    html_clean = _clean(html)

    final_host = urlsplit(final_url).hostname or ""
    final_host = final_host.lower()
    if final_host.startswith("wappass.baidu.com") or "captcha" in final_url.lower() or "detector" in final_url.lower():
        details["negative_page"] = True
        details["score_raw"] = 0.0
        details["score"] = 0.0
        return 0.0, details

    # provider signal
    provider, provider_kind = _provider_signal(url)
    if provider:
        details["provider_signal"] = provider
        details["provider_kind"] = provider_kind
        score += provider

    # title and meta
    title, desc = _title_and_meta(soup)
    details["title"] = title
    details["meta_desc"] = desc

    if NEGATIVE_PAGE_RE.search(title) or NEGATIVE_PAGE_RE.search(desc) or NEGATIVE_PAGE_RE.search(html_clean):
        details["negative_page"] = True
        details["score_raw"] = 0.0
        details["score"] = 0.0
        return 0.0, details

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
    if inst_clean and inst_clean in html_clean:
        details.setdefault("signals", {})["page_affiliation"] = True
        score += 0.06

    # url pattern signals
    url_sig = _url_name_signal(url, name_tokens)
    if url_sig:
        details.setdefault("signals", {})["url_pattern"] = url_sig
        score += url_sig

    # Trusted provider adjustments:
    # - ORCID / Google Scholar / Semantic Scholar should pass if they resolve,
    #   even when the HTML is thin or partially dynamic.
    # - Stanford / SLAC / lab / academic websites still need some page-level
    #   corroboration to avoid over-accepting unrelated pages on the same host.
    if provider_kind in ("orcid", "google_scholar", "semantic_scholar", "paperlantern", "openalex", "base", "core", "wikipedia"):
        score = max(score, PROVIDER_BASE_SCORES[provider_kind])
    elif provider_kind in ("science_gov", "baidu_scholar"):
        if score < 0.95:
            details["negative_page"] = True
            details["score_raw"] = 0.0
            details["score"] = 0.0
            return 0.0, details
    elif provider_kind == "university_profile":
        if score >= 0.7:
            score = max(score, 0.75)

    # clamp
    final = min(1.0, score)
    details["score_raw"] = score
    details["score"] = final
    return final, details


def verify_and_rank(links: List[str], name: str | None, institution: str | None, threshold: float = 0.75) -> List[Dict]:
    """Verify candidate links and return the top verified links above threshold.

    Strategy: score each candidate, sort by score desc, and return every link
    that clears the confidence `threshold`, up to a small fixed cap so the UI
    stays concise.
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

    for score, url, details in scored[:5]:
        if score < threshold:
            continue
        label = re.sub(r"^https?://", "", url).split("/")[0]
        results.append({"url": url, "label": label, "score": round(score, 3), "details": details})
    return results
