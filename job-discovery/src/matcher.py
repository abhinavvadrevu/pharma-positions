"""Matcher module for the job discovery pipeline.

Implements cheap filters (Stage 1 matching) as specified in the PRD:
1. Duplicate check — skip URLs we've already processed
2. Age filter — discard postings older than max_age_days
3. Title keyword filter — include/exclude based on title keywords

Jobs that pass all filters are written to data/candidates.json for
the LLM evaluation skill (Stage 2) to read and evaluate.

This module does NOT involve any LLM calls — it's pure Python filtering
designed to be fast and reduce the number of jobs the LLM needs to evaluate.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import NamedTuple

from src.config import PipelineConfig
from src.models import JobPosting
from src.storage import normalize_url

logger = logging.getLogger(__name__)


class RejectionReason(Enum):
    """Why a job was rejected by cheap filters."""

    DUPLICATE = "REJECTED_DUPLICATE"
    AGE = "REJECTED_AGE"
    TITLE_EXCLUDE = "REJECTED_TITLE_EXCLUDE"
    TITLE_NO_MATCH = "REJECTED_TITLE_NO_MATCH"


class FilterResult(NamedTuple):
    """Result of filtering a single job."""

    job: JobPosting
    passed: bool
    reason: RejectionReason | None = None


# ── Date Parsing ────────────────────────────────────────────────────────────


def parse_posted_date(date_str: str | None) -> datetime | None:
    """Parse a posted date string into a datetime.

    Handles various formats:
    - ISO 8601: "2026-02-01", "2026-02-01T00:00:00Z"
    - Relative: "30+ days ago", "2 days ago", "today", "yesterday"
    - Month day: "Feb 1, 2026", "February 1, 2026"

    Returns None if parsing fails (job should be included when date unknown).
    """
    if not date_str:
        return None

    date_str = date_str.strip().lower()

    # Handle relative dates
    if "today" in date_str:
        return datetime.now(timezone.utc)
    if "yesterday" in date_str:
        return datetime.now(timezone.utc) - timedelta(days=1)

    # "X days ago" pattern
    days_ago_match = re.search(r"(\d+)\+?\s*days?\s*ago", date_str)
    if days_ago_match:
        days = int(days_ago_match.group(1))
        return datetime.now(timezone.utc) - timedelta(days=days)

    # "X weeks ago" pattern
    weeks_ago_match = re.search(r"(\d+)\+?\s*weeks?\s*ago", date_str)
    if weeks_ago_match:
        weeks = int(weeks_ago_match.group(1))
        return datetime.now(timezone.utc) - timedelta(weeks=weeks)

    # "X months ago" pattern (approximate as 30 days)
    months_ago_match = re.search(r"(\d+)\+?\s*months?\s*ago", date_str)
    if months_ago_match:
        months = int(months_ago_match.group(1))
        return datetime.now(timezone.utc) - timedelta(days=months * 30)

    # Try ISO format variations
    for fmt in [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%m/%d/%Y",
        "%m-%d-%Y",
    ]:
        try:
            # Parse and make timezone-aware
            parsed = datetime.strptime(date_str, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue

    logger.debug("Could not parse date: %r", date_str)
    return None


# ── Title Matching ──────────────────────────────────────────────────────────


def title_matches_include(title: str, include_keywords: list[str]) -> bool:
    """Check if title contains any of the include keywords (case-insensitive)."""
    if not include_keywords:
        # No include list means include everything
        return True

    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in include_keywords)


def title_matches_exclude(title: str, exclude_keywords: list[str]) -> bool:
    """Check if title contains any of the exclude keywords (case-insensitive)."""
    if not exclude_keywords:
        return False

    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in exclude_keywords)


# ── Cheap Filters ───────────────────────────────────────────────────────────


def apply_duplicate_filter(
    jobs: list[JobPosting],
    seen_urls: set[str],
) -> tuple[list[JobPosting], list[FilterResult]]:
    """Filter out jobs with URLs we've already processed.

    Args:
        jobs: List of jobs to filter
        seen_urls: Set of normalized URLs we've already seen

    Returns:
        (passed_jobs, rejected_results)
    """
    passed = []
    rejected = []

    for job in jobs:
        normalized = normalize_url(job.url)
        if normalized in seen_urls:
            rejected.append(FilterResult(job, False, RejectionReason.DUPLICATE))
        else:
            passed.append(job)

    logger.debug(
        "Duplicate filter: %d passed, %d rejected", len(passed), len(rejected)
    )
    return passed, rejected


def apply_age_filter(
    jobs: list[JobPosting],
    max_age_days: int,
) -> tuple[list[JobPosting], list[FilterResult]]:
    """Filter out jobs older than max_age_days.

    Jobs without a parseable date are included (fail open).

    Args:
        jobs: List of jobs to filter
        max_age_days: Maximum age in days

    Returns:
        (passed_jobs, rejected_results)
    """
    passed = []
    rejected = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    for job in jobs:
        posted_date = parse_posted_date(job.posted_date)

        if posted_date is None:
            # No date available — include the job (fail open)
            passed.append(job)
        elif posted_date >= cutoff:
            passed.append(job)
        else:
            rejected.append(FilterResult(job, False, RejectionReason.AGE))

    logger.debug("Age filter: %d passed, %d rejected", len(passed), len(rejected))
    return passed, rejected


def apply_title_filter(
    jobs: list[JobPosting],
    include_keywords: list[str],
    exclude_keywords: list[str],
) -> tuple[list[JobPosting], list[FilterResult]]:
    """Filter jobs by title keywords.

    A job passes if:
    1. Its title contains at least one include keyword (or include list is empty)
    2. Its title does NOT contain any exclude keyword

    Exclusion is checked after inclusion — exclude overrides include.

    Args:
        jobs: List of jobs to filter
        include_keywords: Keywords that should appear in title
        exclude_keywords: Keywords that should NOT appear in title

    Returns:
        (passed_jobs, rejected_results)
    """
    passed = []
    rejected = []

    for job in jobs:
        # Check exclusion first (it overrides)
        if title_matches_exclude(job.title, exclude_keywords):
            rejected.append(FilterResult(job, False, RejectionReason.TITLE_EXCLUDE))
            continue

        # Check inclusion
        if title_matches_include(job.title, include_keywords):
            passed.append(job)
        else:
            rejected.append(FilterResult(job, False, RejectionReason.TITLE_NO_MATCH))

    logger.debug("Title filter: %d passed, %d rejected", len(passed), len(rejected))
    return passed, rejected


def cheap_filters(
    jobs: list[JobPosting],
    seen_urls: set[str],
    config: PipelineConfig,
) -> tuple[list[JobPosting], list[FilterResult]]:
    """Apply all cheap filters in sequence.

    Filter order (each operates on output of previous):
    1. Duplicate check (cheapest — dict lookup)
    2. Age filter
    3. Title keyword filter

    Args:
        jobs: Raw jobs from discovery
        seen_urls: Set of normalized URLs already processed
        config: Pipeline configuration with match criteria

    Returns:
        (passed_jobs, all_rejection_results)
    """
    all_rejected: list[FilterResult] = []

    # 1. Duplicate filter
    jobs, rejected = apply_duplicate_filter(jobs, seen_urls)
    all_rejected.extend(rejected)

    # 2. Age filter
    jobs, rejected = apply_age_filter(jobs, config.match_criteria.max_age_days)
    all_rejected.extend(rejected)

    # 3. Title filter
    jobs, rejected = apply_title_filter(
        jobs,
        config.match_criteria.title_include,
        config.match_criteria.title_exclude,
    )
    all_rejected.extend(rejected)

    logger.info(
        "Cheap filters complete: %d passed, %d rejected",
        len(jobs),
        len(all_rejected),
    )

    return jobs, all_rejected


# ── Candidates File ─────────────────────────────────────────────────────────


def write_candidates(
    jobs: list[JobPosting],
    data_dir: str | Path = "data",
) -> Path:
    """Write filtered jobs to data/candidates.json for LLM evaluation.

    This file is overwritten on each run — it's a working file, not a log.
    The evaluation skill reads this file and evaluates each job.

    Args:
        jobs: Jobs that passed cheap filtering
        data_dir: Directory to write to

    Returns:
        Path to the written file
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    candidates_path = data_path / "candidates.json"

    # Convert jobs to dicts for JSON serialization
    candidates = []
    for job in jobs:
        candidates.append({
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "location": job.location,
            "department": job.department,
            "date_posted": job.posted_date,
            "source": job.source,
            "description": job.description or "",
        })

    with open(candidates_path, "w") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d candidates to %s", len(candidates), candidates_path)
    return candidates_path


