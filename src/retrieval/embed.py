"""
Module 3, task 3.2 — embeddings (fastembed + BGE-small-en-v1.5).

384-dim vectors, CPU/ONNX (no PyTorch). BGE distinguishes *passages* from
*queries* — queries get an instruction prefix — so we expose both. The model is
loaded once and reused.

Run:  uv run python -m src.retrieval.embed   (loads the model + sanity check)
"""

import json
import os
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
# Persistent cache on the Linux filesystem so the ~130 MB model downloads ONCE
# and subsequent loads are seconds, not a re-download.
CACHE_DIR = str(Path.home() / ".cache" / "fastembed")
_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        # threads = all cores: ONNX defaults can run single-threaded on CPU.
        _model = TextEmbedding(
            model_name=MODEL_NAME, cache_dir=CACHE_DIR, threads=os.cpu_count()
        )
    return _model


def embed_passages(texts: list[str]) -> list[np.ndarray]:
    """Embed document chunks (what we store in the index)."""
    return list(get_model().embed(texts))


def embed_query(text: str) -> np.ndarray:
    """Embed a search query (BGE adds its retrieval instruction prefix)."""
    return list(get_model().query_embed([text]))[0]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


if __name__ == "__main__":
    chunks = {
        c["chunk_id"]: c
        for c in (
            json.loads(l)
            for l in Path("data/processed/ai_act_chunks.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }

    qv = embed_query("What makes an AI system high-risk?")
    print(f"query vector dim: {qv.shape[0]} (expected 384)\n")

    # Sanity: a relevant chunk must score higher than an unrelated one.
    relevant = chunks["006.001"]          # Article 6(1) — high-risk classification
    unrelated = chunks["rct_180"]          # a late recital (procedural/closing)
    rv, uv = embed_passages([relevant["text"], unrelated["text"]])

    print("cosine similarity to query 'What makes an AI system high-risk?':")
    print(f"  {relevant['citation']:<16} (relevant)  : {cosine(qv, rv):.3f}")
    print(f"  {unrelated['citation']:<16} (unrelated) : {cosine(qv, uv):.3f}")
    print("\nPASS" if cosine(qv, rv) > cosine(qv, uv) else "\nFAIL — relevant did not win")
