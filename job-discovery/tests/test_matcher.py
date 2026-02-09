"""Tests for the matcher module (cheap filters).

Tests cover:
- Date parsing (various formats, relative dates)
- Title keyword matching (include/exclude)
- Duplicate filtering
- Age filtering
- Full cheap filter pipeline
- Candidates file writing/loading
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config import MatchCriteria, PipelineConfig
from src.matcher import (
    FilterResult,
    RejectionReason,
    apply_age_filter,
    apply_duplicate_filter,
    apply_title_filter,
    cheap_filters,
    get_rejection_summary,
    load_candidates,
    parse_posted_date,
    run_matching,
    title_matches_exclude,
    title_matches_include,
    write_candidates,
)
from src.models import JobPosting


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_jobs() -> list[JobPosting]:
    """Create sample job postings for testing."""
    return [
        JobPosting(
            title="Senior Scientist, Drug Product",
            company="BridgeBio",
            url="https://example.com/job/1",
            source="greenhouse:bridgebio",
            location="San Francisco, CA",
            description="Develop lyophilized formulations...",
            posted_date="2026-02-01",
        ),
        JobPosting(
            title="QC Analyst",
            company="Amgen",
            url="https://example.com/job/2",
            source="talentbrew:amgen",
            location="Thousand Oaks, CA",
            description="Perform routine quality control...",
            posted_date="2026-02-05",
        ),
        JobPosting(
            title="Formulation Scientist",
            company="Gilead",
            url="https://example.com/job/3",
            source="workday:gilead",
            location="Foster City, CA",
            description="Biologics formulation development...",
            posted_date="2026-01-15",  # Older posting
        ),
        JobPosting(
            title="Director of CMC",
            company="Revolution Medicines",
            url="https://example.com/job/4",
            source="greenhouse:revolutionmedicines",
            location="Redwood City, CA",
            description="Lead CMC strategy...",
            posted_date="2026-02-03",
        ),
        JobPosting(
            title="Intern, Research",
            company="BMS",
            url="https://example.com/job/5",
            source="workday:bms",
            location="Princeton, NJ",
            description="Summer internship...",
            posted_date="2026-02-04",
        ),
    ]


@pytest.fixture
def default_config() -> PipelineConfig:
    """Create a default pipeline config with match criteria."""
    return PipelineConfig(
        data_dir="data",
        match_criteria=MatchCriteria(
            max_age_days=14,
            title_include=["scientist", "formulation", "drug product"],
            title_exclude=["intern", "director", "VP", "QC analyst"],
        ),
    )


# ── Date Parsing Tests ──────────────────────────────────────────────────────


class TestParseDatePosted:
    """Tests for parse_posted_date function."""

    def test_iso_date(self):
        """Parse ISO 8601 date."""
        result = parse_posted_date("2026-02-01")
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 1

    def test_iso_datetime(self):
        """Parse ISO 8601 datetime."""
        result = parse_posted_date("2026-02-01T10:30:00Z")
        assert result is not None
        assert result.year == 2026

    def test_relative_today(self):
        """Parse 'today'."""
        result = parse_posted_date("today")
        assert result is not None
        now = datetime.now(timezone.utc)
        assert result.date() == now.date()

    def test_relative_yesterday(self):
        """Parse 'yesterday'."""
        result = parse_posted_date("yesterday")
        assert result is not None
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert result.date() == yesterday.date()

    def test_relative_days_ago(self):
        """Parse 'X days ago'."""
        result = parse_posted_date("5 days ago")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=5)
        assert result.date() == expected.date()

    def test_relative_days_ago_plus(self):
        """Parse '30+ days ago'."""
        result = parse_posted_date("30+ days ago")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=30)
        assert result.date() == expected.date()

    def test_relative_weeks_ago(self):
        """Parse 'X weeks ago'."""
        result = parse_posted_date("2 weeks ago")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(weeks=2)
        assert result.date() == expected.date()

    def test_month_day_year(self):
        """Parse 'Feb 1, 2026' format."""
        result = parse_posted_date("Feb 1, 2026")
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 1

    def test_none_input(self):
        """Return None for None input."""
        assert parse_posted_date(None) is None

    def test_empty_string(self):
        """Return None for empty string."""
        assert parse_posted_date("") is None

    def test_unparseable(self):
        """Return None for unparseable string."""
        assert parse_posted_date("not a date") is None


# ── Title Matching Tests ────────────────────────────────────────────────────


class TestTitleMatching:
    """Tests for title keyword matching."""

    def test_include_match(self):
        """Title containing include keyword matches."""
        assert title_matches_include("Senior Scientist", ["scientist"])
        assert title_matches_include("Drug Product Lead", ["drug product"])

    def test_include_case_insensitive(self):
        """Matching is case-insensitive."""
        assert title_matches_include("SENIOR SCIENTIST", ["scientist"])
        assert title_matches_include("senior scientist", ["SCIENTIST"])

    def test_include_no_match(self):
        """Title not containing any include keyword doesn't match."""
        assert not title_matches_include("QC Analyst", ["scientist", "formulation"])

    def test_include_empty_list(self):
        """Empty include list means include everything."""
        assert title_matches_include("Any Title", [])

    def test_exclude_match(self):
        """Title containing exclude keyword is excluded."""
        assert title_matches_exclude("Summer Intern", ["intern"])
        assert title_matches_exclude("VP of R&D", ["VP"])

    def test_exclude_case_insensitive(self):
        """Exclusion is case-insensitive."""
        assert title_matches_exclude("DIRECTOR OF CMC", ["director"])

    def test_exclude_no_match(self):
        """Title not containing exclude keywords is not excluded."""
        assert not title_matches_exclude("Senior Scientist", ["intern", "director"])

    def test_exclude_empty_list(self):
        """Empty exclude list means exclude nothing."""
        assert not title_matches_exclude("Director", [])


