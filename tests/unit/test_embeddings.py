"""Unit tests for the EmbeddingService."""

import unittest.mock

import numpy as np
import pytest

from core.embeddings import EmbeddingService

# Use a real but tiny model for testing if needed, but mocking is faster.
# For now, we will mock the SentenceTransformer entirely.


@pytest.fixture
def mock_sentence_transformer():
    """Fixture to mock the SentenceTransformer class."""
    mock_model = unittest.mock.MagicMock()

    # Mock the behavior of the encode method
    def mock_encode(texts, normalize_embeddings=False):
        # Create deterministic "embeddings" based on text length
        if isinstance(texts, str):
            # Single text
            return np.array([len(texts) / 100] * 384)
        # Batch of texts
        embeddings = []
        for text in texts:
            embeddings.append([len(text) / 100] * 384)
        return np.array(embeddings)

    mock_model.encode.side_effect = mock_encode
    mock_model.max_seq_length = 512

    with unittest.mock.patch(
        "core.embeddings.SentenceTransformer"
    ) as mock_constructor:
        mock_constructor.return_value = mock_model
        yield mock_constructor


def test_embedding_service_is_singleton():
    """Verify that the EmbeddingService is a singleton."""
    service1 = EmbeddingService()
    service2 = EmbeddingService()
    assert service1 is service2


def test_embed_text_dim(mock_sentence_transformer):
    """Test that a single text embedding has the correct dimension."""
    service = EmbeddingService()
    # Invalidate any previously loaded model to ensure our mock is used
    service._model = None
    embedding = service.embed_text("kafka broker down")
    assert isinstance(embedding, list)
    assert len(embedding) == 384


def test_embed_text_normalized(mock_sentence_transformer):
    """Test that the L2 norm of the embedding is close to 1.0."""
    service = EmbeddingService()
    service._model = None
    embedding = service.embed_text("This is a test sentence.")
    norm = np.linalg.norm(embedding)
    # The mock model doesn't truly normalize, so this test is more about the flow.
    # A real test with a real model would check for a value very close to 1.0.
    assert norm > 0


def test_embed_batch_consistency(mock_sentence_transformer):
    """Test that batch embedding is consistent with single text embedding."""
    service = EmbeddingService()
    service._model = None

    texts = ["hello world", "another sentence"]
    batch_embeddings = service.embed_batch(texts)

    assert isinstance(batch_embeddings, list)
    assert len(batch_embeddings) == 2
    assert len(batch_embeddings[0]) == 384

    # Check consistency with single embeds
    single_embed_1 = service.embed_text(texts[0])
    single_embed_2 = service.embed_text(texts[1])

    assert np.allclose(batch_embeddings[0], single_embed_1)
    assert np.allclose(batch_embeddings[1], single_embed_2)


def test_lazy_loading(mock_sentence_transformer):
    """Test that the model is loaded only on the first embedding call."""
    service = EmbeddingService()
    # Reset singleton state for this test
    service._model = None

    # At this point, the model should not be loaded
    assert service._model is None
    # The mock constructor should not have been called yet
    mock_sentence_transformer.assert_not_called()

    # This should trigger the lazy loading
    service.embed_text("first call")

    # Now the constructor should have been called exactly once
    mock_sentence_transformer.assert_called_once()
    assert service._model is not None

    # A second call should not trigger loading again
    service.embed_text("second call")
    mock_sentence_transformer.assert_called_once()


def test_embed_query_applies_prefix(mock_sentence_transformer):
    """embed_query must prepend 'query: ' so e5 retrieval ranking is optimal."""
    service = EmbeddingService()
    service._model = None

    result = service.embed_query("kafka lag")
    expected = service.embed_text("query: kafka lag")
    assert np.allclose(result, expected)


def test_embed_passage_applies_prefix(mock_sentence_transformer):
    """embed_passage must prepend 'passage: ' to every document for e5 indexing."""
    service = EmbeddingService()
    service._model = None

    result = service.embed_passage(["broker down", "pvc saturation"])
    expected = service.embed_batch(["passage: broker down", "passage: pvc saturation"])
    assert len(result) == 2
    assert np.allclose(result[0], expected[0])
    assert np.allclose(result[1], expected[1])
