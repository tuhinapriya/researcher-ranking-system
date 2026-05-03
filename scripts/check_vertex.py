import os
import sys

PROJECT_ID = "project-d84d7c5a-c91d-497b-b78"
LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")

if not PROJECT_ID:
    print("PROJECT_ID environment variable is not set. Set PROJECT_ID and re-run.")
    sys.exit(2)

try:
    import vertexai
    from vertexai.preview.language_models import TextEmbeddingModel
except Exception as e:
    print("Failed to import Vertex AI client libraries:", repr(e))
    print("If missing, install with: pip install google-cloud-aiplatform vertex-ai")
    sys.exit(3)

try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    text = "Gallium Nitride plasma etching for semiconductor fabrication"
    embedding = model.get_embeddings([text])[0].values
    print("Embedding length:", len(embedding))
    print("First 5 values:", embedding[:5])
except Exception as e:
    print("Vertex AI call failed:", repr(e))
    sys.exit(4)