def load_candidates(data_dir: str | Path = "data") -> list[dict]:
    """Load candidates from data/candidates.json.

    Used by the evaluation skill to read jobs for LLM evaluation.

    Args:
        data_dir: Directory containing candidates.json

    Returns:
        List of candidate job dicts
    """
    candidates_path = Path(data_dir) / "candidates.json"

    if not candidates_path.exists():
        logger.warning("No candidates file found at %s", candidates_path)
        return []

    with open(candidates_path, "r") as f:
        return json.load(f)


# ── Main Entry Point ────────────────────────────────────────────────────────


def run_matching(
    jobs: list[JobPosting],
    seen_urls: set[str],
    config: PipelineConfig,
) -> tuple[Path, list[FilterResult]]:
    """Run the full matching module: cheap filters + write candidates file.

    This is the main entry point called by the pipeline. It:
    1. Applies all cheap filters
    2. Writes surviving jobs to data/candidates.json
    3. Returns the path and rejection log

    The evaluation skill then reads candidates.json and evaluates each job.

    Args:
        jobs: Raw jobs from discovery
        seen_urls: Set of normalized URLs already processed
        config: Pipeline configuration

    Returns:
        (candidates_file_path, rejection_log)
    """
    # Apply cheap filters
    passed_jobs, rejection_log = cheap_filters(jobs, seen_urls, config)

    # Write candidates file
    candidates_path = write_candidates(passed_jobs, config.data_dir)

    return candidates_path, rejection_log


def get_rejection_summary(results: list[FilterResult]) -> dict[str, int]:
    """Summarize rejection results by reason.

    Args:
        results: List of rejection results

    Returns:
        Dict mapping reason name to count
    """
    summary: dict[str, int] = {}
    for result in results:
        if result.reason:
            key = result.reason.value
            summary[key] = summary.get(key, 0) + 1
    return summary
