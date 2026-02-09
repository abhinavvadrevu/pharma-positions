"""Discovery orchestrator — runs all scrapers and merges results.

This is the core pipeline:
  1. Instantiate scrapers based on config
  2. Run each scraper (with error isolation)
  3. Log ALL discovered jobs to the discovery log (before any filtering)
  4. Merge and deduplicate results
  5. Output the final job list
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.config import PipelineConfig, ScraperConfig
from src.models import JobPosting
from src.scrapers.base import BaseScraper
from src.scrapers.biospace import BioSpaceScraper
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.attrax import AttraxScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.talentbrew import TalentBrewScraper
from src.scrapers.phenom import PhenomScraper
from src.scrapers.successfactors import SuccessFactorsScraper
from src.storage import init_store, log_discovered_jobs

logger = logging.getLogger(__name__)

# Map scraper_type strings to classes
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "biospace": BioSpaceScraper,
    "greenhouse": GreenhouseScraper,
    "attrax": AttraxScraper,
    "workday": WorkdayScraper,
    "talentbrew": TalentBrewScraper,
    "phenom": PhenomScraper,
    "successfactors": SuccessFactorsScraper,
}


class DiscoveryPipeline:
    """Orchestrates the job discovery process across all configured sources."""

    def __init__(self, config: PipelineConfig, data_dir: str | Path | None = None):
        self.config = config
        self.scrapers: list[BaseScraper] = []

        # Generate a run_id for this pipeline execution (ISO 8601 UTC)
        self.run_id = datetime.now(timezone.utc).isoformat()

        # Initialize the data store (creates data/ and files if missing)
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        init_store(self.data_dir)

        self._build_scrapers()

    def _build_scrapers(self) -> None:
        """Instantiate scrapers for each enabled source in config."""
        for source in self.config.enabled_sources:
            scraper_cls = SCRAPER_REGISTRY.get(source.scraper_type)
            if not scraper_cls:
                logger.warning(
                    "Unknown scraper type '%s' for source '%s' — skipping",
                    source.scraper_type,
                    source.name,
                )
                continue

            try:
                scraper = scraper_cls(source, self.config)
                self.scrapers.append(scraper)
                logger.info("Initialized scraper: %s (%s)", source.name, source.scraper_type)
            except Exception as exc:
                logger.error(
                    "Failed to initialize scraper '%s': %s", source.name, exc
                )

    def run(self) -> list[JobPosting]:
        """Execute all scrapers, merge results, and return deduplicated jobs.

        Each scraper runs in isolation — if one fails, the others continue.

        Per the Storage PRD, every single job from every source is logged
        to discovery_log.jsonl immediately after scraping (before any
        dedup or filtering). This is the raw record of everything seen.
        """
        logger.info("Starting discovery pipeline with %d scrapers (run_id=%s)",
                     len(self.scrapers), self.run_id)

        all_jobs: list[JobPosting] = []
        stats: dict[str, int] = {}

        for scraper in self.scrapers:
            logger.info("Running scraper: %s", scraper.name)
            try:
                jobs = scraper.scrape()

                # Log ALL discovered jobs before any filtering/dedup
                if jobs:
                    log_discovered_jobs(jobs, self.run_id, self.data_dir)
                    logger.info("  → %s: %d jobs found and logged", scraper.name, len(jobs))
                else:
                    logger.info("  → %s: 0 jobs found", scraper.name)

                all_jobs.extend(jobs)
                stats[scraper.name] = len(jobs)
            except Exception as exc:
                logger.error("  → %s: FAILED — %s", scraper.name, exc)
                stats[scraper.name] = 0

        # Deduplicate
        deduped = self._deduplicate(all_jobs)

        # NOTE: Do NOT mark URLs as seen here. URLs should only be marked
        # as seen AFTER they have been evaluated by the LLM (in Step 4 of
        # the pipeline). This prevents the bug where jobs get marked as
        # "seen" but never actually evaluated.

        logger.info(
            "Discovery complete: %d total, %d after dedup",
            len(all_jobs),
            len(deduped),
        )
        self._log_stats(stats)

        return deduped

    def _deduplicate(self, jobs: list[JobPosting]) -> list[JobPosting]:
        """Remove duplicate jobs, preferring company-page versions over aggregator.

        Deduplication uses the URL fingerprint. When the same job appears
        from multiple sources (e.g., BioSpace + the company's own page),
        we prefer the company page version because it typically has a
        more complete description.
        """
        seen: dict[str, JobPosting] = {}

        # Sort so that company-page sources come after aggregator sources.
        # This way, company-page versions overwrite aggregator versions.
        aggregator_sources = {"biospace"}

        def sort_key(job: JobPosting) -> int:
            base_source = job.source.split(":")[0]
            return 0 if base_source in aggregator_sources else 1

        sorted_jobs = sorted(jobs, key=sort_key)

        for job in sorted_jobs:
            fp = job.fingerprint
            if fp in seen:
                existing = seen[fp]
                # Prefer the version with more description text
                if len(job.description) > len(existing.description):
                    seen[fp] = job
            else:
                seen[fp] = job

        return list(seen.values())

    def _log_stats(self, stats: dict[str, int]) -> None:
        """Print a summary of results per scraper."""
        logger.info("=== Discovery Summary ===")
        for name, count in stats.items():
            logger.info("  %s: %d jobs", name, count)

    def save_results(self, jobs: list[JobPosting], output_dir: str | None = None) -> Path:
        """Save results to a timestamped JSON file.

        Returns the path to the output file.
        """
        out_dir = Path(output_dir or self.config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"jobs_{timestamp}.json"

        data = {
            "discovered_at": datetime.utcnow().isoformat(),
            "total_jobs": len(jobs),
            "jobs": [job.to_dict() for job in jobs],
        }

        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("Results saved to %s", out_path)
        return out_path
