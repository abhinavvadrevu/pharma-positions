"""BioSpace job scraper.

BioSpace (biospace.com/jobs) is a pharma/biotech-specific job aggregator
with ~3,500 active listings. The site is server-rendered HTML.

Two URL patterns are supported:
  1. Browse all jobs:  /jobs/, /jobs/2/, /jobs/3/, ...
  2. Keyword search:   /searchjobs/?Keywords=drug+product&page=N
     (Note: /jobs/?q= does NOT filter — use /searchjobs/ instead)

Actual HTML structure (verified 2026-02-07):
  - Job results live in an unordered list
  - Each job is an <li> containing:
    - <h3> with an <a> linking to /job/{id}/{slug}/
    - Company name, location, salary, and description snippet as text
  - ~20 jobs per page
  - RSS feed at /jobsrss/ is DEAD (returns 404)

The actual job links use the domain biospace.com (not jobs.biospace.com).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.biospace.com"
JOBS_URL = f"{BASE_URL}/jobs"


class BioSpaceScraper(BaseScraper):
    """Scrapes job postings from BioSpace via server-rendered HTML."""

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        super().__init__(source_config, pipeline_config)
        self.keywords = [kw.lower() for kw in source_config.keywords]
        self.max_pages = source_config.params.get("max_pages", 20)

    def scrape(self) -> list[JobPosting]:
        """Fetch jobs via HTML pagination with server-side keyword filtering."""
        search_query = " ".join(self.keywords) if self.keywords else ""
        if search_query:
            logger.info(
                "[%s] Starting BioSpace scrape with Keywords=%r (max %d pages)",
                self.name, search_query, self.max_pages,
            )
        else:
            logger.info("[%s] Starting BioSpace scrape (max %d pages)", self.name, self.max_pages)

        jobs = self._scrape_html(search_query)
        logger.info("[%s] Got %d jobs from HTML scraping", self.name, len(jobs))

        return jobs

    def _scrape_html(self, search_query: str = "") -> list[JobPosting]:
        """Scrape job listings from paginated HTML pages.

        If search_query is provided, uses /searchjobs/?Keywords= endpoint
        for server-side filtering. Otherwise uses /jobs/ for all listings.
        """
        all_jobs: list[JobPosting] = []

        for page_num in range(1, self.max_pages + 1):
            if search_query:
                # Keyword search uses /searchjobs/?Keywords=...&page=N
                params = {"Keywords": search_query}
                if page_num > 1:
                    params["page"] = str(page_num)
                url = f"{BASE_URL}/searchjobs/?{urlencode(params)}"
            else:
                # Browse all uses /jobs/ with /jobs/{N}/ pagination
                if page_num > 1:
                    url = f"{JOBS_URL}/{page_num}/"
                else:
                    url = f"{JOBS_URL}/"

            logger.debug("[%s] Fetching page %d: %s", self.name, page_num, url)

            try:
                resp = self._get(url)
            except Exception:
                logger.warning("[%s] Failed to fetch page %d, stopping", self.name, page_num)
                break

            page_jobs = self._parse_html_page(resp.text)

            if not page_jobs:
                logger.debug("[%s] No jobs found on page %d, stopping", self.name, page_num)
                break

            all_jobs.extend(page_jobs)
            logger.debug("[%s] Page %d: found %d jobs", self.name, page_num, len(page_jobs))

        return all_jobs

    def _parse_html_page(self, html: str) -> list[JobPosting]:
        """Parse a single BioSpace HTML page.

        BioSpace structure (verified against live site):
        - Job listings are <li> items inside the results section
        - Each <li> has an <h3> with <a> for the title/link
        - The <li> also contains company name, location, salary, description
        - Job links look like: /job/3030376/medical-director-clinical-development/
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []

        # Find all <h3> tags that contain job title links
        # These link to /job/{id}/{slug}/
        for h3 in soup.find_all("h3"):
            link = h3.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "")
            # Only process actual job links
            if "/job/" not in href:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Normalize the URL
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)

            # The job card is the parent <li> of the <h3>
            card = h3.find_parent("li")
            if not card:
                card = h3.find_parent(["div", "article", "section"])

            company = ""
            location = ""
            salary = ""
            description = ""

            if card:
                # Extract all text elements from the card
                card_text = card.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in card_text.split("\n") if line.strip()]

                # Remove the title from the lines
                lines = [l for l in lines if l != title and "View details" not in l
                         and "Save" not in l and "sign in" not in l
                         and "create an account" not in l]

                # Look for salary pattern ($ followed by numbers)
                for line in lines:
                    if re.match(r"\$[\d,]+", line):
                        salary = line
                        break

                # Find company — look for image alt text or the last meaningful text
                # Company logos have alt text like "Amgen logo"
                img = card.find("img", alt=True)
                if img:
                    alt = img.get("alt", "")
                    if alt.endswith(" logo"):
                        company = alt[:-5].strip()

                # Extract location and description from remaining lines
                non_salary_lines = [l for l in lines if l != salary and l != company]

                # First non-title, non-salary line is often location
                # Lines with state/city patterns or "Remote" are locations
                for line in non_salary_lines:
                    if self._looks_like_location(line):
                        location = line
                        break

                # Description is usually the longest remaining line
                remaining = [l for l in non_salary_lines if l != location and len(l) > 20]
                if remaining:
                    # The description is typically the longest text block
                    description = max(remaining, key=len)

            job = JobPosting(
                title=title,
                company=company,
                url=href,
                source="biospace",
                location=location,
                salary=salary,
                description=description,
            )
            jobs.append(job)

        return jobs

    @staticmethod
    def _looks_like_location(text: str) -> bool:
        """Heuristic: does this text look like a location?"""
        location_patterns = [
            r"Remote",
            r"[A-Z][a-z]+,\s*[A-Z]{2}",           # City, ST
            r"[A-Z][a-z]+,\s*[A-Za-z\s]+",         # City, State Name
            r"United States",
            r"[A-Z][a-z]+\s*--\s*\[",              # "City -- [Remote/Home-Based]"
            r"Fully remote",
        ]
        for pattern in location_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _filter_by_keywords(self, jobs: list[JobPosting]) -> list[JobPosting]:
        """Keep only jobs that match at least one configured keyword."""
        if not self.keywords:
            return jobs

        filtered = []
        for job in jobs:
            searchable = f"{job.title} {job.description} {job.department}".lower()
            if any(kw in searchable for kw in self.keywords):
                filtered.append(job)
        return filtered
