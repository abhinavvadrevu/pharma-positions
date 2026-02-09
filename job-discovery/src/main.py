"""Entry point for the job discovery pipeline.

Usage:
    python -m src.main                    # use default config.yaml
    python -m src.main --config my.yaml   # use custom config
    python -m src.main --source biospace  # run a single source
    python -m src.main --dry-run          # validate config without scraping
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.config import load_config
from src.discovery import DiscoveryPipeline


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the pipeline."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pharma Job Discovery Pipeline — find job postings from "
        "BioSpace, company career pages, and other sources."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml (default: config.yaml in project root)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Run only a specific source by name (e.g., 'biospace', 'bridgebio')",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory (default: from config)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Override data directory for discovery log, seen URLs, etc. (default: data/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load config and list sources without actually scraping",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load config
    config = load_config(args.config)
    log_level = "DEBUG" if args.verbose else config.log_level
    setup_logging(log_level)

    logger = logging.getLogger(__name__)
    logger.info("Loaded config with %d sources", len(config.sources))

    # Filter to a single source if requested
    if args.source:
        config.sources = [
            s for s in config.sources
            if s.name.lower() == args.source.lower()
        ]
        if not config.sources:
            logger.error("No source found matching '%s'", args.source)
            sys.exit(1)
        logger.info("Filtered to source: %s", args.source)

    # Dry run — just list what would run
    if args.dry_run:
        logger.info("=== Dry Run ===")
        for src in config.enabled_sources:
            logger.info(
                "  [%s] %s (type=%s, enabled=%s)",
                "ON" if src.enabled else "OFF",
                src.name,
                src.scraper_type,
                src.enabled,
            )
        logger.info("Dry run complete — no scraping performed.")
        return

    # Run the pipeline
    pipeline = DiscoveryPipeline(config, data_dir=args.data_dir)
    jobs = pipeline.run()

    if not jobs:
        logger.warning("No jobs discovered. Check your config and network.")
        return

    # Save results
    output_dir = args.output_dir or config.output_dir
    out_path = pipeline.save_results(jobs, output_dir)
    logger.info("Done! %d jobs saved to %s", len(jobs), out_path)


if __name__ == "__main__":
    main()
