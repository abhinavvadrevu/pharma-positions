"""Tests for configuration loading."""

import tempfile
from pathlib import Path

import yaml

from src.config import load_config, PipelineConfig


def test_load_default_config():
    """Loading the project's config.yaml should work."""
    config = load_config()
    assert isinstance(config, PipelineConfig)
    assert len(config.sources) > 0


def test_load_missing_file():
    """Missing config file returns defaults."""
    config = load_config("/nonexistent/path.yaml")
    assert isinstance(config, PipelineConfig)
    assert len(config.sources) == 0


def test_enabled_sources_filter():
    """Only enabled sources are returned by enabled_sources."""
    config = load_config()
    # Disable the first source
    if config.sources:
        config.sources[0].enabled = False
        enabled = config.enabled_sources
        assert config.sources[0] not in enabled


def test_custom_config():
    """A custom config with one source should parse correctly."""
    data = {
        "output_dir": "test_output",
        "log_level": "DEBUG",
        "sources": [
            {
                "name": "test-greenhouse",
                "scraper_type": "greenhouse",
                "enabled": True,
                "company": "TestCo",
                "params": {"board_token": "testco"},
            }
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        f.flush()
        config = load_config(f.name)

    assert config.output_dir == "test_output"
    assert config.log_level == "DEBUG"
    assert len(config.sources) == 1
    assert config.sources[0].name == "test-greenhouse"
    assert config.sources[0].params["board_token"] == "testco"
