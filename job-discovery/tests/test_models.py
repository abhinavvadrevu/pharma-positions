"""Tests for the JobPosting data model."""

from src.models import JobPosting


def test_job_posting_creation():
    job = JobPosting(
        title="Senior Scientist",
        company="BridgeBio",
        url="https://boards.greenhouse.io/bridgebio/jobs/12345",
        source="greenhouse:bridgebio",
        location="San Francisco, CA",
    )
    assert job.title == "Senior Scientist"
    assert job.company == "BridgeBio"
    assert job.source == "greenhouse:bridgebio"


def test_fingerprint_is_stable():
    job1 = JobPosting(
        title="Scientist",
        company="Test",
        url="https://example.com/jobs/123",
        source="test",
    )
    job2 = JobPosting(
        title="Different Title",
        company="Different Company",
        url="https://example.com/jobs/123",
        source="different",
    )
    # Same URL → same fingerprint
    assert job1.fingerprint == job2.fingerprint


def test_fingerprint_normalizes_url():
    job1 = JobPosting(
        title="A", company="B",
        url="https://example.com/jobs/123/",
        source="test",
    )
    job2 = JobPosting(
        title="A", company="B",
        url="https://EXAMPLE.COM/jobs/123",
        source="test",
    )
    # Trailing slash and case shouldn't matter
    assert job1.fingerprint == job2.fingerprint


def test_to_dict():
    job = JobPosting(
        title="Analyst",
        company="Merck",
        url="https://jobs.merck.com/12345",
        source="phenom:merck",
    )
    d = job.to_dict()
    assert d["title"] == "Analyst"
    assert "fingerprint" in d
    assert isinstance(d["fingerprint"], str)
