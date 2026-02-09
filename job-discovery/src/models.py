"""Data models for the job discovery pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class JobPosting:
    """Represents a single discovered job posting.

    Fields follow the PRD spec — every job must have at minimum:
    title, company, url, location, source, and description.
    """

    title: str
    company: str
    url: str
    source: str  # e.g. "biospace", "greenhouse:bridgebio", "workday:gilead"
    location: str = ""
    description: str = ""
    salary: str = ""
    department: str = ""
    job_id: str = ""
    posted_date: Optional[str] = None
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def fingerprint(self) -> str:
        """A stable hash for deduplication.

        Uses the canonical URL as the primary key. If two sources point
        to the same URL, they represent the same job.
        """
        normalized = self.url.strip().rstrip("/").lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        d = asdict(self)
        d["fingerprint"] = self.fingerprint
        return d

    def __repr__(self) -> str:
        return (
            f"JobPosting(title={self.title!r}, company={self.company!r}, "
            f"source={self.source!r}, location={self.location!r})"
        )
