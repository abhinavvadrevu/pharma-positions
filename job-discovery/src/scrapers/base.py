"""Abstract base class for all job scrapers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import requests

from src.config import ScraperConfig, PipelineConfig
from src.models import JobPosting

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class that all platform-specific scrapers extend.

    Provides shared HTTP utilities (session management, rate limiting,
    retries) so individual scrapers only need to implement `scrape()`.
    """

    def __init__(self, source_config: ScraperConfig, pipeline_config: PipelineConfig):
        self.source_config = source_config
        self.pipeline_config = pipeline_config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": pipeline_config.user_agent})
        self._last_request_time: float = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @abstractmethod
    def scrape(self) -> list[JobPosting]:
        """Fetch and return all job postings from this source.

        Must be implemented by every subclass.
        """
        ...

    @property
    def name(self) -> str:
        return self.source_config.name

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Rate-limited GET request with retries."""
        self._rate_limit()
        kwargs.setdefault("timeout", self.pipeline_config.request_timeout_seconds)

        for attempt in range(1, 4):
            try:
                resp = self.session.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                logger.warning(
                    "[%s] GET %s attempt %d failed: %s", self.name, url, attempt, exc
                )
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

        # Unreachable, but keeps type checkers happy
        raise RuntimeError("Retry loop exited unexpectedly")

    def _post(self, url: str, **kwargs) -> requests.Response:
        """Rate-limited POST request with retries."""
        self._rate_limit()
        kwargs.setdefault("timeout", self.pipeline_config.request_timeout_seconds)

        for attempt in range(1, 4):
            try:
                resp = self.session.post(url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                logger.warning(
                    "[%s] POST %s attempt %d failed: %s", self.name, url, attempt, exc
                )
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Retry loop exited unexpectedly")

    def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        delay = self.pipeline_config.request_delay_seconds
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.monotonic()
