"""Configuration loader for the job discovery pipeline.

Reads config.yaml and returns typed configuration objects that the
orchestrator and individual scrapers consume.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass
class ScraperConfig:
    """Configuration for a single scraper source."""

    name: str
    scraper_type: str  # "biospace", "greenhouse", "attrax", "workday", etc.
    enabled: bool = True
    url: str = ""
    company: str = ""
    keywords: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchCriteria:
    """Criteria for cheap filtering of job postings."""

    max_age_days: int = 14
    title_include: list[str] = field(default_factory=list)
    title_exclude: list[str] = field(default_factory=list)


@dataclass
class PipelineConfig:
    """Top-level pipeline configuration."""

    sources: list[ScraperConfig] = field(default_factory=list)
    output_dir: str = "output"
    data_dir: str = "data"
    log_level: str = "INFO"
    request_delay_seconds: float = 1.0  # polite delay between HTTP requests
    request_timeout_seconds: float = 30.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Candidate profile and matching criteria
    candidate_profile: str = ""
    target_titles: list[str] = field(default_factory=list)
    education_guideline: str = ""
    key_domain_terms: list[str] = field(default_factory=list)
    match_criteria: MatchCriteria = field(default_factory=MatchCriteria)

    @property
    def enabled_sources(self) -> list[ScraperConfig]:
        return [s for s in self.sources if s.enabled]


def load_config(path: Path | str | None = None) -> PipelineConfig:
    """Load and validate the pipeline configuration from a YAML file."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        logger.warning("Config file not found at %s — using defaults", config_path)
        return PipelineConfig()

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    if not raw:
        return PipelineConfig()

    sources = []
    for src in raw.get("sources", []):
        sources.append(
            ScraperConfig(
                name=src["name"],
                scraper_type=src["scraper_type"],
                enabled=src.get("enabled", True),
                url=src.get("url", ""),
                company=src.get("company", ""),
                keywords=src.get("keywords", []),
                params=src.get("params", {}),
            )
        )

    # Parse match criteria
    match_raw = raw.get("match_criteria", {})
    match_criteria = MatchCriteria(
        max_age_days=match_raw.get("max_age_days", 14),
        title_include=match_raw.get("title_include", []),
        title_exclude=match_raw.get("title_exclude", []),
    )

    return PipelineConfig(
        sources=sources,
        output_dir=raw.get("output_dir", "output"),
        data_dir=raw.get("data_dir", "data"),
        log_level=raw.get("log_level", "INFO"),
        request_delay_seconds=raw.get("request_delay_seconds", 1.0),
        request_timeout_seconds=raw.get("request_timeout_seconds", 30.0),
        user_agent=raw.get("user_agent", PipelineConfig.user_agent),
        candidate_profile=raw.get("candidate_profile", ""),
        target_titles=raw.get("target_titles", []),
        education_guideline=raw.get("education_guideline", ""),
        key_domain_terms=raw.get("key_domain_terms", []),
        match_criteria=match_criteria,
    )
