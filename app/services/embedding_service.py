"""Embedding service and provider abstractions for generating dense vector representations."""

from abc import ABC, abstractmethod
import hashlib
import math
from typing import List, Optional
from app.core.config import settings
from app.core.errors import BadRequestException
from app.models.knowledge import KnowledgeChunk
from app.services.base import BaseService


class BaseEmbeddingProvider(ABC):
    """Abstract interface for text embedding models to allow swappable providers."""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate a dense vector embedding for a single text string."""
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate dense vector embeddings for a batch of text strings."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector dimensionality produced by this model."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        pass


class FastEmbedProvider(BaseEmbeddingProvider):
    """Local, open-source embedding provider using FastEmbed (ONNX runtime, CPU-optimized)."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self._dimension = settings.EMBEDDING_DIMENSION
        self._model = None

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_model(self):
        """Lazy-load the FastEmbed model on first use."""
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text string."""
        if not text or not text.strip():
            raise BadRequestException(message="Text cannot be empty for embedding generation.")
        model = self._get_model()
        embeddings = list(model.embed([text]))
        return [float(x) for x in embeddings[0]]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of text strings in batch."""
        if not texts:
            return []
        cleaned = [t.strip() for t in texts]
        if any(not t for t in cleaned):
            raise BadRequestException(message="Cannot embed empty text items in batch.")
        model = self._get_model()
        embeddings = list(model.embed(cleaned))
        return [[float(x) for x in emb] for emb in embeddings]


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic mock provider for unit tests and offline operation."""

    def __init__(self, dimension: int = 384, model_name: str = "mock-embedding-384") -> None:
        self._dimension = dimension
        self._model_name = model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def _generate_vector(self, text: str) -> List[float]:
        # Hash text to generate a deterministic unit vector
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw_vals = [(h[i % len(h)] / 255.0) - 0.5 for i in range(self._dimension)]
        norm = math.sqrt(sum(x * x for x in raw_vals)) or 1.0
        return [x / norm for x in raw_vals]

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise BadRequestException(message="Text cannot be empty for embedding generation.")
        return self._generate_vector(text)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return [self.embed_text(t) for t in texts]


class EmbeddingService(BaseService):
    """Service managing text embedding generation with support for swappable providers."""

    def __init__(self, provider: Optional[BaseEmbeddingProvider] = None) -> None:
        super().__init__()
        self._provider = provider or FastEmbedProvider()

    @property
    def provider(self) -> BaseEmbeddingProvider:
        """Get the active embedding provider."""
        return self._provider

    def set_provider(self, provider: BaseEmbeddingProvider) -> None:
        """Switch embedding provider at runtime (e.g. for testing or model upgrades)."""
        self.logger.info("Switching embedding provider to '%s'", provider.model_name)
        self._provider = provider

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for a given text query or chunk.

        Args:
            text: Input string.

        Returns:
            List[float]: Normalized embedding vector.
        """
        if not text or not text.strip():
            raise BadRequestException("Query text cannot be empty.")
        return self._provider.embed_text(text)

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for multiple texts.

        Args:
            texts: List of input strings.

        Returns:
            List[List[float]]: List of normalized embedding vectors.
        """
        if not texts:
            return []
        return self._provider.embed_texts(texts)

    def embed_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        """Generate and assign embedding vector for a KnowledgeChunk.

        Args:
            chunk: KnowledgeChunk instance.

        Returns:
            KnowledgeChunk: The updated chunk with populated embedding.
        """
        chunk.embedding = self.generate_embedding(chunk.content)
        return chunk

    def embed_chunks(self, chunks: List[KnowledgeChunk]) -> List[KnowledgeChunk]:
        """Batch generate and assign embeddings for a list of KnowledgeChunks.

        Args:
            chunks: List of KnowledgeChunk instances.

        Returns:
            List[KnowledgeChunk]: Updated chunks with populated embeddings.
        """
        if not chunks:
            return []
        texts = [c.content for c in chunks]
        embeddings = self.generate_embeddings(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb
        return chunks

    def get_dimension(self) -> int:
        """Return the vector dimension of the active provider."""
        return self._provider.dimension


# Global singleton instance
embedding_service = EmbeddingService()
