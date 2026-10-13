"""HTML content cleaning and extraction utilities for website crawling."""

import re
from typing import List, Optional, Set, Tuple
from bs4 import BeautifulSoup, Comment, Tag

from app.utils.text_cleaner import clean_text
from app.utils.url_utils import is_crawlable_url, resolve_link

# Unnecessary HTML tags to remove entirely
UNWANTED_TAGS: Set[str] = {
    "script", "style", "noscript", "svg", "canvas", "iframe",
    "audio", "video", "source", "track", "form", "input",
    "button", "select", "option", "textarea", "nav", "header",
    "footer", "aside", "dialog", "template", "embed", "object",
}

# Patterns indicating cookie notices, consent popups, ads, or header/footer overlays
UNWANTED_SELECTORS: List[str] = [
    # Cookie / GDPR / Consent notices
    "[id*='cookie' i]", "[class*='cookie' i]",
    "[id*='consent' i]", "[class*='consent' i]",
    "[id*='gdpr' i]", "[class*='gdpr' i]",
    "[id*='notice' i]", "[class*='notice' i]",
    # Banner / modal overlays
    "[id*='banner' i]", "[class*='banner' i]",
    "[id*='modal' i]", "[class*='modal' i]",
    "[id*='popup' i]", "[class*='popup' i]",
    # Navigation / menus / social widgets
    "[role='navigation']", "[role='banner']", "[role='contentinfo']",
    "[role='dialog']", "[role='alertdialog']",
    "[class*='navbar' i]", "[id*='navbar' i]",
    "[class*='nav-menu' i]", "[id*='nav-menu' i]",
    "[class*='social' i]", "[id*='social' i]",
    "[class*='subscribe' i]", "[id*='subscribe' i]",
    "[class*='newsletter' i]", "[id*='newsletter' i]",
]


def extract_page_title(soup: BeautifulSoup, default_url: str = "") -> str:
    """Extract page title from HTML using title tag, meta tags, or first h1.

    Args:
        soup: Parsed BeautifulSoup object.
        default_url: Fallback if no title is found.

    Returns:
        str: Best extracted page title.
    """
    # 1. Try <title> tag
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        if title:
            # Strip common site suffixes like " | Official Temple Website"
            clean_title = re.split(r"\s+[|\-–—:]\s+", title)[0].strip()
            if clean_title:
                return clean_title
            return title

    # 2. Try OpenGraph / Twitter meta title
    meta_og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
    if meta_og and meta_og.get("content"):
        content = meta_og["content"].strip()
        if content:
            return content

    # 3. Try primary <h1> heading
    h1 = soup.find("h1")
    if h1:
        h1_text = h1.get_text(strip=True)
        if h1_text:
            return h1_text

    # 4. Fallback to URL path or default
    if default_url:
        path = default_url.rstrip("/").split("/")[-1]
        if path:
            return path.replace("-", " ").replace("_", " ").title()

    return "Temple Web Page"


def extract_internal_links(soup: BeautifulSoup, current_url: str, base_domain: str) -> List[str]:
    """Discover all valid, crawlable internal links within the same domain.

    Args:
        soup: BeautifulSoup parsed document.
        current_url: URL of the current page.
        base_domain: Domain to restrict crawling to.

    Returns:
        List[str]: Unique canonical URLs belonging to the same domain.
    """
    discovered_urls: List[str] = []
    seen: Set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        resolved = resolve_link(current_url, href)
        if resolved and resolved not in seen:
            if is_crawlable_url(resolved, base_domain):
                seen.add(resolved)
                discovered_urls.append(resolved)

    return discovered_urls


def clean_html_content(html: str, current_url: str, base_domain: str) -> Tuple[str, str, List[str]]:
    """Clean rendered HTML, remove boilerplate/noise, extract text and internal links.

    Process:
    1. Parse HTML with BeautifulSoup.
    2. Extract page title and discover internal links (before removing nav/footer).
    3. Remove HTML comments and unwanted tags (scripts, styles, nav, footer, etc.).
    4. Remove cookie banners, GDPR modals, and popup overlays.
    5. Prioritize main content containers (<main>, <article>, #content) if present.
    6. Extract visible text with natural line breaks.
    7. Pass through text cleaning normalization pipeline.

    Args:
        html: Rendered HTML from Playwright.
        current_url: Current URL being parsed.
        base_domain: Base domain for link crawling restriction.

    Returns:
        Tuple[str, str, List[str]]: (title, cleaned_text, internal_links)
    """
    if not html or not html.strip():
        return ("Empty Page", "", [])

    soup = BeautifulSoup(html, "html.parser")

    # 1. Extract title and internal links before stripping navigation/header/footer
    title = extract_page_title(soup, default_url=current_url)
    internal_links = extract_internal_links(soup, current_url=current_url, base_domain=base_domain)

    # 2. Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 3. Remove unwanted HTML tags
    for tag_name in UNWANTED_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 4. Remove cookie banners, GDPR consent notices, popups, and nav widgets by selector
    for selector in UNWANTED_SELECTORS:
        try:
            for element in soup.select(selector):
                element.decompose()
        except Exception:
            continue

    # 5. Extract text from primary content container if clearly defined, else full body
    content_root = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"^(main|content|page-content|article)$", re.I))
        or soup.find(class_=re.compile(r"^(main|content|page-content|article)$", re.I))
        or soup.body
        or soup
    )

    # Convert block elements to have explicit line breaks so text doesn't merge
    raw_extracted_text = content_root.get_text(separator="\n", strip=True)

    # 6. Normalize and clean extracted text using standard text cleaner
    cleaned_content = clean_text(raw_extracted_text)

    return title, cleaned_content, internal_links
