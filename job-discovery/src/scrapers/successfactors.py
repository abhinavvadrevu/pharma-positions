"""SAP SuccessFactors career site scraper.

SuccessFactors powers career sites for Novo Nordisk and Astellas.

Investigation results (2026-02-07):
  - Novo Nordisk: careers.novonordisk.com → SuccessFactors NES platform
    - Internal site: career2.successfactors.eu
    - The search page loads jQuery + search.js, but results are rendered by JS
    - No accessible JSON API found — AJAX calls require browser context
  - Astellas: careers.astellas.com → SuccessFactors NES platform
    - Internal site: career8.successfactors.com (company: astellasT5)
    - Same architecture as Novo Nordisk — JS-rendered search results
    - NOT Workday despite some references (confirmed SuccessFactors)

Both sites use the SuccessFactors "New External Sites" (NES) framework
which renders the job search via JavaScript after page load. Direct HTTP
requests return the HTML shell but no job data.

Current status: Returns empty results. Needs Playwright integration.
"""

from __future__ import annotations

import logging

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SuccessFactorsScraper(BaseScraper):
    """Placeholder scraper for SAP SuccessFactors career portals.

    SuccessFactors NES sites are JavaScript-rendered and require
    browser automation. This scraper currently returns empty results.
    Full implementation requires Playwright.
    """

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        super().__init__(source_config, pipeline_config)
        self.company_name = source_config.company
        self.site_url = source_config.url.rstrip("/")

    def scrape(self) -> list[JobPosting]:
        """Attempt to fetch jobs from SuccessFactors site.

        Currently returns empty — SuccessFactors NES sites require
        Playwright for rendering. The job search results are loaded
        via JavaScript after the initial page load.
        """
        logger.warning(
            "[%s] SuccessFactors sites (%s) require Playwright for scraping. "
            "The job search is JavaScript-rendered — no job data is available "
            "in the raw HTML. Returning empty results.",
            self.name,
            self.site_url,
        )
        return []
