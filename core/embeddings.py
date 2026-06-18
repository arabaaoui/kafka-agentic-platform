"""Singleton service for generating text embeddings using sentence-transformers.

This module ensures that the embedding model is loaded only once and shared
across the application to conserve memory and reduce startup time. The model
is loaded lazily on the first call to any embedding function.
"""

from __future__ import annotations

import logging
import os
import time
from typing import ClassVar, cast

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """A singleton service to manage a SentenceTransformer model."""

    _instance: ClassVar[EmbeddingService | None] = None
    _model: SentenceTransformer | None = None

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_model(self) -> SentenceTransformer:
        """Lazily loads the SentenceTransformer model."""
        if self._model is None:
            model_name = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-small")
            # If a local path is provided, use it; otherwise, sentence-transformers
            # will download from Hugging Face Hub.
            model_path = os.getenv("EMBEDDING_MODEL_PATH", model_name)

            logger.info("Lazily loading embedding model '%s'...", model_path)
            start_time = time.monotonic()
            try:
                self._model = SentenceTransformer(model_path)
                load_time = time.monotonic() - start_time
                logger.info(
                    "Embedding model loaded in %.2fs. Max sequence length: %s",
                    load_time,
                    self._model.max_seq_length,
                )
            except Exception:
                logger.exception(
                    "Failed to load embedding model '%s'. "
                    "Ensure the model is available at the specified path or can be downloaded.",
                    model_path,
                )
                raise
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """
        Generates an embedding for a single string of text.

        Args:
            text: The input text.

        Returns:
            A list of floats representing the embedding.
        """
        model = self._get_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return cast(list[float], embedding.tolist())

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generates embeddings for a batch of texts.

        Args:
            texts: A list of strings.

        Returns:
            A list of embeddings.
        """
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return cast(list[list[float]], embeddings.tolist())

    def embed_query(self, text: str) -> list[float]:
        # e5 models require "query: " prefix for search queries
        return self.embed_text(f"query: {text}")

    def embed_passage(self, texts: list[str]) -> list[list[float]]:
        # e5 models require "passage: " prefix for indexed documents
        return self.embed_batch([f"passage: {t}" for t in texts])


# Global instance of the service
embedding_service = EmbeddingService()
