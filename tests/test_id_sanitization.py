import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "researcher-kb-pipeline"))
import utils

cases = [
    (
        "en-dash – in title",
        "A5087556046",
        {
            "title": "Spin–phonon interactions in sili",
            "year": 2023,
            "venue": "Phys Rev",
        },
    ),
    (
        "em-dash — in title",
        "A5087556046",
        {"title": "Energy—momentum relation", "year": 2020},
    ),
    ("accents éü", "A5087556046", {"title": "Café résumé étude", "year": 2019}),
    (
        "CJK 中文日本語",
        "A5087556046",
        {"title": "研究について 中文 日本語", "year": 2021},
    ),
    ("emoji 😀", "A5087556046", {"title": "Novel approach 😀 in ML", "year": 2022}),
    (
        "mixed languages and symbols",
        "A5087556046",
        {"title": "Δ-研究: Spin–phonon — effects 😀", "year": 2024},
    ),
]

import re as _re

allowed_re = _re.compile(r"^[A-Za-z0-9_\-]+$")

failures = []
for desc, researcher, paper in cases:
    pid = utils.safe_paper_id(researcher, paper)
    eid = utils.safe_embedding_id(researcher, pid)
    ok_pid = utils.is_ascii_safe_identifier(pid)
    ok_eid = utils.is_ascii_safe_identifier(eid)
    print(desc, "->", pid, eid)
    if not ok_pid or not ok_eid:
        failures.append((desc, pid, eid))

if failures:
    print("Failures:")
    for f in failures:
        print(f)
    raise SystemExit(1)

print("All sanitization tests passed")