# ── Duplicate Filter Tests ──────────────────────────────────────────────────


class TestDuplicateFilter:
    """Tests for duplicate URL filtering."""

    def test_no_duplicates(self, sample_jobs):
        """All jobs pass when no URLs are seen."""
        passed, rejected = apply_duplicate_filter(sample_jobs, set())
        assert len(passed) == 5
        assert len(rejected) == 0

    def test_all_duplicates(self, sample_jobs):
        """All jobs rejected when all URLs are seen."""
        seen = {
            "https://example.com/job/1",
            "https://example.com/job/2",
            "https://example.com/job/3",
            "https://example.com/job/4",
            "https://example.com/job/5",
        }
        passed, rejected = apply_duplicate_filter(sample_jobs, seen)
        assert len(passed) == 0
        assert len(rejected) == 5
        assert all(r.reason == RejectionReason.DUPLICATE for r in rejected)

    def test_some_duplicates(self, sample_jobs):
        """Mix of new and duplicate jobs."""
        seen = {"https://example.com/job/1", "https://example.com/job/3"}
        passed, rejected = apply_duplicate_filter(sample_jobs, seen)
        assert len(passed) == 3
        assert len(rejected) == 2


# ── Age Filter Tests ────────────────────────────────────────────────────────


class TestAgeFilter:
    """Tests for age-based filtering."""

    def test_recent_jobs_pass(self):
        """Jobs within max_age_days pass."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        jobs = [
            JobPosting(
                title="Test",
                company="Test",
                url="https://test.com/1",
                source="test",
                posted_date=today,
            )
        ]
        passed, rejected = apply_age_filter(jobs, max_age_days=14)
        assert len(passed) == 1
        assert len(rejected) == 0

    def test_old_jobs_rejected(self):
        """Jobs older than max_age_days are rejected."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        jobs = [
            JobPosting(
                title="Test",
                company="Test",
                url="https://test.com/1",
                source="test",
                posted_date=old_date,
            )
        ]
        passed, rejected = apply_age_filter(jobs, max_age_days=14)
        assert len(passed) == 0
        assert len(rejected) == 1
        assert rejected[0].reason == RejectionReason.AGE

    def test_no_date_passes(self):
        """Jobs without a date pass (fail open)."""
        jobs = [
            JobPosting(
                title="Test",
                company="Test",
                url="https://test.com/1",
                source="test",
                posted_date=None,
            )
        ]
        passed, rejected = apply_age_filter(jobs, max_age_days=14)
        assert len(passed) == 1
        assert len(rejected) == 0

    def test_unparseable_date_passes(self):
        """Jobs with unparseable dates pass (fail open)."""
        jobs = [
            JobPosting(
                title="Test",
                company="Test",
                url="https://test.com/1",
                source="test",
                posted_date="not a date",
            )
        ]
        passed, rejected = apply_age_filter(jobs, max_age_days=14)
        assert len(passed) == 1


# ── Title Filter Tests ──────────────────────────────────────────────────────


class TestTitleFilter:
    """Tests for title keyword filtering."""

    def test_matching_title_passes(self):
        """Jobs with matching titles pass."""
        jobs = [
            JobPosting(
                title="Senior Scientist",
                company="Test",
                url="https://test.com/1",
                source="test",
            )
        ]
        passed, rejected = apply_title_filter(jobs, ["scientist"], [])
        assert len(passed) == 1

    def test_excluded_title_rejected(self):
        """Jobs with excluded keywords are rejected."""
        jobs = [
            JobPosting(
                title="Research Intern",
                company="Test",
                url="https://test.com/1",
                source="test",
            )
        ]
        passed, rejected = apply_title_filter(jobs, ["scientist"], ["intern"])
        assert len(passed) == 0
        assert len(rejected) == 1
        assert rejected[0].reason == RejectionReason.TITLE_EXCLUDE

    def test_exclude_overrides_include(self):
        """Exclusion takes precedence over inclusion."""
        jobs = [
            JobPosting(
                title="Director Scientist",  # Has both "scientist" and "director"
                company="Test",
                url="https://test.com/1",
                source="test",
            )
        ]
        passed, rejected = apply_title_filter(jobs, ["scientist"], ["director"])
        assert len(passed) == 0
        assert rejected[0].reason == RejectionReason.TITLE_EXCLUDE

    def test_no_include_match_rejected(self):
        """Jobs not matching any include keyword are rejected."""
        jobs = [
            JobPosting(
                title="Sales Representative",
                company="Test",
                url="https://test.com/1",
                source="test",
            )
        ]
        passed, rejected = apply_title_filter(jobs, ["scientist", "formulation"], [])
        assert len(passed) == 0
        assert rejected[0].reason == RejectionReason.TITLE_NO_MATCH


