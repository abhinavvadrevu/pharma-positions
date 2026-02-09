"""Storage module for the job discovery pipeline.

Manages three data files as specified in the Storage & Deduplication PRD:

1. **Discovery log** (`data/discovery_log.jsonl`)
   - Append-only log of every job posting encountered, every run
   - JSON Lines format (one JSON object per line)
   - Never deduplicated or pruned

2. **Matched jobs** (`data/jobs.json`)
   - Curated list of jobs the orchestrator determined are a fit
   - JSON array, read-modify-write with atomic writes

3. **Seen URLs** (`data/seen_urls.json`)
   - Index of all job URLs ever processed, for cross-run deduplication
   - JSON object {url: first_seen_timestamp}, atomic writes

All writes to jobs.json and seen_urls.json use atomic write pattern:
  1. Write to .tmp file
  2. fsync
  3. Rename to target (atomic on POSIX)

Before each write, a .bak backup is created. If the primary file is
corrupted, it's restored from .bak automatically.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs, urlencode

from src.models import JobPosting

logger = logging.getLogger(__name__)

# Pacific Time offset (standard: -08:00, daylight: -07:00)
# For simplicity we use the current offset; a full solution would use pytz/zoneinfo
_PACIFIC = timezone(timedelta(hours=-8))

# Tracking params to strip during URL normalization
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                    "utm_content", "source", "ref", "src", "trk"}

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── Initialization ─────────────────────────────────────────────────────────

def init_store(data_dir: str | Path = DEFAULT_DATA_DIR) -> None:
    """Ensure data directory and files exist.

    Creates jobs.json ([]), seen_urls.json ({}), and discovery_log.jsonl
    if missing. Safe to call multiple times.
    """
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)

    jobs_path = d / "jobs.json"
    if not jobs_path.exists():
        _atomic_write_json(jobs_path, [])
        logger.info("Created %s", jobs_path)

    seen_path = d / "seen_urls.json"
    if not seen_path.exists():
        _atomic_write_json(seen_path, {})
        logger.info("Created %s", seen_path)

    log_path = d / "discovery_log.jsonl"
    if not log_path.exists():
        log_path.touch()
        logger.info("Created %s", log_path)


# ── Discovery Log ──────────────────────────────────────────────────────────

def log_discovered_jobs(
    jobs: list[JobPosting],
    run_id: str,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> None:
    """Append all discovered jobs to discovery_log.jsonl.

    Called before any filtering. Every job from every source gets logged
    here, including duplicates. This is the raw record of everything seen.

    Each line is a JSON object with fields per the PRD:
      run_id, scraped_at, title, company, url, location, department,
      date_posted, source, description_snippet
    """
    log_path = Path(data_dir) / "discovery_log.jsonl"
    now_pacific = datetime.now(_PACIFIC)

    with open(log_path, "a") as f:
        for job in jobs:
            entry = {
                "run_id": run_id,
                "scraped_at": now_pacific.isoformat(),
                "title": job.title,
                "company": job.company,
                "url": job.url,
                "location": job.location,
                "department": job.department,
                "date_posted": job.posted_date,
                "source": job.source,
                "description_snippet": (job.description or "")[:200],
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.debug("Appended %d entries to discovery log (run_id=%s)", len(jobs), run_id)


# ── Deduplication (Seen URLs) ──────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Normalize a URL for dedup comparison.

    - Strip trailing slashes
    - Lowercase the hostname
    - Strip common tracking parameters (utm_*, source, ref, etc.)
    """
    url = url.strip()
    parsed = urlparse(url)

    # Lowercase hostname
    hostname = parsed.hostname or ""

    # Strip tracking params
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered_params = {
        k: v for k, v in query_params.items()
        if k.lower() not in _TRACKING_PARAMS
    }
    clean_query = urlencode(filtered_params, doseq=True) if filtered_params else ""

    # Rebuild path without trailing slash
    path = parsed.path.rstrip("/") or ""

    # Reconstruct
    scheme = parsed.scheme or "https"
    normalized = f"{scheme}://{hostname}{path}"
    if clean_query:
        normalized += f"?{clean_query}"

    return normalized


def load_seen_urls(data_dir: str | Path = DEFAULT_DATA_DIR) -> dict[str, str]:
    """Load the full set of seen URLs into memory (for batch filtering).

    Returns a dict of {normalized_url: first_seen_timestamp}.
    """
    seen_path = Path(data_dir) / "seen_urls.json"
    return _safe_read_json(seen_path, default={})


def is_seen(url: str, data_dir: str | Path = DEFAULT_DATA_DIR) -> bool:
    """Check if a URL has been processed before."""
    seen = load_seen_urls(data_dir)
    normalized = normalize_url(url)
    return normalized in seen


def mark_seen(urls: list[str], data_dir: str | Path = DEFAULT_DATA_DIR) -> None:
    """Add URLs to seen_urls.json with current timestamp.

    Uses atomic write with backup.
    """
    seen_path = Path(data_dir) / "seen_urls.json"
    seen = _safe_read_json(seen_path, default={})

    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    for url in urls:
        normalized = normalize_url(url)
        if normalized not in seen:
            seen[normalized] = now
            new_count += 1

    _backup_and_write(seen_path, seen)
    logger.info("Marked %d new URLs as seen (total: %d)", new_count, len(seen))


