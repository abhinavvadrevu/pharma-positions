# PRD: Storage & Deduplication

**Parent:** [High-Level PRD](high-level-prd.md)

---

## Overview

The storage module manages three data files:

1. **Discovery log** (`data/discovery_log.jsonl`) — an append-only log of every single job posting encountered by the pipeline, every run, including duplicates. This is the raw record of everything we've seen.
2. **Matched jobs** (`data/jobs.json`) — a curated list of jobs that the orchestrator determined are a fit. Lightweight, used for notification tracking.
3. **Seen URLs** (`data/seen_urls.json`) — an index of all job URLs ever processed, used for deduplication across runs.

---

## Discovery Log

### Purpose

A complete history of every job posting the pipeline has ever encountered. Every time the fetcher returns a job — whether it's new or a duplicate, whether it matches or not — it gets appended here. This log is never deduplicated or pruned.

### Why keep everything

- **Debugging:** if a job was missed or incorrectly filtered, we can look back at the raw data from any run.
- **Analytics:** over time, we can see how many jobs each company posts, how quickly postings turn over, which sources produce the most results, etc.
- **Reprocessing:** if we change the candidate profile or matching criteria, we can replay the log through the new filters without re-scraping.

### File: `data/discovery_log.jsonl`

Uses JSON Lines format (one JSON object per line). This makes appending cheap — just write a line, no need to read/parse the whole file.

**Format:**
```jsonl
{"run_id": "2026-02-06T08:00:00Z", "scraped_at": "2026-02-06T00:00:03-08:00", "title": "Senior Scientist, Drug Product", "company": "BridgeBio", "url": "https://...", "location": "San Francisco, CA", "department": "Manufacturing", "date_posted": "2026-02-01", "source": "greenhouse:bridgebio", "description_snippet": "Develop and optimize lyophilized..."}
{"run_id": "2026-02-06T08:00:00Z", "scraped_at": "2026-02-06T00:00:07-08:00", "title": "QC Analyst", "company": "Amgen", "url": "https://...", "location": "Thousand Oaks, CA", "department": "Quality", "date_posted": "2026-02-03", "source": "talentbrew:amgen", "description_snippet": "Perform routine quality control testing..."}
```

### Fields per entry

| Field | Type | Description |
|---|---|---|
| `run_id` | string | ISO 8601 timestamp identifying which pipeline run this belongs to |
| `scraped_at` | string | Exact time this job was scraped, in Pacific Time (ISO 8601 with `-08:00` or `-07:00` offset) |
| `title` | string | Job title |
| `company` | string | Company name |
| `url` | string | Direct link to the posting |
| `location` | string | Location string |
| `department` | string | Department if available |
| `date_posted` | string or null | When the job was posted |
| `source` | string | Which scraper found it |
| `description_snippet` | string | First ~200 characters of description (enough for debugging, not the full text) |

### Write pattern

The discovery log is append-only. After the fetcher returns results for each source, every job is appended as a line. No reads, no dedup, no filtering — just append.

---

## Matched Jobs

### Purpose

The curated list of jobs the orchestrator decided are a fit. This is the store the notifier reads from to compose email digests.

### File: `data/jobs.json`

**Format:** A JSON array of match records:

```json
[
  {
    "id": "a1b2c3d4-...",
    "company": "BridgeBio",
    "title": "Senior Scientist, Drug Product",
    "url": "https://job-boards.greenhouse.io/bridgebio/jobs/...",
    "location": "San Francisco, CA",
    "is_bay_area": true,
    "department": "Manufacturing",
    "date_posted": "2026-02-01",
    "date_found": "2026-02-06T08:00:00Z",
    "source": "greenhouse:bridgebio",
    "notified": false,
    "notified_at": null
  },
  ...
]
```

### Fields

| Field | Type | Source | Description |
|---|---|---|---|
| `id` | string | Generated | UUID, created at save time |
| `company` | string | Discovery | Company name |
| `title` | string | Discovery | Job title |
| `url` | string | Discovery | Direct link to posting |
| `location` | string | Discovery | Location string |
| `is_bay_area` | bool | LLM Evaluation | Whether the job is located in the SF Bay Area (see Bay Area definition below) |
| `department` | string | Discovery | Department if available |
| `date_posted` | string or null | Discovery | When the job was posted |
| `date_found` | string | Generated | When our pipeline found it |
| `source` | string | Discovery | Which scraper found it |
| `notified` | bool | Notification | Has this been emailed? |
| `notified_at` | string or null | Notification | When it was emailed |

### Bay Area Definition

The `is_bay_area` field is `true` if the job location is in the San Francisco Bay Area, which includes:
- San Francisco, South San Francisco, Daly City, Brisbane
- Peninsula: San Mateo, Redwood City, Palo Alto, Menlo Park, Foster City, San Carlos
- South Bay: San Jose, Sunnyvale, Santa Clara, Mountain View, Cupertino, Milpitas, Fremont
- East Bay: Oakland, Berkeley, Emeryville, Alameda, Hayward, Union City, Pleasanton, Dublin
- North Bay: San Rafael, Novato, Mill Valley

Remote jobs or jobs with unspecified locations should be marked `is_bay_area: false`.