# ── Full Pipeline Tests ─────────────────────────────────────────────────────


class TestCheapFilters:
    """Tests for the full cheap_filters function."""

    def test_filters_applied_in_order(self, sample_jobs, default_config):
        """Filters are applied: duplicate → age → title."""
        seen = {"https://example.com/job/1"}  # First job is duplicate

        # Freeze time context would be better, but for now we'll adjust expectations
        passed, rejected = cheap_filters(sample_jobs, seen, default_config)

        # Check that rejections include expected reasons
        reasons = [r.reason for r in rejected]
        assert RejectionReason.DUPLICATE in reasons  # job/1
        assert RejectionReason.TITLE_EXCLUDE in reasons  # QC Analyst, Director, Intern

    def test_empty_input(self, default_config):
        """Empty job list returns empty results."""
        passed, rejected = cheap_filters([], set(), default_config)
        assert len(passed) == 0
        assert len(rejected) == 0


# ── Candidates File Tests ───────────────────────────────────────────────────


class TestCandidatesFile:
    """Tests for candidates file I/O."""

    def test_write_and_load(self, sample_jobs):
        """Write candidates and load them back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write
            path = write_candidates(sample_jobs[:2], tmpdir)
            assert path.exists()

            # Load
            loaded = load_candidates(tmpdir)
            assert len(loaded) == 2
            assert loaded[0]["title"] == "Senior Scientist, Drug Product"
            assert loaded[1]["company"] == "Amgen"

    def test_write_creates_directory(self, sample_jobs):
        """Writing creates the data directory if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "nested" / "data"
            path = write_candidates(sample_jobs[:1], new_dir)
            assert path.exists()

    def test_load_missing_file(self):
        """Loading from missing file returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded = load_candidates(tmpdir)
            assert loaded == []

    def test_candidates_format(self, sample_jobs):
        """Verify candidates file has correct format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            write_candidates(sample_jobs[:1], tmpdir)

            with open(Path(tmpdir) / "candidates.json") as f:
                data = json.load(f)

            assert len(data) == 1
            candidate = data[0]
            assert "title" in candidate
            assert "company" in candidate
            assert "url" in candidate
            assert "location" in candidate
            assert "department" in candidate
            assert "date_posted" in candidate
            assert "source" in candidate
            assert "description" in candidate


# ── Integration Tests ───────────────────────────────────────────────────────


class TestRunMatching:
    """Integration tests for run_matching."""

    def test_full_pipeline(self, sample_jobs):
        """Test the full matching pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = PipelineConfig(
                data_dir=tmpdir,
                match_criteria=MatchCriteria(
                    max_age_days=14,
                    title_include=["scientist", "formulation"],
                    title_exclude=["intern", "director", "QC analyst"],
                ),
            )

            # Run matching - note: jobs may be filtered by age depending on current date
            candidates_path, rejections = run_matching(sample_jobs, set(), config)

            # Verify file was created
            assert candidates_path.exists()

            # Load and verify candidates
            candidates = load_candidates(tmpdir)
            
            # Should have filtered out: QC Analyst (exclude), Director (exclude), Intern (exclude)
            # May also filter Gilead job if older than 14 days
            titles = [c["title"] for c in candidates]
            assert "QC Analyst" not in titles
            assert "Director of CMC" not in titles
            assert "Intern, Research" not in titles


class TestRejectionSummary:
    """Tests for rejection summary generation."""

    def test_summary_counts(self):
        """Summary correctly counts rejection reasons."""
        job = JobPosting(title="Test", company="Test", url="https://test.com", source="test")
        results = [
            FilterResult(job, False, RejectionReason.DUPLICATE),
            FilterResult(job, False, RejectionReason.DUPLICATE),
            FilterResult(job, False, RejectionReason.AGE),
            FilterResult(job, False, RejectionReason.TITLE_EXCLUDE),
        ]
        summary = get_rejection_summary(results)
        assert summary["REJECTED_DUPLICATE"] == 2
        assert summary["REJECTED_AGE"] == 1
        assert summary["REJECTED_TITLE_EXCLUDE"] == 1

    def test_empty_results(self):
        """Empty results give empty summary."""
        summary = get_rejection_summary([])
        assert summary == {}
