"""Tests for the discovery pipeline orchestrator."""

from src.config import PipelineConfig, ScraperConfig
from src.discovery import DiscoveryPipeline
from src.models import JobPosting


def test_deduplication_prefers_company_page():
    """When the same URL appears from both BioSpace and a company page,
    the company page version should win."""
    config = PipelineConfig(sources=[])
    pipeline = DiscoveryPipeline(config)

    biospace_job = JobPosting(
        title="Scientist",
        company="BridgeBio",
        url="https://boards.greenhouse.io/bridgebio/jobs/123",
        source="biospace",
        description="Short snippet",
    )
    greenhouse_job = JobPosting(
        title="Scientist",
        company="BridgeBio",
        url="https://boards.greenhouse.io/bridgebio/jobs/123",
        source="greenhouse:bridgebio",
        description="Full detailed description of the role including responsibilities...",
    )

    deduped = pipeline._deduplicate([biospace_job, greenhouse_job])
    assert len(deduped) == 1
    assert deduped[0].source == "greenhouse:bridgebio"
    assert "Full detailed" in deduped[0].description


def test_deduplication_keeps_unique_jobs():
    """Different URLs should not be deduplicated."""
    config = PipelineConfig(sources=[])
    pipeline = DiscoveryPipeline(config)

    job1 = JobPosting(
        title="Scientist", company="A",
        url="https://example.com/job/1", source="test",
    )
    job2 = JobPosting(
        title="Engineer", company="B",
        url="https://example.com/job/2", source="test",
    )

    deduped = pipeline._deduplicate([job1, job2])
    assert len(deduped) == 2


def test_empty_pipeline():
    """Pipeline with no sources should return empty results."""
    config = PipelineConfig(sources=[])
    pipeline = DiscoveryPipeline(config)
    jobs = pipeline.run()
    assert jobs == []
