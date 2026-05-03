import os
import sys
import logging

# 1. Environment Check
print("[CHECK] 1. Environment Variables")
if "PINECONE_API_KEY" in os.environ:
    print("  PINECONE_API_KEY: present")
else:
    print("  ERROR: PINECONE_API_KEY not set")
    sys.exit(1)

# 2. Vertex Check
print("[CHECK] 2. Vertex AI Embedding")
try:
    import vertexai
    from vertexai.preview.language_models import TextEmbeddingModel

    project = os.environ.get("VERTEX_PROJECT") or "project-d84d7c5a-c91d-497b-b78"
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    emb = model.get_embeddings(["test"])[0].values
    print(f"  Vertex embedding length: {len(emb)}")
    if len(emb) != 768:
        print("  ERROR: Vertex embedding length != 768")
        sys.exit(2)
except Exception as e:
    print(f"  ERROR: Vertex AI embedding check failed: {e}")
    sys.exit(2)

# 3. Pinecone Check
print("[CHECK] 3. Pinecone Index")
try:
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    idx_name = "researcher-papers"

    indexes = [i["name"] for i in pc.list_indexes()]
    if idx_name not in indexes:
        print(f"  ERROR: Pinecone index '{idx_name}' does not exist")
        sys.exit(3)

    idx = pc.Index(idx_name)
    stats = idx.describe_index_stats()
    dim = stats.get("dimension")
    print(f"  Pinecone index '{idx_name}' dimension: {dim}")

    if dim != 768:
        print(f"  ERROR: Pinecone index dimension != 768 (got {dim})")
        sys.exit(3)

    print(f"  Pinecone index stats: {stats}")

except Exception as e:
    print(f"  ERROR: Pinecone check failed: {e}")
    sys.exit(3)

# 4. MySQL Check
print("[CHECK] 4. MySQL Connection")
try:
    import mysql.connector

    conn = mysql.connector.connect(
        host="localhost", user="root", password="Uttam@123", database="researcher_kb"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM researchers;")
    count = cursor.fetchone()[0]
    print(f"  MySQL researchers count: {count}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"  ERROR: MySQL check failed: {e}")
    sys.exit(4)

# 5. Run Stage 4 limited test
print("[CHECK] ALL PASSED. Running Stage 4 limited test...")
import subprocess

result = subprocess.run(
    ["python", "researcher-kb-pipeline/pipeline.py", "--stage", "4", "--limit", "5"],
    capture_output=True,
    text=True,
)
print("[STAGE 4 OUTPUT]\n" + result.stdout)
if result.returncode != 0:
    print("  ERROR: Stage 4 failed.")
    sys.exit(5)
