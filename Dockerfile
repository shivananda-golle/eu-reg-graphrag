# EU AI Act GraphRAG — container for the Streamlit chat UI.
# One image, two targets: Hugging Face Spaces (Docker SDK) and AWS (App Runner/ECS).
# Listens on 7860 (HF default). Secrets (GROQ/NEO4J/LANGFUSE) come from env vars.

FROM python:3.12-slim

# uv (fast, reproducible installs)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Run as non-root uid 1000 (Hugging Face Spaces convention).
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    UV_LINK_MODE=copy
WORKDIR /home/user/app

# 1) Dependencies first (cached layer). --no-install-project: we run from source.
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) App code.
COPY --chown=user src/ ./src/

# 3) Prebuilt data artifacts (the corpus + embeddings). Qdrant is rebuilt from
#    these on first launch; Neo4j is the managed AuraDB instance via env vars.
COPY --chown=user data/processed/ai_act.json \
                   data/processed/ai_act_chunks.jsonl \
                   data/processed/embeddings.npy ./data/processed/

# 4) Bake the embedding model into the image so cold starts don't re-download it.
RUN uv run python -c "from src.retrieval.embed import get_model; get_model()"

EXPOSE 7860
CMD ["uv", "run", "streamlit", "run", "src/app/streamlit_app.py", \
     "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true", \
     "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
