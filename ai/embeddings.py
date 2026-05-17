"""
Text embeddings using sentence-transformers.
"""

import logging
from typing import List
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logging.warning("sentence-transformers not available")

logger = logging.getLogger(__name__)

# Global model instance
_model = None


def get_model():
    """Get or initialize the embedding model."""
    global _model
    
    if not EMBEDDINGS_AVAILABLE:
        raise ImportError("sentence-transformers not installed")
    
    if _model is None:
        logger.info("Loading embedding model: all-MiniLM-L6-v2")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Embedding model loaded")
    
    return _model


def embed_text(text: str) -> List[float]:
    """
    Generate embeddings for a single text.
    
    Args:
        text: Text to embed
    
    Returns:
        Embedding vector as list of floats
    """
    try:
        model = get_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    except Exception as e:
        logger.error(f"Failed to embed text: {e}")
        raise


def embed_batch(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """
    Generate embeddings for multiple texts.
    
    Args:
        texts: List of texts to embed
        batch_size: Batch size for processing
    
    Returns:
        List of embedding vectors
    """
    try:
        model = get_model()
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=True
        )
        return embeddings.tolist()
    
    except Exception as e:
        logger.error(f"Failed to embed batch: {e}")
        raise


def is_embeddings_available() -> bool:
    """Check if embeddings are available."""
    return EMBEDDINGS_AVAILABLE
