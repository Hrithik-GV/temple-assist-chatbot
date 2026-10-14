"""Website crawler service using Playwright for JavaScript-rendered temple websites."""

import asyncio
from collections import deque
import time
from typing import Dict, List, Optional, Set
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.core.config import settings
from app.core.errors import BadRequestException
from app.models.knowledge import (
    CrawlPageResult,
    CrawlSummary,
    DocumentSourceType,
)
from app.services.base import BaseService
from app.services.ingestion_service import IngestionService, ingestion_service
from app.utils.helpers import get_utc_now
from app.utils.html_cleaner import clean_html_content
from app.utils.url_utils import extract_domain, is_same_domain, normalize_url


class WebsiteCrawlerService(BaseService):
    """Playwright-based web crawler for extracting knowledge from client-side rendered temple websites."""

    def __init__(self, ingester: Optional[IngestionService] = None) -> None:
        super().__init__()
        self._ingestion_service = ingester or ingestion_service

    async def crawl_temple_website(
        self,
        temple_id: str,
        start_url: str,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        timeout_ms: Optional[int] = None,
        category: Optional[str] = "website",
        force_reingest: bool = False,
    ) -> CrawlSummary:
        """Crawl a temple website starting from `start_url` and ingest all discovered content.

        Features:
        - Renders client-side JavaScript using headless Chromium.
        - Strips navigation, headers, footers, scripts, styles, and cookie notices.
        - Discovers and follows internal links within the same domain.
        - Prevents infinite loops, URL duplicates, and external website leakage.
        - Applies configurable page limits and depth limits.
        - Gracefully handles timeouts and broken pages without halting the crawl.
        - Passes extracted content into the RAG vector ingestion pipeline.

        Args:
            temple_id: Identifier of the temple to associate knowledge with.
            start_url: Starting entry-point URL (e.g. 'https://temple.org/').
            max_pages: Maximum number of pages to crawl (default from settings).
            max_depth: Maximum link hop depth from start_url (default from settings).
            timeout_ms: Page navigation timeout in milliseconds (default from settings).
            category: Classification category for chunks (default: 'website').
            force_reingest: If True, re-indexes pages even if identical content was indexed.

        Returns:
            CrawlSummary: Detailed summary of visited, ingested, and failed pages.
        """
        # 1. Validation
        if not temple_id or not temple_id.strip():
            raise BadRequestException("templeId is required for website crawling.")
        if not start_url or not start_url.strip():
            raise BadRequestException("start_url is required for website crawling.")

        normalized_start_url = normalize_url(start_url)
        base_domain = extract_domain(normalized_start_url)
        if not base_domain:
            raise BadRequestException(f"Invalid starting URL or domain: {start_url}")

        limit_pages = max_pages if (max_pages is not None and max_pages > 0) else settings.CRAWLER_MAX_PAGES
        max_allowed = getattr(settings, "CRAWLER_MAX_ALLOWED_PAGES", 50)
        limit_pages = min(limit_pages, max_allowed)

        limit_depth = max_depth if (max_depth is not None and max_depth >= 0) else settings.CRAWLER_MAX_DEPTH
        nav_timeout = timeout_ms if (timeout_ms is not None and timeout_ms > 0) else settings.CRAWLER_PAGE_TIMEOUT_MS
        wait_ms = settings.CRAWLER_WAIT_AFTER_LOAD_MS
        total_crawl_timeout = getattr(settings, "CRAWLER_TOTAL_TIMEOUT_SECONDS", 300)

        self.logger.info(
            "Starting crawl for temple '%s' | Entry: %s | Domain: %s | MaxPages: %d (capped at %d) | MaxDepth: %d",
            temple_id,
            normalized_start_url,
            base_domain,
            limit_pages,
            max_allowed,
            limit_depth,
        )

        start_time = time.time()
        visited_urls: Set[str] = set()
        enqueued_urls: Set[str] = {normalized_start_url}
        queue: deque = deque([(normalized_start_url, 0)])  # (url, depth)

        page_results: List[CrawlPageResult] = []
        pages_ingested = 0
        pages_skipped = 0
        pages_failed = 0
        total_chunks = 0

        # Concurrency semaphore to throttle parallel browser processes
        if not hasattr(self, "_crawl_semaphore"):
            self._crawl_semaphore = asyncio.Semaphore(getattr(settings, "CRAWLER_MAX_CONCURRENCY", 2))

        async with self._crawl_semaphore:
            # 2. Launch Headless Playwright Browser
            async with async_playwright() as p:
                browser: Browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )

                context: BrowserContext = await browser.new_context(
                    user_agent=settings.CRAWLER_USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                )

                page: Page = await context.new_page()

                # Optimize crawl speed: Block heavy binary media (images, media, fonts) while keeping JS/CSS/XHR
                await page.route(
                    "**/*",
                    lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_(),
                )

                try:
                    while queue and len(visited_urls) < limit_pages:
                        # Check total crawl timeout
                        if (time.time() - start_time) > total_crawl_timeout:
                            self.logger.warning(
                                "Crawl for temple '%s' reached total timeout limit of %ds. Concluding crawl.",
                                temple_id,
                                total_crawl_timeout,
                            )
                            break

                        current_url, current_depth = queue.popleft()
                        if current_url in visited_urls:
                            continue

                        visited_urls.add(current_url)
                        page_index = len(visited_urls)

                        self.logger.info(
                            "[%d/%d] Crawling page: %s (depth: %d)...",
                            page_index,
                            limit_pages,
                            current_url,
                            current_depth,
                        )

                        crawl_res = await self._crawl_and_ingest_page(
                            page=page,
                            current_url=current_url,
                            base_domain=base_domain,
                            temple_id=temple_id,
                            depth=current_depth,
                            category=category,
                            nav_timeout=nav_timeout,
                            wait_ms=wait_ms,
                            force_reingest=force_reingest,
                        )

                        page_results.append(crawl_res)

                        if crawl_res.status == "ingested":
                            pages_ingested += 1
                            total_chunks += crawl_res.chunks_created
                        elif crawl_res.status in ("skipped_duplicate", "empty"):
                            pages_skipped += 1
                        elif crawl_res.status == "failed":
                            pages_failed += 1

                        # Enqueue newly discovered internal links if within depth limit
                        if current_depth < limit_depth and hasattr(crawl_res, "_discovered_links"):
                            for link in crawl_res._discovered_links:
                                if link not in visited_urls and link not in enqueued_urls:
                                    if len(enqueued_urls) < limit_pages * 2:  # Prevent unbounded memory queue
                                        enqueued_urls.add(link)
                                        queue.append((link, current_depth + 1))
                                        self.logger.debug("Enqueued internal link: %s (depth: %d)", link, current_depth + 1)

                finally:
                    await context.close()
                    await browser.close()

        duration = round(time.time() - start_time, 2)
        self.logger.info(
            "Crawl finished for temple '%s' in %.2fs: %d visited, %d ingested, %d skipped, %d failed, %d chunks created.",
            temple_id,
            duration,
            len(visited_urls),
            pages_ingested,
            pages_skipped,
            pages_failed,
            total_chunks,
        )

        return CrawlSummary(
            templeId=temple_id,
            startUrl=normalized_start_url,
            totalPagesVisited=len(visited_urls),
            pagesIngested=pages_ingested,
            pagesSkipped=pages_skipped,
            pagesFailed=pages_failed,
            totalChunksCreated=total_chunks,
            durationSeconds=duration,
            pageResults=page_results,
        )

    async def _crawl_and_ingest_page(
        self,
        page: Page,
        current_url: str,
        base_domain: str,
        temple_id: str,
        depth: int,
        category: Optional[str],
        nav_timeout: int,
        wait_ms: int,
        force_reingest: bool,
    ) -> CrawlPageResult:
        """Fetch, render, clean, and ingest a single web page. Catches all errors gracefully."""
        discovered_links: List[str] = []

        try:
            # 1. Navigate to page with Playwright
            response = await page.goto(
                current_url,
                wait_until="domcontentloaded",
                timeout=nav_timeout,
            )

            if response and response.status >= 400:
                self.logger.warning("HTTP error %d for URL: %s", response.status, current_url)
                res = CrawlPageResult(
                    url=current_url,
                    title="",
                    status="failed",
                    error=f"HTTP status {response.status}",
                )
                res._discovered_links = []
                return res

            # 2. Wait for client-side JavaScript execution / rendering
            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)

            # 3. Get rendered HTML
            rendered_html = await page.content()

            # 4. Extract title, clean visible text, and discover links
            title, cleaned_text, discovered_links = clean_html_content(
                html=rendered_html,
                current_url=current_url,
                base_domain=base_domain,
            )

            # 5. Check if page has sufficient readable content (skip blank or stub pages)
            if not cleaned_text or len(cleaned_text.strip()) < 30:
                self.logger.info("Page '%s' contains insufficient readable text (skipping ingestion).", current_url)
                res = CrawlPageResult(
                    url=current_url,
                    title=title,
                    status="empty",
                    chunks_created=0,
                    error="Page contained no substantial textual content",
                )
                res._discovered_links = discovered_links
                return res

            # 6. Pass through ingestion pipeline
            doc_metadata = {
                "url": current_url,
                "domain": base_domain,
                "depth": depth,
                "crawledAt": get_utc_now().isoformat(),
            }

            ingest_result = await self._ingestion_service.ingest_document(
                temple_id=temple_id,
                source=cleaned_text,
                title=title,
                source_type=DocumentSourceType.WEBSITE,
                filename=current_url,
                source_url=current_url,
                category=category,
                metadata=doc_metadata,
                force_reingest=force_reingest,
            )

            if ingest_result.is_duplicate:
                status = "skipped_duplicate"
            else:
                status = "ingested"

            res = CrawlPageResult(
                url=current_url,
                title=title,
                status=status,
                chunks_created=ingest_result.chunks_created,
                document_id=ingest_result.document_id,
            )
            res._discovered_links = discovered_links
            return res

        except Exception as exc:
            self.logger.error("Failed to crawl page '%s': %s", current_url, str(exc), exc_info=False)
            res = CrawlPageResult(
                url=current_url,
                title="",
                status="failed",
                chunks_created=0,
                error=str(exc),
            )
            res._discovered_links = discovered_links
            return res


# Global singleton instance
crawler_service = WebsiteCrawlerService()
