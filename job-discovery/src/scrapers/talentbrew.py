"""Amgen careers scraper (TalentBrew / Radancy platform).

Amgen uses TalentBrew at careers.amgen.com. The search results page
is server-rendered HTML with job listings.

Actual HTML structure (verified 2026-02-07):
  - Search results at /search-jobs with 1,223 total results
  - Each job is a list item with:
    - Date (e.g., "Aug. 18, 2025")
    - Title as bold text within a link
    - Location (e.g., "US - Minnesota - Minneapolis")
    - Link pattern: /en/job/{city}/{slug}/{company_id}/{job_id}
  - Individual job pages are fully server-rendered with:
    - Title, location, job ID, date posted, category, salary range
    - Full job description text
  - The TalentBrew JSON API at /search-jobs/results returns empty,
    so we parse the HTML directly
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://careers.amgen.com"


class TalentBrewScraper(BaseScraper):
    """Scrapes jobs from Amgen's TalentBrew-based career site.

    Parses the server-rendered HTML search results page. Each page
    shows ~10 job listings with title, location, and link.
    """

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        super().__init__(source_config, pipeline_config)
        self.company_name = source_config.company
        self.site_url = source_config.url or BASE_URL
        self.keywords = source_config.keywords
        self.search_query = " ".join(source_config.keywords) if source_config.keywords else ""
        self.max_pages = source_config.params.get("max_pages", 20)

    def scrape(self) -> list[JobPosting]:
        """Fetch jobs from the server-rendered search results page.

        NOTE: TalentBrew paginates via AJAX (XHR) that requires JavaScript
        execution to return results. Without Playwright, we can only get
        the first page of server-rendered results (~10-12 jobs). The AJAX
        endpoint at /search-jobs/results returns empty HTML without a
        browser context. Full scraping would require Playwright.

        If keywords are configured, they are passed in the URL path
        (e.g. /search-jobs/drug%20product) for server-side filtering.
        """
        if self.search_query:
            logger.info(
                "[%s] Starting TalentBrew scrape for %s (query=%r)",
                self.name, self.company_name, self.search_query,
            )
        else:
            logger.info("[%s] Starting TalentBrew scrape for %s", self.name, self.company_name)

        # TalentBrew accepts keyword searches as a URL path segment
        from urllib.parse import quote
        if self.search_query:
            first_url = f"{self.site_url}/search-jobs/{quote(self.search_query)}"
        else:
            first_url = f"{self.site_url}/search-jobs"
        try:
            resp = self._get(first_url)
        except Exception:
            logger.error("[%s] Failed to fetch search page", self.name)
            return []

        jobs = self._parse_search_page(resp.text)

        if not jobs:
            logger.warning("[%s] No jobs found on search page", self.name)
            return []

        logger.info(
            "[%s] Got %d jobs from server-rendered first page "
            "(full pagination requires Playwright)",
            self.name, len(jobs),
        )
        return jobs

    def _parse_search_page(self, html: str) -> list[JobPosting]:
        """Parse job listings from the TalentBrew search results HTML.

        Amgen's search results have links following this pattern:
        /en/job/{city}/{slug}/{company_id}/{job_id}
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []
        seen_urls: set[str] = set()

        # Find all job links — they match /en/job/
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "/en/job/" not in href:
                continue

            # Normalize URL
            if not href.startswith("http"):
                href = urljoin(self.site_url, href)

            if href in seen_urls:
                continue

            title = link.get_text(strip=True)
            # Skip non-title links (e.g., "Save Job Button")
            if not title or len(title) < 5 or title == "Save Job Button":
                continue

            seen_urls.add(href)

            # Find the parent list item to extract location and date
            parent = link.find_parent("li")
            if not parent:
                parent = link.find_parent(["div", "tr"])

            location = ""
            posted_date = ""

            if parent:
                parent_text = parent.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in parent_text.split("\n") if l.strip()]

                # Remove the title from lines
                lines = [l for l in lines if l != title and l != "Save Job Button"]

                # Date is usually first — looks like "Aug. 18, 2025"
                for line in lines:
                    if re.match(r"[A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4}", line):
                        posted_date = line
                        break

                # Location — lines containing country/state patterns
                for line in lines:
                    if line == posted_date:
                        continue
                    # Amgen uses "US - State - City" or "Country - City" format
                    if re.match(r"(US|United States|Canada|Mexico|India|China|Japan|Germany|Ireland)", line) or \
                       " - " in line:
                        location = line
                        break
                    # Also match "and N other location" patterns
                    if "other location" in line.lower():
                        continue

            jobs.append(JobPosting(
                title=title,
                company=self.company_name,
                url=href,
                source=f"talentbrew:{self.company_name.lower().replace(' ', '')}",
                location=location,
                posted_date=posted_date,
            ))

        return jobs
