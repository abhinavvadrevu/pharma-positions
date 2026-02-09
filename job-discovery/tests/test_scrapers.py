"""Tests for individual scrapers using mocked HTTP responses."""

import json

import responses

from src.config import ScraperConfig, PipelineConfig
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.workday import WorkdayScraper


# --- Greenhouse Scraper Tests ---

@responses.activate
def test_greenhouse_scraper_parses_api_response():
    """Greenhouse scraper should parse the JSON API correctly."""
    api_url = "https://boards-api.greenhouse.io/v1/boards/testco/jobs"

    mock_data = {
        "jobs": [
            {
                "id": 12345,
                "title": "Senior Scientist",
                "absolute_url": "https://boards.greenhouse.io/testco/jobs/12345",
                "location": {"name": "San Francisco, CA"},
                "departments": [{"name": "Research"}],
                "content": "<p>Join our team as a Senior Scientist.</p>",
                "updated_at": "2026-01-15T10:00:00Z",
            },
            {
                "id": 67890,
                "title": "Research Associate",
                "absolute_url": "https://boards.greenhouse.io/testco/jobs/67890",
                "location": {"name": "Remote"},
                "departments": [],
                "content": "",
                "updated_at": "2026-02-01T10:00:00Z",
            },
        ]
    }

    responses.add(
        responses.GET,
        api_url,
        json=mock_data,
        status=200,
    )

    source = ScraperConfig(
        name="test-greenhouse",
        scraper_type="greenhouse",
        company="TestCo",
        params={"board_token": "testco"},
    )
    pipeline = PipelineConfig()
    scraper = GreenhouseScraper(source, pipeline)
    jobs = scraper.scrape()

    assert len(jobs) == 2
    assert jobs[0].title == "Senior Scientist"
    assert jobs[0].company == "TestCo"
    assert jobs[0].location == "San Francisco, CA"
    assert jobs[0].source == "greenhouse:testco"
    assert jobs[0].department == "Research"
    assert "Senior Scientist" in jobs[0].description
    assert jobs[1].title == "Research Associate"


@responses.activate
def test_greenhouse_scraper_handles_empty_response():
    """Greenhouse scraper should handle an empty jobs list."""
    api_url = "https://boards-api.greenhouse.io/v1/boards/emptyco/jobs"

    responses.add(responses.GET, api_url, json={"jobs": []}, status=200)

    source = ScraperConfig(
        name="test-empty",
        scraper_type="greenhouse",
        company="EmptyCo",
        params={"board_token": "emptyco"},
    )
    pipeline = PipelineConfig()
    scraper = GreenhouseScraper(source, pipeline)
    jobs = scraper.scrape()

    assert jobs == []


# --- Workday Scraper Tests ---

@responses.activate
def test_workday_scraper_parses_api_response():
    """Workday scraper should parse the internal API response."""
    api_url = "https://testco.wd1.myworkdayjobs.com/wday/cxs/testco/careers/jobs"

    mock_data = {
        "total": 2,
        "jobPostings": [
            {
                "title": "Director, Clinical Operations",
                "externalPath": "/job/Director-Clinical-Operations/123",
                "locationsText": "Foster City, CA",
                "postedOn": "2026-01-20",
                "bulletFields": ["Full Time", "R&D"],
            },
            {
                "title": "Medical Writer",
                "externalPath": "/job/Medical-Writer/456",
                "locationsText": "Remote",
                "postedOn": "2026-02-01",
                "bulletFields": ["Full Time"],
            },
        ],
    }

    responses.add(responses.POST, api_url, json=mock_data, status=200)

    source = ScraperConfig(
        name="test-workday",
        scraper_type="workday",
        url="https://testco.wd1.myworkdayjobs.com",
        company="TestCo",
        params={"tenant": "testco", "site": "careers", "max_pages": 1},
    )
    pipeline = PipelineConfig()
    scraper = WorkdayScraper(source, pipeline)
    jobs = scraper.scrape()

    assert len(jobs) == 2
    assert jobs[0].title == "Director, Clinical Operations"
    assert jobs[0].location == "Foster City, CA"
    assert jobs[0].source == "workday:testco"
    assert "/job/Director" in jobs[0].url
    assert jobs[1].title == "Medical Writer"
