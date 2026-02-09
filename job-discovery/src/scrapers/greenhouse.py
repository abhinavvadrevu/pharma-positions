"""Greenhouse job board scraper.

Greenhouse provides a public JSON API at:
  https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs

This returns structured data with title, location, department, and
a link to each job's full description. It's the easiest and most
reliable scraper — no HTML parsing or browser rendering required.

Covers:
  - BridgeBio (board_token: bridgebio)
  - Revolution Medicines (board_token: revolutionmedicines)
"""

from __future__ import annotations

import logging

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseScraper(BaseScraper):
    """Fetches job listings from the Greenhouse public JSON API."""

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        super().__init__(source_config, pipeline_config)
        self.board_token = source_config.params.get("board_token", "")
        self.company_name = source_config.company
        if not self.board_token:
            raise ValueError(
                f"Greenhouse scraper '{source_config.name}' requires "
                f"params.board_token in config"
            )

    def scrape(self) -> list[JobPosting]:
        """Fetch all jobs from the Greenhouse board API."""
        logger.info(
            "[%s] Fetching jobs from Greenhouse API (board=%s)",
            self.name,
            self.board_token,
        )

        url = f"{API_BASE}/{self.board_token}/jobs"
        params = {"content": "true"}  # include job description HTML

        try:
            resp = self._get(url, params=params)
        except Exception:
            logger.error("[%s] Failed to fetch Greenhouse API", self.name)
            return []

        data = resp.json()
        raw_jobs = data.get("jobs", [])
        logger.info("[%s] API returned %d jobs", self.name, len(raw_jobs))

        jobs: list[JobPosting] = []
        for raw in raw_jobs:
            job = self._parse_job(raw)
            if job:
                jobs.append(job)

        return jobs

    def _parse_job(self, raw: dict) -> JobPosting | None:
        """Convert a single Greenhouse API job object into a JobPosting."""
        title = raw.get("title", "").strip()
        if not title:
            return None

        # Location — Greenhouse lists locations as an array
        locations = raw.get("location", {})
        location_name = locations.get("name", "") if isinstance(locations, dict) else ""

        # Departments
        departments = raw.get("departments", [])
        department = departments[0].get("name", "") if departments else ""

        # Full description HTML → plain text
        content = raw.get("content", "")
        description = self._html_to_text(content) if content else ""

        # Absolute URL to the posting
        absolute_url = raw.get("absolute_url", "")

        # Greenhouse job ID
        job_id = str(raw.get("id", ""))

        # Posted date
        updated_at = raw.get("updated_at", "")

        return JobPosting(
            title=title,
            company=self.company_name,
            url=absolute_url,
            source=f"greenhouse:{self.board_token}",
            location=location_name,
            description=description,
            department=department,
            job_id=job_id,
            posted_date=updated_at,
        )

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML content to plain text."""
        from bs4 import BeautifulSoup

        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)