---

## Seen URLs (Deduplication)

### Purpose

Tracks which job URLs we've already processed so we don't re-evaluate the same posting across runs. Checked by the cheap filters in the matching module before any LLM evaluation happens.

### File: `data/seen_urls.json`

**Format:**
```json
{
  "https://job-boards.greenhouse.io/bridgebio/jobs/5025425007": "2026-02-06T08:00:00Z",
  "https://www.biospace.com/job/3026634/...": "2026-02-06T08:00:00Z"
}
```

Each key is a normalized job URL. The value is the ISO 8601 timestamp of when we first saw it.

### When dedup happens

```
Discovery → raw jobs
    ↓
Log ALL jobs to discovery_log.jsonl (before any filtering)
    ↓
Cheap filters check URLs against seen_urls.json → skip known jobs
    ↓
Only new jobs go to LLM evaluation
    ↓
After evaluation, ALL new URLs (matched or not) are added to seen_urls.json
```

This means:
- Every job ever encountered gets logged (discovery log), regardless of dedup status.
- A job that doesn't match still gets added to seen_urls, so we don't re-evaluate it next run.

### URL normalization

Before comparing, normalize URLs to avoid false negatives:
- Strip trailing slashes
- Strip common tracking parameters (`utm_*`, `source`, `ref`)
- Lowercase the hostname

---

## Summary of Data Files

| File | Format | Write Pattern | Grows? | Purpose |
|---|---|---|---|---|
| `data/discovery_log.jsonl` | JSON Lines | Append-only, every run | Yes, unbounded | Raw record of everything seen |
| `data/jobs.json` | JSON array | Read-modify-write | Slowly (only matches) | Qualified jobs + notification tracking |
| `data/seen_urls.json` | JSON object | Read-modify-write | Yes, one entry per unique URL | Deduplication index |

---

## File Safety

### Atomic writes

Every write to `jobs.json` or `seen_urls.json` follows this pattern:

1. Write to a temp file (`jobs.json.tmp`) in the same directory
2. `fsync` the temp file
3. Rename temp to target (atomic on POSIX)

This prevents corruption if the process crashes mid-write.

The discovery log (`discovery_log.jsonl`) is append-only, so it just opens the file in append mode and writes lines. A partial last line from a crash is acceptable — the next read can skip malformed trailing lines.

### Backups

Before each write to `jobs.json` or `seen_urls.json`, copy the current file to `{filename}.bak`. If the primary file is corrupted (fails JSON parse), restore from `.bak` automatically.

No backups needed for the discovery log since it's append-only and a partial write only affects the last line.

---

## Interface

```python
def init_store(data_dir: str = "data") -> None:
    """
    Ensure data directory and files exist.
    Creates jobs.json ([]), seen_urls.json ({}), and discovery_log.jsonl if missing.
    Safe to call multiple times.
    """

# ── Discovery Log ──────────────────────────────────

def log_discovered_jobs(jobs: list[RawJobPosting], run_id: str, data_dir: str = "data") -> None:
    """Append all discovered jobs to discovery_log.jsonl. Called before any filtering."""

# ── Deduplication ──────────────────────────────────

def is_seen(url: str, data_dir: str = "data") -> bool:
    """Check if a URL has been processed before."""

def load_seen_urls(data_dir: str = "data") -> set[str]:
    """Load the full set of seen URLs into memory (for batch filtering)."""

def mark_seen(urls: list[str], data_dir: str = "data") -> None:
    """Add URLs to seen_urls.json with current timestamp."""

# ── Matched Jobs ───────────────────────────────────

def save_matched_jobs(jobs: list[dict], data_dir: str = "data") -> None:
    """Append matched jobs to jobs.json."""

def get_unnotified_matches(data_dir: str = "data") -> list[dict]:
    """Return matched jobs where notified == False."""

def mark_jobs_notified(job_ids: list[str], data_dir: str = "data") -> None:
    """Set notified=True and notified_at=now for the given job IDs."""

def get_all_matches(data_dir: str = "data") -> list[dict]:
    """Return all matched jobs (for review)."""
```

---

## Pipeline Integration

```
1. Discovery fetches raw jobs from all sources
2. store.log_discovered_jobs(raw_jobs, run_id)     ← log everything first
3. Cheap filters check against store.load_seen_urls() → only new jobs
4. Cheap filters apply age + title filters → candidate jobs
5. Orchestrator evaluates candidate jobs → matched jobs
6. store.save_matched_jobs(matched_jobs)
7. store.mark_seen(all_new_job_urls)                ← includes non-matches
8. Notifier reads store.get_unnotified_matches()
9. After email sent: store.mark_jobs_notified(job_ids)
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `data/` directory missing | `init_store()` creates it |
| `jobs.json` missing | `init_store()` creates empty `[]` |
| `jobs.json` corrupted | Restore from `.bak`; if `.bak` also bad, start fresh with `[]` and log error |
| `seen_urls.json` corrupted | Same as above but with `{}` |
| `discovery_log.jsonl` corrupted last line | Ignore the partial line; append normally on next write |
| Disk full | Catch `OSError`, log, raise to pipeline |
