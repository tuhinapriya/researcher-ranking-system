#!/usr/bin/env python3
"""Analyze overlap between semiconductor-related OpenAlex topic buckets.

This script fetches a paper sample for each requested bucket and computes:
- total papers per bucket (sampled)
- unique papers per bucket (not seen in any other bucket)
- pairwise overlap counts
- pairwise overlap percentages (row-normalized)
- redundancy percentages

Resolution strategy per bucket:
1) Try to resolve an OpenAlex Topic ID via /topics search.
2) If no good topic match is found, fall back to /works?search=<phrase>.

Usage:
    python scripts/analyze_openalex_topic_overlap.py --sample-size 800

Optional:
    python scripts/analyze_openalex_topic_overlap.py \
      --sample-size 800 \
      --contact-email you@example.com \
      --output-json data/semiconductor_topic_overlap.json
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

OPENALEX_BASE = "https://api.openalex.org"
WORKS_PER_PAGE = 200

TOPIC_LABELS = [
    "Semiconductor",
    "Semiconductor Equipment",
    "Semiconductor Processes",
    "Semiconductor Materials",
    "Semiconductor Devices",
]

TOPIC_MATCH_RULES = {
    "Semiconductor": {
        "required": ["semiconductor"],
        "preferred": ["materials", "devices"],
        "forbidden": [],
    },
    "Semiconductor Equipment": {
        "required": ["semiconductor", "equipment"],
        "preferred": ["tool", "fab", "lithography", "etch", "deposition"],
        "forbidden": [],
    },
    "Semiconductor Processes": {
        "required": ["semiconductor", "process"],
        "preferred": ["fabrication", "manufacturing", "etch", "deposition"],
        "forbidden": [],
    },
    "Semiconductor Materials": {
        "required": ["semiconductor", "material"],
        "preferred": ["interface", "thin film", "gan", "sic", "chalcogenide"],
        "forbidden": ["equipment"],
    },
    "Semiconductor Devices": {
        "required": ["semiconductor", "device"],
        "preferred": ["transistor", "detector", "circuit"],
        "forbidden": ["equipment"],
    },
}


@dataclass
class TopicResolution:
    label: str
    mode: str  # "topic" or "search"
    topic_id: Optional[str]
    topic_name: Optional[str]
    works_count: Optional[int]


def openalex_get(url: str, contact_email: Optional[str] = None) -> dict:
    headers = {}
    if contact_email:
        headers["User-Agent"] = f"openalex-overlap-audit/1.0 (mailto:{contact_email})"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def topic_id_from_url(openalex_id: Optional[str]) -> Optional[str]:
    if not openalex_id:
        return None
    return openalex_id.rstrip("/").split("/")[-1]


def _resolution_score(label: str, candidate_name: str, works_count: int) -> float:
    label_l = label.lower().strip()
    name_l = (candidate_name or "").lower().strip()
    label_tokens = [t for t in label_l.replace("-", " ").split() if t]

    score = 0.0
    if name_l == label_l:
        score += 100.0

    token_hits = sum(1 for token in label_tokens if token in name_l)
    if label_tokens:
        score += 50.0 * (token_hits / len(label_tokens))

    if "semiconductor" in name_l:
        score += 20.0

    rules = TOPIC_MATCH_RULES.get(label, {})
    required = rules.get("required", [])
    preferred = rules.get("preferred", [])
    forbidden = rules.get("forbidden", [])

    for token in required:
        if token in name_l:
            score += 25.0
        else:
            score -= 50.0

    for token in preferred:
        if token in name_l:
            score += 8.0

    for token in forbidden:
        if token in name_l:
            score -= 25.0

    score += min(math.log10(max(works_count, 1)), 7.0)
    return score


def resolve_topic(label: str, contact_email: Optional[str]) -> TopicResolution:
    url = f"{OPENALEX_BASE}/topics?search={quote_plus(label)}&per-page=25"
    payload = openalex_get(url, contact_email=contact_email)
    results = payload.get("results", [])

    if not results:
        return TopicResolution(
            label=label,
            mode="search",
            topic_id=None,
            topic_name=None,
            works_count=None,
        )

    best = None
    best_score = -1.0
    for row in results:
        topic_name = row.get("display_name") or ""
        works_count = int(row.get("works_count") or 0)
        score = _resolution_score(label, topic_name, works_count)
        if score > best_score:
            best_score = score
            best = row

    if not best:
        return TopicResolution(
            label=label,
            mode="search",
            topic_id=None,
            topic_name=None,
            works_count=None,
        )

    best_name = best.get("display_name") or ""
    best_id = topic_id_from_url(best.get("id"))
    best_count = int(best.get("works_count") or 0)

    # Guardrail: if required token coverage is weak, use free-text works search instead.
    token_hits = 0
    rules = TOPIC_MATCH_RULES.get(label, {})
    label_tokens = list(rules.get("required", [])) or [
        t for t in label.lower().split() if t
    ]
    name_l = best_name.lower()
    for token in label_tokens:
        if token in name_l:
            token_hits += 1
    token_coverage = token_hits / len(label_tokens) if label_tokens else 0.0

    if token_coverage < 0.66:
        return TopicResolution(
            label=label,
            mode="search",
            topic_id=None,
            topic_name=None,
            works_count=None,
        )

    return TopicResolution(
        label=label,
        mode="topic",
        topic_id=best_id,
        topic_name=best_name,
        works_count=best_count,
    )


def resolve_topic_by_mode(
    label: str,
    contact_email: Optional[str],
    resolution_mode: str,
) -> TopicResolution:
    if resolution_mode == "search":
        return TopicResolution(
            label=label,
            mode="search",
            topic_id=None,
            topic_name=None,
            works_count=None,
        )
    return resolve_topic(label, contact_email=contact_email)


def work_id_from_url(openalex_id: Optional[str]) -> Optional[str]:
    if not openalex_id:
        return None
    return openalex_id.rstrip("/").split("/")[-1]


def _build_works_url(
    *,
    resolution: TopicResolution,
    cursor: str,
    per_page: int,
) -> str:
    if resolution.mode == "topic" and resolution.topic_id:
        return (
            f"{OPENALEX_BASE}/works?filter=primary_topic.id:{resolution.topic_id}"
            f"&sort=cited_by_count:desc&per-page={per_page}&cursor={quote_plus(cursor)}"
        )

    # Fallback to broad OpenAlex search when no strong topic-id match exists.
    return (
        f"{OPENALEX_BASE}/works?search={quote_plus(resolution.label)}"
        f"&sort=cited_by_count:desc&per-page={per_page}&cursor={quote_plus(cursor)}"
    )


def researcher_id_from_url(openalex_id: Optional[str]) -> Optional[str]:
    if not openalex_id:
        return None
    return openalex_id.rstrip("/").split("/")[-1]


def fetch_work_and_researcher_ids(
    resolution: TopicResolution,
    sample_size: int,
    contact_email: Optional[str],
    sleep_seconds: float,
) -> Tuple[Set[str], Set[str]]:
    collected_papers: Set[str] = set()
    collected_researchers: Set[str] = set()
    cursor = "*"

    while len(collected_papers) < sample_size:
        url = _build_works_url(
            resolution=resolution,
            cursor=cursor,
            per_page=WORKS_PER_PAGE,
        )
        payload = openalex_get(url, contact_email=contact_email)
        results = payload.get("results", [])
        if not results:
            break

        for row in results:
            wid = work_id_from_url(row.get("id"))
            if wid:
                collected_papers.add(wid)

            for authorship in row.get("authorships") or []:
                author_obj = authorship.get("author") or {}
                rid = researcher_id_from_url(author_obj.get("id"))
                if rid:
                    collected_researchers.add(rid)

            if len(collected_papers) >= sample_size:
                break

        next_cursor = (payload.get("meta") or {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return collected_papers, collected_researchers


def pairwise_overlap_count(a: Set[str], b: Set[str]) -> int:
    return len(a.intersection(b))


def pairwise_overlap_pct_row(a: Set[str], b: Set[str]) -> float:
    if not a:
        return 0.0
    return 100.0 * len(a.intersection(b)) / len(a)


def unique_count(label: str, topic_sets: Dict[str, Set[str]]) -> int:
    mine = topic_sets[label]
    others_union: Set[str] = set()
    for other_label, other_set in topic_sets.items():
        if other_label == label:
            continue
        others_union |= other_set
    return len(mine - others_union)


def print_totals_and_uniques(
    topic_sets: Dict[str, Set[str]],
    entity_label: str,
) -> Dict[str, Dict[str, float]]:
    summary = {}
    print(f"\n=== Totals and Unique {entity_label.title()} ===")
    print(f"{'Topic':34s} {'Total':>8s} {'Unique':>8s} {'Redundancy %':>13s}")
    print("-" * 70)

    for label, papers in topic_sets.items():
        total = len(papers)
        uniq = unique_count(label, topic_sets)
        redundancy = 0.0 if total == 0 else 100.0 * (1.0 - (uniq / total))
        summary[label] = {
            "total": total,
            "unique": uniq,
            "redundancy_pct": redundancy,
        }
        print(f"{label:34s} {total:8d} {uniq:8d} {redundancy:13.2f}")

    total_sampled = sum(len(s) for s in topic_sets.values())
    union_count = len(set().union(*topic_sets.values()))
    overall_redundancy = (
        0.0 if total_sampled == 0 else 100.0 * (1.0 - union_count / total_sampled)
    )
    print("-" * 70)
    print(
        f"{'ALL TOPICS (sample aggregate)':34s} {total_sampled:8d} {union_count:8d} {overall_redundancy:13.2f}"
    )

    return summary


def print_overlap_matrix(
    topic_sets: Dict[str, Set[str]], as_percent: bool
) -> List[List[float]]:
    labels = list(topic_sets.keys())
    matrix: List[List[float]] = []

    title = (
        "Pairwise Overlap % (row-normalized: overlap / row total)"
        if as_percent
        else "Pairwise Overlap Counts"
    )
    print(f"\n=== {title} ===")

    header = ["Topic"] + labels
    col_width = 22
    print("".join(h[:col_width].ljust(col_width) for h in header))
    print("-" * (col_width * len(header)))

    for row_label in labels:
        row_vals: List[float] = []
        row_cells = [row_label[:col_width].ljust(col_width)]
        for col_label in labels:
            a = topic_sets[row_label]
            b = topic_sets[col_label]
            if as_percent:
                val = pairwise_overlap_pct_row(a, b)
                row_cells.append(f"{val:>14.2f}%  ")
            else:
                val = float(pairwise_overlap_count(a, b))
                row_cells.append(f"{int(val):>14d}  ")
            row_vals.append(val)
        print("".join(row_cells))
        matrix.append(row_vals)

    return matrix


def semiconductor_superset_recommendation(topic_sets: Dict[str, Set[str]]) -> str:
    if "Semiconductor" not in topic_sets:
        return "Superset check skipped: 'Semiconductor' bucket not present."

    semi = topic_sets["Semiconductor"]
    if not semi:
        return "Superset check skipped: 'Semiconductor' has no sampled papers."

    thresholds = []
    for label, papers in topic_sets.items():
        if label == "Semiconductor":
            continue
        coverage = 0.0 if not papers else 100.0 * len(papers & semi) / len(papers)
        thresholds.append((label, coverage, len(papers - semi), len(papers)))

    lines = ["\n=== Recommendation: Should 'Semiconductor' be kept? ==="]
    for label, coverage, missed, total in thresholds:
        lines.append(
            f"- Coverage of {label} by Semiconductor: {coverage:.2f}% (missed {missed}/{total} sampled papers)"
        )

    min_coverage = min((c for _, c, _, _ in thresholds), default=0.0)
    semiconductor_unique = unique_count("Semiconductor", topic_sets)
    semiconductor_total = len(semi)
    semiconductor_unique_pct = (
        0.0
        if semiconductor_total == 0
        else 100.0 * semiconductor_unique / semiconductor_total
    )

    if min_coverage >= 90.0 and semiconductor_unique_pct < 10.0:
        lines.append(
            "- Conclusion: Semiconductor behaves like a broad superset with low unique value. "
            "You can likely drop it and keep specific categories."
        )
    elif min_coverage >= 90.0:
        lines.append(
            "- Conclusion: Semiconductor is close to a superset, but it still adds non-trivial unique papers. "
            "Keep it only if broad recall is important."
        )
    else:
        lines.append(
            "- Conclusion: Semiconductor is not a reliable superset for all specific categories. "
            "Keep specific categories and consider Semiconductor optional."
        )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze overlap between OpenAlex semiconductor topic buckets"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=800,
        help="Target number of unique papers to sample per topic bucket (default: 800)",
    )
    parser.add_argument(
        "--resolution-mode",
        choices=["auto", "search"],
        default="auto",
        help=(
            "How to map bucket labels to OpenAlex retrieval. "
            "'auto' = topic-id when confidently resolvable, else search fallback. "
            "'search' = use works search for all labels."
        ),
    )
    parser.add_argument(
        "--contact-email",
        default=None,
        help="Optional contact email for OpenAlex polite pool user-agent",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.11,
        help="Sleep between paged API calls (default: 0.11)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional output path to save machine-readable results as JSON",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=== OpenAlex Topic Overlap Audit ===")
    print(f"Sample size per bucket: {args.sample_size}")
    print(f"Resolution mode: {args.resolution_mode}")

    resolutions: Dict[str, TopicResolution] = {}
    topic_sets: Dict[str, Set[str]] = {}
    researcher_sets: Dict[str, Set[str]] = {}

    for label in TOPIC_LABELS:
        resolution = resolve_topic_by_mode(
            label,
            contact_email=args.contact_email,
            resolution_mode=args.resolution_mode,
        )
        resolutions[label] = resolution

        if resolution.mode == "topic":
            print(
                f"- {label}: using topic id {resolution.topic_id} "
                f"({resolution.topic_name}; works_count={resolution.works_count})"
            )
        else:
            print(f"- {label}: no strong topic-id match, using works search fallback")

        papers, researchers = fetch_work_and_researcher_ids(
            resolution=resolution,
            sample_size=args.sample_size,
            contact_email=args.contact_email,
            sleep_seconds=args.sleep_seconds,
        )
        topic_sets[label] = papers
        researcher_sets[label] = researchers
        print(f"  sampled unique papers: {len(papers)}")
        print(f"  sampled unique researchers: {len(researchers)}")

    summary = print_totals_and_uniques(topic_sets, entity_label="papers")
    count_matrix = print_overlap_matrix(topic_sets, as_percent=False)
    pct_matrix = print_overlap_matrix(topic_sets, as_percent=True)

    researcher_summary = print_totals_and_uniques(
        researcher_sets, entity_label="researchers"
    )
    researcher_count_matrix = print_overlap_matrix(researcher_sets, as_percent=False)
    researcher_pct_matrix = print_overlap_matrix(researcher_sets, as_percent=True)

    recommendation = semiconductor_superset_recommendation(topic_sets)
    print(recommendation)

    if args.output_json:
        payload = {
            "sample_size": args.sample_size,
            "resolutions": {
                label: {
                    "mode": r.mode,
                    "topic_id": r.topic_id,
                    "topic_name": r.topic_name,
                    "works_count": r.works_count,
                }
                for label, r in resolutions.items()
            },
            "totals": summary,
            "researcher_totals": researcher_summary,
            "labels": list(topic_sets.keys()),
            "overlap_count_matrix": count_matrix,
            "overlap_pct_matrix_row_normalized": pct_matrix,
            "researcher_overlap_count_matrix": researcher_count_matrix,
            "researcher_overlap_pct_matrix_row_normalized": researcher_pct_matrix,
            "recommendation": recommendation,
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved JSON results to: {args.output_json}")


if __name__ == "__main__":
    main()
