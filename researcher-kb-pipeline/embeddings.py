"""
Embedding helpers: Vertex AI embeddings + Pinecone upsert.
"""

import logging
import os

# Vertex AI Embeddings
try:
    import vertexai
    from vertexai.preview.language_models import TextEmbeddingModel

    vertexai.init()
    _embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
except Exception as e:
    logging.error(f"Vertex AI model load failed: {e}")
    _embedding_model = None

BATCH_SIZE = 10


def get_embeddings_batch(texts):
    """
    Given a list of texts, return a list of embedding vectors (or None for failed).
    Each text: str
    Returns: list[list[float] or None]
    """
    if not _embedding_model:
        logging.error("Vertex AI embedding model not initialized.")
        return [None] * len(texts)
    results = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        try:
            batch_embeddings = _embedding_model.get_embeddings(batch)
            results.extend([emb.values for emb in batch_embeddings])
        except Exception as e:
            logging.error(f"Vertex AI embedding batch failed: {e}")
            results.extend([None] * len(batch))
    return results