# ── Matched Jobs ───────────────────────────────────────────────────────────

def save_matched_jobs(
    jobs: list[dict],
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> None:
    """Append matched jobs to jobs.json.

    Each job dict should have fields per the PRD: company, title, url,
    location, department, date_posted, source, is_bay_area. This function adds:
    id (UUID), date_found, notified=False, notified_at=None.

    Also writes data.js for the static HTML viewer.
    """
    jobs_path = Path(data_dir) / "jobs.json"
    existing = _safe_read_json(jobs_path, default=[])

    now = datetime.now(timezone.utc).isoformat()
    for job in jobs:
        record = {
            "id": str(uuid.uuid4()),
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "url": job.get("url", ""),
            "location": job.get("location", ""),
            "is_bay_area": job.get("is_bay_area", False),
            "department": job.get("department", ""),
            "date_posted": job.get("date_posted") or job.get("posted_date"),
            "date_found": now,
            "source": job.get("source", ""),
            "notified": False,
            "notified_at": None,
        }
        existing.append(record)

    _backup_and_write(jobs_path, existing)
    _export_data_js(existing, data_dir)
    logger.info("Saved %d matched jobs (total: %d)", len(jobs), len(existing))


def get_unnotified_matches(data_dir: str | Path = DEFAULT_DATA_DIR) -> list[dict]:
    """Return matched jobs where notified == False."""
    jobs_path = Path(data_dir) / "jobs.json"
    all_jobs = _safe_read_json(jobs_path, default=[])
    return [j for j in all_jobs if not j.get("notified", False)]


def mark_jobs_notified(
    job_ids: list[str],
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> None:
    """Set notified=True and notified_at=now for the given job IDs."""
    jobs_path = Path(data_dir) / "jobs.json"
    all_jobs = _safe_read_json(jobs_path, default=[])

    now = datetime.now(timezone.utc).isoformat()
    id_set = set(job_ids)
    updated = 0

    for job in all_jobs:
        if job.get("id") in id_set:
            job["notified"] = True
            job["notified_at"] = now
            updated += 1

    _backup_and_write(jobs_path, all_jobs)
    logger.info("Marked %d jobs as notified", updated)


def get_all_matches(data_dir: str | Path = DEFAULT_DATA_DIR) -> list[dict]:
    """Return all matched jobs (for review)."""
    jobs_path = Path(data_dir) / "jobs.json"
    return _safe_read_json(jobs_path, default=[])


# ── Internal Helpers ───────────────────────────────────────────────────────

def _export_data_js(jobs: list[dict], data_dir: str | Path) -> None:
    """Export jobs to data.js for the static HTML viewer.

    Writes: window.JOBS_DATA = [...];
    """
    data_js_path = Path(data_dir) / "data.js"
    content = "// Auto-generated by job discovery pipeline\n"
    content += f"// Updated: {datetime.now(timezone.utc).isoformat()}\n"
    content += "window.JOBS_DATA = "
    content += json.dumps(jobs, indent=2, ensure_ascii=False)
    content += ";\n"

    with open(data_js_path, "w") as f:
        f.write(content)

    logger.debug("Exported %d jobs to data.js", len(jobs))


def _safe_read_json(path: Path, default: Any = None) -> Any:
    """Read a JSON file, restoring from .bak if corrupted.

    If the primary file can't be parsed, tries .bak. If both fail,
    returns the default value and logs an error.
    """
    if not path.exists():
        return default if default is not None else {}

    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s — trying backup", path, exc)

    # Try .bak
    bak_path = path.with_suffix(path.suffix + ".bak")
    if bak_path.exists():
        try:
            with open(bak_path, "r") as f:
                data = json.load(f)
            logger.info("Restored %s from backup", path)
            # Write the restored data back to the primary file
            _atomic_write_json(path, data)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Backup %s also corrupted: %s", bak_path, exc)

    logger.error("Could not read %s or its backup — using default", path)
    return default if default is not None else {}


def _backup_and_write(path: Path, data: Any) -> None:
    """Create a .bak backup of the current file, then atomically write new data."""
    # Backup current file
    if path.exists():
        bak_path = path.with_suffix(path.suffix + ".bak")
        try:
            import shutil
            shutil.copy2(path, bak_path)
        except OSError as exc:
            logger.warning("Failed to create backup of %s: %s", path, exc)

    _atomic_write_json(path, data)


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON data atomically using temp file + rename.

    1. Write to .tmp file in the same directory
    2. fsync the temp file
    3. Rename temp to target (atomic on POSIX)
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        tmp_path.rename(path)
    except OSError as exc:
        logger.error("Failed to write %s: %s", path, exc)
        # Clean up temp file if it exists
        if tmp_path.exists():
            tmp_path.unlink()
        raise
