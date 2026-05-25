"""
Text embeddings for RAG.

Default provider is OpenAI API (no PyTorch in-process). Set EMBEDDING_PROVIDER=local
and install requirements-local-embeddings.txt for offline sentence-transformers.
"""

import logging
from typing import List

import config

logger = logging.getLogger(__name__)

_local_model = None
_openai_client = None


def _provider() -> str:
    return (config.EMBEDDING_PROVIDER or "openai").strip().lower()


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
        _openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


def _get_local_model():
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers not installed. "
                "Use EMBEDDING_PROVIDER=openai or pip install -r requirements-local-embeddings.txt"
            ) from exc
        logger.info("Loading embedding model: all-MiniLM-L6-v2")
        _local_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded")
    return _local_model


def embed_text(text: str) -> List[float]:
    """Generate embeddings for a single text."""
    return embed_batch([text])[0]


def embed_batch(texts: List[str], batch_size: int | None = None) -> List[List[float]]:
    """Generate embeddings for multiple texts."""
    if not texts:
        return []
    batch_size = batch_size or config.EMBEDDING_BATCH_SIZE
    provider = _provider()
    try:
        if provider == "openai":
            return _embed_batch_openai(texts, batch_size)
        if provider == "local":
            return _embed_batch_local(texts, batch_size)
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")
    except Exception as e:
        logger.error("Failed to embed batch (%s): %s", provider, e)
        raise


def _embed_batch_openai(texts: List[str], batch_size: int) -> List[List[float]]:
    client = _get_openai_client()
    model = config.EMBEDDING_MODEL
    out: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=model, input=batch)
        ordered = sorted(resp.data, key=lambda d: d.index)
        out.extend([list(d.embedding) for d in ordered])
    return out


def _embed_batch_local(texts: List[str], batch_size: int) -> List[List[float]]:
    model = _get_local_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        show_progress_bar=len(texts) > 64,
    )
    return embeddings.tolist()


def is_embeddings_available() -> bool:
    """True when the configured embedding provider can run."""
    provider = _provider()
    if provider == "openai":
        return bool(config.OPENAI_API_KEY)
    if provider == "local":
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            return False
    return False
