"""
Module 3, task 3.3a — embed all chunks to disk, RESUMABLY.

CPU embedding of the whole corpus takes ~13 min here, and a single run can get
interrupted. So we embed in batches and save after each one: re-running picks
up exactly where it left off (done = rows already saved). The slow part
(embedding) is decoupled from the fast part (Qdrant upsert in index.py).

Run (repeat until it prints DONE):  uv run python -m src.retrieval.embed_corpus
"""

import json
from pathlib import Path

import numpy as np

from src.retrieval.embed import embed_passages

CHUNKS_PATH = Path("data/processed/ai_act_chunks.jsonl")
EMB_PATH = Path("data/processed/embeddings.npy")
BATCH = 32


def main() -> None:
    texts = [
        json.loads(line)["text"]
        for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
    ]
    total = len(texts)

    if EMB_PATH.exists():
        emb = np.load(EMB_PATH)
        done = emb.shape[0]
    else:
        emb = np.empty((0, 384), dtype=np.float32)
        done = 0

    if done >= total:
        print(f"DONE — {done}/{total} already embedded -> {EMB_PATH}")
        return

    print(f"resuming at {done}/{total}...", flush=True)
    for start in range(done, total, BATCH):
        batch = texts[start:start + BATCH]
        vecs = np.array([v for v in embed_passages(batch)], dtype=np.float32)
        emb = np.vstack([emb, vecs])
        np.save(EMB_PATH, emb)               # checkpoint after every batch
        print(f"  {emb.shape[0]}/{total}", flush=True)

    print(f"DONE — embedded {emb.shape[0]}/{total} -> {EMB_PATH}")


if __name__ == "__main__":
    main()
