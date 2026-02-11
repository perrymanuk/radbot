"""
Text embedding utilities for the Qdrant memory system.

Uses the google-genai package (not google-generativeai) for Gemini embeddings.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingModel:
    """Data class for embedding model information."""

    name: str
    vector_size: int
    client: Any  # The actual embedding client instance


def get_embedding_model() -> EmbeddingModel:
    """
    Initialize and return the appropriate embedding model based on configuration.

    Returns:
        EmbeddingModel: The configured embedding model
    """
    embed_model = os.getenv("radbot_EMBED_MODEL", "gemini").lower()

    if embed_model != "gemini":
        logger.warning(
            f"Unknown embedding model '{embed_model}', falling back to Gemini"
        )
    return _initialize_gemini_embedding()


def _initialize_gemini_embedding() -> EmbeddingModel:
    """
    Initialize the Gemini embedding model using the google-genai package.

    Returns:
        EmbeddingModel: The initialized embedding model
    """
    from google import genai

    # Get API key: try env var first, then config
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        try:
            from radbot.config.config_loader import config_loader

            config = config_loader.get_config()
            api_key = config.get("api_keys", {}).get("google")
        except Exception as e:
            logger.warning(f"Could not load API key from config: {e}")

    if not api_key:
        raise ValueError(
            "No Google API key found. Set GOOGLE_API_KEY env var or api_keys.google in config.yaml"
        )

    client = genai.Client(api_key=api_key)

    return EmbeddingModel(
        name="gemini-embedding-001",
        vector_size=768,  # Using output_dimensionality=768 for compatibility
        client=client,
    )


def embed_text(
    text: str,
    model: EmbeddingModel,
    is_query: bool = True,
    source: str = "agent_memory",
) -> List[float]:
    """
    Generate embedding vector for a text string.

    Args:
        text: The text to embed
        model: The embedding model to use
        is_query: Whether this is a query (True) or a document (False)
        source: The source system for the embedding

    Returns:
        List of embedding vector values
    """
    try:
        if model.name.startswith("text-embedding") or model.name.startswith("gemini"):
            # google-genai embedding via Client
            task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
            result = model.client.models.embed_content(
                model=model.name,
                contents=text,
                config={
                    "task_type": task_type,
                    "output_dimensionality": model.vector_size,
                },
            )
            return list(result.embeddings[0].values)

        else:
            logger.error(f"Unsupported embedding model: {model.name}")
            raise ValueError(f"Unsupported embedding model: {model.name}")

    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        # Return a zero vector as fallback
        return [0.0] * model.vector_size
