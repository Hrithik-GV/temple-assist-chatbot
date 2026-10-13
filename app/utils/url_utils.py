"""URL normalization, domain validation, and link filtering utilities for web crawling."""

from typing import Optional, Set
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# File extensions to ignore during web crawl
EXCLUDED_EXTENSIONS: Set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tif", ".tiff",
    # Documents / Binaries
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".zip", ".tar", ".gz", ".rar", ".7z",
    # Audio / Video
    ".mp3", ".wav", ".ogg", ".mp4", ".avi", ".mov", ".mkv", ".webm",
    # Web assets / code
    ".css", ".js", ".json", ".xml", ".rss", ".woff", ".woff2", ".ttf", ".eot",
}

# Tracking query parameters to remove to avoid crawling duplicate pages
TRACKING_QUERY_PARAMS: Set[str] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "ref", "source",
}


def normalize_url(url: str) -> str:
    """Normalize a URL to canonical form.

    - Strips whitespace
    - Lowercases scheme and netloc/hostname
    - Removes URL fragments (#anchor)
    - Strips tracking query parameters (utm_*, etc.)
    - Normalizes trailing slashes for standard paths

    Args:
        url: Raw URL string.

    Returns:
        str: Canonical normalized URL.
    """
    if not url or not url.strip():
        return ""

    url = url.strip()
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Drop default ports if present
    if (scheme == "http" and netloc.endswith(":80")) or (scheme == "https" and netloc.endswith(":443")):
        netloc = netloc.rsplit(":", 1)[0]

    # Normalize path
    path = parts.path or "/"
    # Clean multiple consecutive slashes in path
    while "//" in path:
        path = path.replace("//", "/")

    # Normalize trailing slash: retain trailing slash only on root "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Filter out tracking query params
    filtered_query = ""
    if parts.query:
        query_pairs = parse_qsl(parts.query, keep_blank_values=False)
        clean_pairs = [
            (k, v) for k, v in query_pairs
            if k.lower() not in TRACKING_QUERY_PARAMS
        ]
        clean_pairs.sort()
        if clean_pairs:
            filtered_query = urlencode(clean_pairs)

    # Reassemble without fragment
    return urlunsplit((scheme, netloc, path, filtered_query, ""))


def extract_domain(url: str) -> str:
    """Extract lowercase hostname/domain from a URL."""
    try:
        parts = urlsplit(url.strip())
        netloc = parts.netloc.lower()
        if ":" in netloc:
            netloc = netloc.split(":", 1)[0]
        return netloc
    except Exception:
        return ""


def is_same_domain(base_url_or_domain: str, target_url: str) -> bool:
    """Check if target_url belongs to the same domain as base_url_or_domain.

    Supports exact domain match and matching with or without 'www.' prefix.
    """
    base_domain = extract_domain(base_url_or_domain) if "://" in base_url_or_domain else base_url_or_domain.lower()
    target_domain = extract_domain(target_url)

    if not base_domain or not target_domain:
        return False

    # Normalize www. prefix for comparison
    base_core = base_domain[4:] if base_domain.startswith("www.") else base_domain
    target_core = target_domain[4:] if target_domain.startswith("www.") else target_domain

    return base_core == target_core


def is_crawlable_url(url: str, base_domain: str) -> bool:
    """Validate whether a URL is a valid, in-domain HTML page suitable for crawling.

    Args:
        url: URL to test.
        base_domain: Allowed domain or root URL.

    Returns:
        bool: True if URL is crawlable, False otherwise.
    """
    if not url or not url.strip():
        return False

    norm_url = normalize_url(url)
    if not norm_url:
        return False

    parts = urlsplit(norm_url)

    # Must be http or https
    if parts.scheme not in ("http", "https"):
        return False

    # Must have a netloc
    if not parts.netloc:
        return False

    # Must match domain
    if not is_same_domain(base_domain, norm_url):
        return False

    # Check for excluded file extensions in path
    path_lower = parts.path.lower()
    for ext in EXCLUDED_EXTENSIONS:
        if path_lower.endswith(ext):
            return False

    return True


def resolve_link(base_url: str, link_href: str) -> Optional[str]:
    """Resolve a relative or absolute link against a base URL and normalize it.

    Args:
        base_url: Current page URL.
        link_href: 'href' attribute from anchor tag.

    Returns:
        Optional[str]: Resolved normalized URL or None if invalid.
    """
    if not link_href:
        return None

    href = link_href.strip()

    # Skip anchors, javascript, mailto, tel
    if href.startswith(("#", "javascript:", "mailto:", "tel:", "data:", "sms:")):
        return None

    try:
        absolute_url = urljoin(base_url, href)
        normalized = normalize_url(absolute_url)
        return normalized if normalized else None
    except Exception:
        return None
