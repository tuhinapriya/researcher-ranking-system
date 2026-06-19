import os
import logging

try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:
    # Allow tests to import this module when pinecone SDK is not installed.
    Pinecone = None
    ServerlessSpec = None

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "").strip()
INDEX_NAME = os.environ.get("PINECONE_INDEX", "researcher-kb-index")
DIMENSION = 768
METRIC = "cosine"
if Pinecone is not None:
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

    try:
        index = pc.Index(INDEX_NAME)
    except Exception:
        # In test environments the pinecone index may not be available; set to None and
        # allow callers/tests to patch `index` with a dummy.
        index = None
else:
    pc = None
    index = None

BATCH_SIZE = 10


def upsert_vectors(vectors):
    """
    Upsert a list of vectors to Pinecone.
    Each vector: {id, values, metadata}
    """
    try:
        # Lazy import to avoid circular import at module load
        import utils

        pinecone_vectors = []
        for v in vectors:
            if not v.get("values"):
                continue
            orig_id = v.get("id")
            # Sanitize id aggressively to enforce ASCII-only allowed chars
            sanitized_id = utils.sanitize_identifier(orig_id, fallback_prefix=None)
            # Handle cases where sanitization strips all meaningful suffix characters
            # leaving a trailing underscore like 'A12345_'. Prefer a stable hashed
            # suffix instead of leaving trailing delimiter-only ids.
            if sanitized_id.endswith("_"):
                parts = orig_id.split("_", 1)
                prefix = parts[0] if parts else None
                if prefix and prefix.isascii() and prefix.isalnum():
                    sanitized_id = f"{prefix}_{utils.stable_hash(orig_id)}"
                else:
                    sanitized_id = f"id_{utils.stable_hash(orig_id)}"

            if sanitized_id != orig_id:
                logging.warning(
                    "Pinecone id sanitized: original=%r sanitized=%r",
                    orig_id,
                    sanitized_id,
                )
            pinecone_vectors.append(
                {
                    "id": sanitized_id,
                    "values": v["values"],
                    "metadata": v.get("metadata", {}),
                }
            )

        if pinecone_vectors:
            for i in range(0, len(pinecone_vectors), BATCH_SIZE):
                batch = pinecone_vectors[i : i + BATCH_SIZE]
                # index.upsert may raise; let callers decide how to handle.
                index.upsert(vectors=batch)

    except Exception as e:
        logging.error(f"Pinecone upsert failed: {e}")
        raise
