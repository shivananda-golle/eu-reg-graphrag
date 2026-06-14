"""
Module 3, task 3.3 — build the Qdrant vector index.

Embeds all chunks and stores each as a point: a 384-dim vector + the chunk's
metadata as payload. Qdrant runs in local/embedded mode (file-persisted under
data/qdrant, no server) — the same client API as Qdrant Cloud, so the AWS
deploy later is a one-line endpoint swap.

Qdrant point ids must be int/UUID, so we use an enumerated int id and keep the
real chunk_id in the payload. Distance = cosine (vectors are normalized).

Run:  uv run python -m src.retrieval.index
"""

import json
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.retrieval.embed import embed_passages

QDRANT_PATH = "data/qdrant"
COLLECTION = "ai_act"
DIM = 384
CHUNKS_PATH = Path("data/processed/ai_act_chunks.jsonl")
EMB_PATH = Path("data/processed/embeddings.npy")


def load_chunks() -> list[dict]:
    return [
        json.loads(line)
        for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
    ]


def build_index() -> None:
    chunks = load_chunks()

    # Reuse the checkpointed embeddings if they match the chunk count; otherwise
    # embed now (slow). Decoupling keeps the Qdrant upsert a seconds-long step.
    if EMB_PATH.exists() and (emb := np.load(EMB_PATH)).shape[0] == len(chunks):
        print(f"using cached embeddings {emb.shape} from {EMB_PATH}")
        vectors = list(emb)
    else:
        print(f"embedding {len(chunks)} chunks (no usable cache)...")
        vectors = embed_passages([c["text"] for c in chunks])

    client = QdrantClient(path=QDRANT_PATH)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)          # idempotent rebuild
    client.create_collection(
        COLLECTION,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    )

    points = [
        PointStruct(id=i, vector=vec.tolist(), payload=chunk)
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]
    client.upsert(COLLECTION, points=points)

    stored = client.count(COLLECTION).count
    print(f"upserted {len(points)} -> collection '{COLLECTION}' now holds {stored}")
    assert stored == len(chunks), f"count mismatch: {stored} != {len(chunks)}"

    # Peek at one stored point to confirm vector + payload landed together.
    sample = client.scroll(COLLECTION, limit=1, with_payload=True, with_vectors=True)[0][0]
    print(f"\nsample point id={sample.id}  vector_dim={len(sample.vector)}")
    print(f"  payload citation: {sample.payload.get('citation')}")
    print(f"  payload node_id : {sample.payload.get('node_id')}")


if __name__ == "__main__":
    build_index()
