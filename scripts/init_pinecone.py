import os
from pinecone import Pinecone, ServerlessSpec

INDEX_NAME = "researcher-papers"
EMBED_DIM = 768

api_key = os.environ.get("PINECONE_API_KEY")
if not api_key:
    raise ValueError("PINECONE_API_KEY not set")

pc = Pinecone(api_key=api_key)

existing = [i["name"] for i in pc.list_indexes()]

if INDEX_NAME not in existing:
    print("Creating Pinecone index...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=EMBED_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
else:
    print("Index already exists.")

print("Pinecone ready.")
