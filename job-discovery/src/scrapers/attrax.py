"""AbbVie careers scraper (Attrax platform).

AbbVie uses the Attrax ATS at careers.abbvie.com. The site is
server-rendered with very well-structured HTML.

Actual HTML structure (verified 2026-02-07):
  - Each job listing contains:
    - Title as a link: <a href="https://careers.abbvie.com/en/job/{slug}">Title</a>
    - "Salary" field with range (e.g., "$82,500 - $157,500")
    - "Location" field (e.g., "North Chicago, IL")
    - "Function" field (e.g., "Research & Development")
    - "Experience Level" field
    - "Description" snippet
    - "Job ID" (e.g., "R00138081")
  - Pagination: URL param ?page=N works (page 1, 2, 3, ...)
  - ~12 jobs per page, ~1,100 total results
  - The page also has a "Learn more" link for each job
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://careers.abbvie.com"


class AttraxScraper(BaseScraper):
    """Scrapes job listings from AbbVie's Attrax-based career site."""

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        super().__init__(source_config, pipeline_config)
        self.max_pages = source_config.params.get("max_pages", 20)
        self.keywords = source_config.keywords

    def scrape(self) -> list[JobPosting]:
        """Fetch all jobs from AbbVie careers, paginating through results."""
        logger.info("[%s] Starting AbbVie (Attrax) scrape", self.name)
        all_jobs: list[JobPosting] = []

        for page in range(1, self.max_pages + 1):
            url = self._build_search_url(page)
            logger.debug("[%s] Fetching page %d: %s", self.name, page, url)

            try:
                resp = self._get(url)
            except Exception:
                logger.warning("[%s] Failed to fetch page %d, stopping", self.name, page)
                break

            page_jobs = self._parse_page(resp.text)

            if not page_jobs:
                logger.debug("[%s] No jobs on page %d, stopping", self.name, page)
                break

            all_jobs.extend(page_jobs)
            logger.debug("[%s] Page %d: %d jobs", self.name, page, len(page_jobs))

        logger.info("[%s] Total: %d jobs scraped", self.name, len(all_jobs))
        return all_jobs

    def _build_search_url(self, page: int = 1) -> str:
        """Build the Attrax search URL with pagination."""
        params: dict[str, str] = {}

        if self.keywords:
            params["q"] = " ".join(self.keywords)

        if page > 1:
            params["page"] = str(page)

        base = f"{BASE_URL}/en/jobs"
        if params:
            return f"{base}?{urlencode(params)}"
        return base

    def _parse_page(self, html: str) -> list[JobPosting]:
        """Parse job listings from a single Attrax HTML page.

        The AbbVie Attrax page has a very structured layout. Each job
        block contains labeled fields that we can extract by looking
        for links to job detail pages and then extracting sibling text.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []

        # Find all job links — they point to /en/job/{slug}
        # Each job appears twice (title + "Learn more") so we deduplicate
        seen_urls: set[str] = set()

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "/en/job/" not in href:
                continue

            # Normalize URL
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)

            # Skip duplicates (each job has title link + "Learn more" link)
            if href in seen_urls:
                continue

            title = link.get_text(strip=True)
            if not title or title == "Learn more" or len(title) < 3:
                continue

            seen_urls.add(href)

            # Find the job block — walk up to find the containing element
            # that has all the job fields
            job_block = self._find_job_block(link)

            salary = ""
            location = ""
            department = ""
            description = ""
            job_id = ""

            if job_block:
                block_text = job_block.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in block_text.split("\n") if l.strip()]

                # Parse labeled fields from the block text
                salary = self._extract_field(lines, "Salary")
                location = self._extract_field(lines, "Location")
                department = self._extract_field(lines, "Function")
                description = self._extract_field(lines, "Description")
                job_id = self._extract_field(lines, "Job ID")

                # If we got multiple Job IDs, prefer the one starting with R
                if not job_id:
                    for line in lines:
                        if re.match(r"R\d{8}", line):
                            job_id = line
                            break

                # If location wasn't found by label, look for city/state pattern
                if not location:
                    for line in lines:
                        if re.match(r"[A-Z][a-z]+.*,\s*[A-Z]{2}", line):
                            location = line
                            break

            jobs.append(JobPosting(
                title=title,
                company="AbbVie",
                url=href,
                source="attrax:abbvie",
                location=location,
                salary=salary,
                description=description,
                department=department,
                job_id=job_id,
            ))

        return jobs

    def _find_job_block(self, link_element) -> object | None:
        """Walk up the DOM to find the container that holds all job fields."""
        # Walk up looking for a container that has salary/location info
        for parent in link_element.parents:
            text = parent.get_text(strip=True) if parent.name else ""
            # The job block should contain "Location" and either "Salary" or "Job ID"
            if "Location" in text and ("Salary" in text or "Job ID" in text):
                # Make sure it's not the entire page
                if parent.name in ("div", "li", "article", "section", "tr"):
                    return parent
                # If it's too large, keep going
                if len(text) > 5000:
                    continue
                return parent
        return None

    def _extract_field(self, lines: list[str], field_name: str) -> str:
        """Extract the value following a field label in the text lines.

        Example: lines like ["Salary", "$82,500 - $157,500"] → returns "$82,500 - $157,500"
        """
        for i, line in enumerate(lines):
            if line.strip().lower() == field_name.lower():
                # Return the next non-empty line
                for j in range(i + 1, min(i + 3, len(lines))):
                    val = lines[j].strip()
                    # Don't return another label
                    if val and val not in (
                        "Salary", "Location", "Function", "Description",
                        "Job ID", "Job Type", "Experience Level", "Brands",
                        "Travel", "Therapy Area", "Expiry Date", "Learn more",
                    ):
                        return val
        return ""
