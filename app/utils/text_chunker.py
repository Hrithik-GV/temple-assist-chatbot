"""Boundary-aware text chunking with configurable chunk size and overlap."""

from typing import List
from app.core.config import settings
from app.core.errors import BadRequestException


def count_tokens(text: str) -> int:
    """Estimate token count for a text segment.

    Approximates tokens as roughly 1 token per 4 characters or ~0.75 words per token.
    """
    if not text:
        return 0
    words = text.split()
    return max(len(words), len(text) // 4)


def chunk_text(
    text: str,
    chunk_size: int = settings.DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = settings.DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into semantic chunks with configurable size and overlap.

    Splits along natural boundaries (paragraphs, sentences, word breaks)
    to avoid bisecting words or semantic units.

    Args:
        text: Input text string.
        chunk_size: Maximum character length per chunk (default: settings.DEFAULT_CHUNK_SIZE).
        chunk_overlap: Overlapping character count between consecutive chunks (default: settings.DEFAULT_CHUNK_OVERLAP).

    Returns:
        List[str]: List of non-empty text chunks.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    total_len = len(text)

    if chunk_size <= 0:
        raise BadRequestException("chunk_size must be greater than 0.")
    if chunk_overlap < 0:
        raise BadRequestException("chunk_overlap must be non-negative.")
    if chunk_overlap >= chunk_size:
        raise BadRequestException("chunk_overlap must be strictly less than chunk_size.")

    # If entire text fits in a single chunk
    if total_len <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0

    while start < total_len:
        end = min(start + chunk_size, total_len)

        # If not at the end of the text, find the best natural breakpoint
        if end < total_len:
            # Search for boundaries in preferred order: \n\n, \n, .!?, space
            substring = text[start:end]

            best_break = -1
            for separator in ("\n\n", "\n", ". ", "? ", "! ", "; ", " "):
                pos = substring.rfind(separator)
                # Ensure the break does not occur too close to the beginning (at least 30% of chunk_size)
                if pos > int(chunk_size * 0.3):
                    best_break = pos + len(separator.rstrip())
                    break

            if best_break != -1:
                end = start + best_break

        chunk_str = text[start:end].strip()
        if chunk_str:
            chunks.append(chunk_str)

        # Move forward, respecting overlap
        step = max(end - start - chunk_overlap, 1)
        start += step

        # Prevent infinite loop or trailing tiny overlap chunk if remaining text is empty
        if start >= total_len:
            break

    return chunks
