"""Tests for URL filtering, HTML cleaning, and Playwright crawler logic."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models.knowledge import CrawlSummary, DocumentSourceType, IngestionResult, DocumentStatus
from app.services.crawler_service import WebsiteCrawlerService
from app.utils.html_cleaner import clean_html_content, extract_page_title, extract_internal_links
from app.utils.url_utils import (
    extract_domain,
    is_crawlable_url,
    is_same_domain,
    normalize_url,
    resolve_link,
)


# ==============================================================================
# URL Utility Tests
# ==============================================================================


class TestUrlUtils:
    """Test suite for URL normalization and domain validation."""

    def test_normalize_url_strips_fragments(self) -> None:
        """URL fragments (#anchor) must be stripped to prevent duplicate crawls."""
        url = "https://temple.org/darshan-timings#morning-aarti"
        assert normalize_url(url) == "https://temple.org/darshan-timings"

    def test_normalize_url_strips_tracking_params(self) -> None:
        """Marketing and tracking query parameters (utm_*, ref, etc.) must be removed."""
        url = "https://temple.org/events?utm_source=facebook&utm_medium=cpc&id=101&ref=social"
        normalized = normalize_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert "ref" not in normalized
        assert "id=101" in normalized

    def test_normalize_url_normalizes_trailing_slash_and_case(self) -> None:
        """Trailing slashes on paths must be stripped, scheme/domain lowercased."""
        url = "HTTPS://WWW.TEMPLE.ORG/About-Us/"
        assert normalize_url(url) == "https://www.temple.org/About-Us"

    def test_normalize_url_preserves_root_slash(self) -> None:
        """Root domain URL must keep single slash."""
        url = "https://temple.org/"
        assert normalize_url(url) == "https://temple.org/"

    def test_extract_domain(self) -> None:
        """Extract clean hostname from full URL."""
        assert extract_domain("https://www.somnath.org/history") == "www.somnath.org"
        assert extract_domain("http://tirupati.org:8080/darshan") == "tirupati.org"

    def test_is_same_domain_matches_core_domain(self) -> None:
        """Same domain matches with and without www prefix."""
        base = "https://somnath.org"
        assert is_same_domain(base, "https://somnath.org/about") is True
        assert is_same_domain(base, "https://www.somnath.org/rituals") is True
        assert is_same_domain("www.somnath.org", "https://somnath.org/contact") is True

    def test_is_same_domain_rejects_external_websites(self) -> None:
        """External links and third-party social links must be rejected."""
        base = "https://somnath.org"
        assert is_same_domain(base, "https://facebook.com/somnath") is False
        assert is_same_domain(base, "https://google.com/search") is False
        assert is_same_domain(base, "https://othertemple.org/darshan") is False

    def test_is_crawlable_url_validates_html_pages(self) -> None:
        """HTML pages on the domain are crawlable."""
        base_domain = "somnath.org"
        assert is_crawlable_url("https://somnath.org/history", base_domain) is True
        assert is_crawlable_url("https://www.somnath.org/puja-timings", base_domain) is True

    def test_is_crawlable_url_rejects_static_media_and_binaries(self) -> None:
        """Images, documents, stylesheets, and binary assets must be skipped."""
        base_domain = "somnath.org"
        assert is_crawlable_url("https://somnath.org/banner.jpg", base_domain) is False
        assert is_crawlable_url("https://somnath.org/logo.png", base_domain) is False
        assert is_crawlable_url("https://somnath.org/brochure.pdf", base_domain) is False
        assert is_crawlable_url("https://somnath.org/video.mp4", base_domain) is False
        assert is_crawlable_url("https://somnath.org/styles.css", base_domain) is False
        assert is_crawlable_url("https://somnath.org/app.js", base_domain) is False

    def test_resolve_link(self) -> None:
        """Resolve relative and absolute links correctly."""
        base = "https://somnath.org/pages/home"
        assert resolve_link(base, "/about") == "https://somnath.org/about"
        assert resolve_link(base, "rituals") == "https://somnath.org/pages/rituals"
        assert resolve_link(base, "https://somnath.org/timings") == "https://somnath.org/timings"
        assert resolve_link(base, "#top") is None
        assert resolve_link(base, "javascript:void(0)") is None
        assert resolve_link(base, "mailto:info@somnath.org") is None


# ==============================================================================
# HTML Cleaning & Extraction Tests
# ==============================================================================


class TestHtmlCleaner:
    """Test suite for DOM parsing, noise stripping, and text extraction."""

    SAMPLE_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Somnath Temple | Official Sacred Shrine</title>
        <style>body { font-family: sans-serif; }</style>
        <script>console.log("analytics tracking");</script>
    </head>
    <body>
        <div class="cookie-banner" id="cookie-consent">
            <p>We use cookies to improve your user experience. <button>Accept All</button></p>
        </div>

        <header>
            <nav class="navbar">
                <a href="/home">Home</a>
                <a href="/about">About</a>
                <a href="/darshan">Darshan</a>
                <a href="https://twitter.com/temple">Twitter</a>
            </nav>
        </header>

        <main id="main-content">
            <h1>Sacred Somnath Temple</h1>
            <p>The Somnath temple is the first among the twelve Aadi Jyotirlings of India.</p>
            <p>Daily Morning Aarti commences at 7:00 AM sharp.</p>
            <a href="/rituals">View Daily Rituals</a>
            <a href="/gallery.png">View Image</a>
            <a href="https://external.com/news">External News</a>
        </main>

        <footer>
            <p>© 2026 Somnath Temple Trust. All rights reserved.</p>
            <div class="social-links">
                <a href="https://youtube.com/temple">YouTube</a>
            </div>
        </footer>
    </body>
    </html>
    """

    def test_extract_page_title(self) -> None:
        """Title tag is parsed cleanly without boilerplate suffixes."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self.SAMPLE_HTML, "html.parser")
        title = extract_page_title(soup, "https://somnath.org")
        assert title == "Somnath Temple"

    def test_clean_html_content_strips_noise(self) -> None:
        """Navigation, headers, footers, cookie banners, scripts, and styles are stripped."""
        title, text, links = clean_html_content(
            html=self.SAMPLE_HTML,
            current_url="https://somnath.org/home",
            base_domain="somnath.org",
        )

        assert title == "Somnath Temple"
        # Core textual content must be preserved
        assert "Sacred Somnath Temple" in text
        assert "twelve Aadi Jyotirlings" in text
        assert "Daily Morning Aarti commences at 7:00 AM" in text

        # Boilerplate noise must NOT be present in extracted text
        assert "We use cookies" not in text
        assert "Accept All" not in text
        assert "All rights reserved" not in text
        assert "analytics tracking" not in text

    def test_clean_html_extracts_only_internal_crawlable_links(self) -> None:
        """Extracts internal HTML links while discarding external, social, and image links."""
        _, _, links = clean_html_content(
            html=self.SAMPLE_HTML,
            current_url="https://somnath.org/home",
            base_domain="somnath.org",
        )

        # Internal links discovered
        assert "https://somnath.org/home" in links
        assert "https://somnath.org/about" in links
        assert "https://somnath.org/darshan" in links
        assert "https://somnath.org/rituals" in links

        # External, image, or social links must be excluded
        assert "https://twitter.com/temple" not in links
        assert "https://external.com/news" not in links
        assert "https://youtube.com/temple" not in links
        assert not any(link.endswith(".png") for link in links)


# ==============================================================================
# WebsiteCrawlerService Tests
# ==============================================================================


class TestWebsiteCrawlerService:
    """Test suite for WebsiteCrawlerService orchestration and error resilience."""

    @pytest.mark.anyio
    async def test_crawler_input_validation(self) -> None:
        """Crawler requires valid temple_id and start_url."""
        crawler = WebsiteCrawlerService()

        with pytest.raises(Exception) as exc_info:
            await crawler.crawl_temple_website(temple_id="", start_url="https://temple.org")
        assert "templeId is required" in str(exc_info.value)

        with pytest.raises(Exception) as exc_info:
            await crawler.crawl_temple_website(temple_id="temple_1", start_url="")
        assert "start_url is required" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_crawler_crawls_and_ingests_rendered_pages(self) -> None:
        """Crawler loads pages with Playwright, extracts content, and calls IngestionService."""
        mock_ingester = MagicMock()
        mock_ingester.ingest_document = AsyncMock(
            return_value=IngestionResult(
                document_id="doc_test_123",
                temple_id="temple_somnath",
                title="Somnath Darshan",
                status=DocumentStatus.PROCESSED,
                chunks_created=3,
                is_duplicate=False,
                message="Ingestion successful",
            )
        )

        crawler = WebsiteCrawlerService(ingester=mock_ingester)

        sample_page_html = """
        <html>
            <head><title>Somnath Darshan Info</title></head>
            <body>
                <main>
                    <h1>Darshan Timings</h1>
                    <p>Morning Darshan opens at 6:00 AM and closes at 11:30 AM.</p>
                </main>
            </body>
        </html>
        """

        # Mock Playwright browser interactions
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
        mock_page.content = AsyncMock(return_value=sample_page_html)
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.route = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("app.services.crawler_service.async_playwright") as mock_async_pw:
            mock_async_pw.return_value.__aenter__.return_value = mock_pw

            summary: CrawlSummary = await crawler.crawl_temple_website(
                temple_id="temple_somnath",
                start_url="https://somnath.org",
                max_pages=1,
                max_depth=1,
            )

            assert summary.temple_id == "temple_somnath"
            assert summary.total_pages_visited == 1
            assert summary.pages_ingested == 1
            assert summary.total_chunks_created == 3

            # Verify IngestionService was called with correct parameters
            mock_ingester.ingest_document.assert_called_once()
            call_kwargs = mock_ingester.ingest_document.call_args.kwargs
            assert call_kwargs["temple_id"] == "temple_somnath"
            assert "Somnath Darshan Info" in call_kwargs["title"]
            assert call_kwargs["source_type"] == DocumentSourceType.WEBSITE
            assert "Morning Darshan opens at 6:00 AM" in call_kwargs["source"]

    @pytest.mark.anyio
    async def test_crawler_handles_broken_pages_gracefully(self) -> None:
        """Crawl does not crash when an HTTP error or timeout occurs on a page."""
        mock_ingester = MagicMock()
        mock_ingester.ingest_document = AsyncMock()

        crawler = WebsiteCrawlerService(ingester=mock_ingester)

        mock_page = AsyncMock()
        # Simulate HTTP 404 response
        mock_page.goto = AsyncMock(return_value=MagicMock(status=404))
        mock_page.route = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("app.services.crawler_service.async_playwright") as mock_async_pw:
            mock_async_pw.return_value.__aenter__.return_value = mock_pw

            summary = await crawler.crawl_temple_website(
                temple_id="temple_somnath",
                start_url="https://somnath.org/nonexistent",
                max_pages=1,
            )

            assert summary.total_pages_visited == 1
            assert summary.pages_failed == 1
            assert summary.pages_ingested == 0
            # Pipeline ingestion should NOT have been invoked
            mock_ingester.ingest_document.assert_not_called()
