"""Workday job portal scraper.

Workday portals are JavaScript SPAs that make predictable API calls
under the hood. The key endpoint pattern is:

  POST https://{company}.{wd_instance}.myworkdayjobs.com/wday/cxs/{company}/{site}/jobs

This endpoint accepts JSON with search criteria and pagination, and
returns structured job data. Since the API is well-documented in
open-source projects, we call it directly — no browser rendering needed.

Covers:
  - Gilead: gilead.wd1.myworkdayjobs.com/gileadcareers
  - Bristol Myers Squibb: bristolmyerssquibb.wd5.myworkdayjobs.com/BMS
"""

from __future__ import annotations

import logging

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Default page size for Workday API requests
DEFAULT_PAGE_SIZE = 20


class WorkdayScraper(BaseScraper):
    """Fetches job listings from Workday career portals via their internal API."""

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        super().__init__(source_config, pipeline_config)

        # Required params from config
        self.base_url = source_config.url.rstrip("/")
        self.company_name = source_config.company

        # Parse Workday-specific URL components
        # e.g., "https://gilead.wd1.myworkdayjobs.com/gileadcareers"
        # → tenant = "gilead", site = "gileadcareers"
        self.tenant = source_config.params.get("tenant", "")
        self.site = source_config.params.get("site", "")
        self.max_pages = source_config.params.get("max_pages", 50)
        self.page_size = source_config.params.get("page_size", DEFAULT_PAGE_SIZE)

        # Keywords are passed as searchText to the Workday API for server-side filtering
        self.search_text = " ".join(source_config.keywords) if source_config.keywords else ""

        if not self.tenant or not self.site:
            raise ValueError(
                f"Workday scraper '{source_config.name}' requires "
                f"params.tenant and params.site in config"
            )

    def scrape(self) -> list[JobPosting]:
        """Fetch all jobs via the Workday internal API."""
        if self.search_text:
            logger.info(
                "[%s] Fetching jobs from Workday API (tenant=%s, site=%s, searchText=%r)",
                self.name, self.tenant, self.site, self.search_text,
            )
        else:
            logger.info(
                "[%s] Fetching jobs from Workday API (tenant=%s, site=%s)",
                self.name, self.tenant, self.site,
            )

        all_jobs: list[JobPosting] = []
        offset = 0
        total: int | None = None  # Capture from first response only

        for page in range(1, self.max_pages + 1):
            logger.debug("[%s] Fetching page %d (offset=%d)", self.name, page, offset)

            try:
                data = self._fetch_page(offset)
            except Exception as exc:
                logger.error("[%s] API request failed at offset %d: %s", self.name, offset, exc)
                break

            job_postings = data.get("jobPostings", [])

            # Workday only returns the real total on the FIRST request.
            # Subsequent requests return total=0. So we capture it once.
            if total is None:
                total = data.get("total", 0)
                logger.info("[%s] API reports %d total jobs", self.name, total)

            if not job_postings:
                break

            for raw in job_postings:
                job = self._parse_job(raw)
                if job:
                    all_jobs.append(job)

            offset += self.page_size
            if offset >= total:
                break

        logger.info("[%s] Scraped %d of %d jobs", self.name, len(all_jobs), total or 0)
        return all_jobs

    def _fetch_page(self, offset: int) -> dict:
        """Call the Workday jobs API for a single page of results."""
        api_url = f"{self.base_url}/wday/cxs/{self.tenant}/{self.site}/jobs"

        payload = {
            "appliedFacets": {},
            "limit": self.page_size,
            "offset": offset,
            "searchText": self.search_text,
        }

        # Workday API expects specific headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        resp = self._post(api_url, json=payload, headers=headers)
        return resp.json()

    def _parse_job(self, raw: dict) -> JobPosting | None:
        """Convert a Workday API job object into a JobPosting."""
        title = raw.get("title", "").strip()
        if not title:
            return None

        # Build the full URL to the job posting
        external_path = raw.get("externalPath", "")
        job_url = f"{self.base_url}{external_path}" if external_path else ""

        # Location — Workday returns locationsText or bulletFields
        location = raw.get("locationsText", "")

        # Posted date
        posted_on = raw.get("postedOn", "")

        # Workday sometimes includes bullet fields with extra info
        bullet_fields = raw.get("bulletFields", [])
        extra_info = " | ".join(bullet_fields) if bullet_fields else ""

        return JobPosting(
            title=title,
            company=self.company_name,
            url=job_url,
            source=f"workday:{self.tenant}",
            location=location,
            description=extra_info,  # Brief info; full description requires a second API call
            posted_date=posted_on,
        )

    def fetch_job_detail(self, external_path: str) -> str:
        """Fetch the full job description for a specific posting.

        This makes a second API call to get the complete job details.
        Call this selectively — not for every job in the initial listing.
        """
        api_url = f"{self.base_url}/wday/cxs/{self.tenant}/{self.site}{external_path}"

        try:
            resp = self._get(api_url, headers={"Accept": "application/json"})
            data = resp.json()
            return data.get("jobPostingInfo", {}).get("jobDescription", "")
        except Exception:
            logger.warning("[%s] Failed to fetch detail for %s", self.name, external_path)
            return ""
