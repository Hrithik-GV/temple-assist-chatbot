"""Text cleaning and normalization utilities for document ingestion."""

import re
import unicodedata


def clean_text(raw_text: str) -> str:
    """Clean raw extracted text by removing formatting noise, control chars, and excessive whitespace.

    Args:
        raw_text: Raw string extracted from document.

    Returns:
        str: Cleaned, normalized string ready for chunking.
    """
    if not raw_text:
        return ""

    # 1. Unicode normalization (NFKC decomposes compatibility chars and recomposes canonically)
    text = unicodedata.normalize("NFKC", raw_text)

    # 2. Normalize Windows/Mac line endings to standard Unix newline
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Replace non-breaking spaces and exotic space characters with standard space
    text = re.sub(r"[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]", " ", text)

    # 4. Remove unprintable control characters, but preserve tabs and newlines
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or unicodedata.category(ch)[0] != "C")

    # 5. Normalize horizontal whitespace per line (multiple tabs/spaces -> single space)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(cleaned_line)

    text = "\n".join(cleaned_lines)

    # 6. Collapse excessive consecutive blank lines (max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 7. Strip outer whitespace
    return text.strip()
