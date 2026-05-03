#!/usr/bin/env python3
"""Compile OpenAlex topic candidates for Bill's topic list.

Outputs:
    data/openalex_topic_candidates.csv
Columns:
    topic_id, topic_name
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import urlopen

OPENALEX_URL_TEMPLATE = (
    "https://api.openalex.org/topics?search={search_term}&per-page=200"
)

SEARCH_TERMS = [
    "Semiconductors",
    "Semiconductor equipment",
    "Semiconductor processes",
    "Semiconductor materials",
    "Semiconductor devices",
    "Photonics",
    "radio frequency for plasma",
    "Plasma science",
    "Etch chemistries",
    "All etch processes",
    "In situ wafer metrology",
    "Real time plasma diagnostics",
    "Novel logic devices",
    "Novel memory devices",
    "ferro electric",
    "2D materials",
    "perovskites",
    "atomic layer deposition",
    "chemical layer deposition",
    "Pulsed laser deposition",
    "electro chemical deposition",
    "Electroplating",
    "Cleaning and surface treatments",
    "High kappa thermal conductivity materials",
    "High-aspect ratio gapfill",
    "Selective deposition",
    "Advanced packaging",
    "3D integration",
    "Heterogeneous integration",
    "Robotics",
    "Fab automation",
    "Equipment automation",
    "Virtual twins",
    "Digital twins",
    "artificial intelligence for semiconductors",
    "Quantum computing",
    "Corrosion resistant coatings",
]


def extract_topic_id(openalex_id: str | None) -> str | None:
    if not openalex_id:
        return None
    return openalex_id.rstrip("/").split("/")[-1]


def fetch_topic_candidates(search_term: str) -> list[dict]:
    url = OPENALEX_URL_TEMPLATE.format(search_term=quote_plus(search_term))
    with urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("results", [])


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_path = repo_root / "data" / "openalex_topic_candidates.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    unique_topics: dict[str, str] = {}

    for term in SEARCH_TERMS:
        candidates = fetch_topic_candidates(term)
        for candidate in candidates:
            topic_id = extract_topic_id(candidate.get("id"))
            topic_name = candidate.get("display_name")
            if not topic_id or not topic_name:
                continue
            if topic_id not in unique_topics:
                unique_topics[topic_id] = topic_name

    sorted_topics = sorted(unique_topics.items(), key=lambda row: row[0])

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["topic_id", "topic_name"])
        for topic_id, topic_name in sorted_topics:
            writer.writerow([topic_id, topic_name])

    print(f"total search terms searched: {len(SEARCH_TERMS)}")
    print(f"total unique OpenAlex topic IDs found: {len(sorted_topics)}")


if __name__ == "__main__":
    main()
