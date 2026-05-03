import os
import logging

try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:
    raise RuntimeError("pinecone not installed; install with: pip install pinecone")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "").strip()
INDEX_NAME = os.environ.get("PINECONE_INDEX", "researcher-kb-index")
DIMENSION = 768
METRIC = "cosine"

if not PINECONE_API_KEY:
    raise RuntimeError("Missing PINECONE_API_KEY")

# Initialize Pinecone client (modern SDK, no environment needed)
pc = Pinecone(api_key=PINECONE_API_KEY)

# Ensure index exists ONCE
existing_indexes = [idx["name"] for idx in pc.list_indexes()]
if INDEX_NAME not in existing_indexes:
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric=METRIC,
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )

index = pc.Index(INDEX_NAME)

BATCH_SIZE = 10


def upsert_vectors(vectors):
    """
    Upsert a list of vectors to Pinecone.
    Each vector: {id, values, metadata}
    """
    try:
        pinecone_vectors = [
            {
                "id": v["id"],
                "values": v["values"],
                "metadata": v.get("metadata", {}),
            }
            for v in vectors
            if v.get("values")
        ]

        if pinecone_vectors:
            for i in range(0, len(pinecone_vectors), BATCH_SIZE):
                batch = pinecone_vectors[i : i + BATCH_SIZE]
                index.upsert(vectors=batch)

    except Exception as e:
        logging.error(f"Pinecone upsert failed: {e}")
        raise
