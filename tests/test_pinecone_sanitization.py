import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "researcher-kb-pipeline"))

import pinecone_client
import utils


class DummyIndex:
    def __init__(self):
        self.upserted = []

    def upsert(self, vectors=None):
        self.upserted.append(vectors)


# Patch the real index with dummy
# Patch the real index with dummy
pinecone_client.index = DummyIndex()

vectors = [
    {
        "id": "A5087556046_Spin–phonon interactions in sili",
        "values": [0.1] * 768,
        "metadata": {"researcher_id": "A5087556046"},
    },
    {
        "id": "A5087556046_Caf\u00e9 Learning",
        "values": [0.2] * 768,
        "metadata": {"researcher_id": "A5087556046"},
    },
    {
        "id": "A5087556046_研究人工智能",
        "values": [0.3] * 768,
        "metadata": {"researcher_id": "A5087556046"},
    },
    {
        "id": "A5087556046_AI 🤖 Systems",
        "values": [0.4] * 768,
        "metadata": {"researcher_id": "A5087556046"},
    },
]

pinecone_client.upsert_vectors(vectors)

# Inspect dummy index contents
all_upserted = [vec for batch in pinecone_client.index.upserted for vec in batch]
for v in all_upserted:
    print(v["id"])
    assert utils.is_ascii_safe_identifier(v["id"]), f"Non-ascii id survived: {v['id']}"

print("Pinecone sanitization test passed")
