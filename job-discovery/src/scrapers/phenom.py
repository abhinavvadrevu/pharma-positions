"""Phenom People career site scraper.

Phenom People powers career sites for Genentech and Merck. These are
JavaScript SPAs that load job data via internal API calls.

Investigation results (2026-02-07):
  - Merck: jobs.merck.com — pure JS SPA, uses Phenom People platform (site ID: MERCUS)
  - Genentech: careers.gene.com — pure JS SPA, uses Phenom People platform (site ID: GENEUS)
  - Both sites return template placeholders ("Lorem Ipsum", "${pageStateData...}")
    when fetched without JavaScript execution
  - The Phenom content delivery API requires authentication tokens generated
    client-side, so direct API calls don't work
  - These sites REQUIRE Playwright for scraping

Current status: Returns empty results. Needs Playwright integration.
"""

from __future__ import annotations

import logging

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class PhenomScraper(BaseScraper):
    """Placeholder scraper for Phenom People-based career sites.

    Phenom People sites are JavaScript SPAs that require browser rendering.
    This scraper currently returns empty results and logs a warning.
    Full implementation requires Playwright.
    """

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        super().__init__(source_config, pipeline_config)
        self.company_name = source_config.company
        self.site_url = source_config.url.rstrip("/")

    def scrape(self) -> list[JobPosting]:
        """Attempt to fetch jobs from Phenom People site.

        Currently returns empty — Phenom People sites are JS SPAs that
        require Playwright for rendering. The site returns template
        placeholders without JavaScript execution.
        """
        logger.warning(
            "[%s] Phenom People sites (%s) require Playwright for scraping. "
            "The site is a JavaScript SPA — no job data is available in the "
            "raw HTML. Returning empty results.",
            self.name,
            self.site_url,
        )
        return []
