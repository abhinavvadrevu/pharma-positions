---
name: run-pipeline
description: "**[REQUIRED]** Use for ALL pharma job discovery tasks. Runs the COMPLETE pipeline end-to-end: scraping → filtering → LLM evaluation → saving to jobs.json. MUST complete all steps. Triggers: run pipeline, find jobs, discover jobs, scrape jobs, job search, check for jobs, pharma jobs, job discovery, run the pipeline, execute pipeline, search for jobs."
---

# Run Pipeline Skill

**CRITICAL: You MUST complete ALL steps below in a single execution. Do NOT stop after discovery.**

## Step 1: Discovery (Scrape Jobs)

```bash
cd "/Users/avadrevu/workspace/pharma positions/job-discovery"
.venv/bin/python -m src.main --output-dir data
```

Note the output file path (e.g., `data/jobs_TIMESTAMP.json`).

## Step 2: Apply Cheap Filters

Run this Python script to filter and prepare candidates:

```bash
cd "/Users/avadrevu/workspace/pharma positions/job-discovery"
.venv/bin/python -c "
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

data_dir = Path('data')

# Find latest discovery file
discovery_files = sorted(data_dir.glob('jobs_*.json'), reverse=True)
if not discovery_files:
    print('ERROR: No discovery files found')
    sys.exit(1)

latest = discovery_files[0]
print(f'Loading {latest.name}')
with open(latest) as f:
    raw_jobs = json.load(f)
print(f'Found {len(raw_jobs)} raw jobs')

# Import pipeline modules
from src.config import load_config
from src.models import JobPosting
from src.storage import load_seen_urls, log_discovered_jobs
from src.matcher import run_matching, get_rejection_summary

config = load_config()
run_id = datetime.now(timezone.utc).isoformat()

# Convert to JobPosting objects
jobs = [
    JobPosting(
        title=j.get('title', ''),
        company=j.get('company', ''),
        url=j.get('url', ''),
        source=j.get('source', ''),
        location=j.get('location', ''),
        description=j.get('description', ''),
        department=j.get('department', ''),
        posted_date=j.get('posted_date') or j.get('date_posted'),
    )
    for j in raw_jobs
]

# Log all discovered jobs
log_discovered_jobs(jobs, run_id, data_dir)
print(f'Logged {len(jobs)} jobs to discovery_log.jsonl')

# Apply cheap filters
seen_urls = set(load_seen_urls(data_dir).keys())
candidates_path, rejections = run_matching(jobs, seen_urls, config)

# Report
from src.matcher import load_candidates
candidates = load_candidates(data_dir)
summary = get_rejection_summary(rejections)
print(f'\\nCheap filter results:')
print(f'  Candidates for LLM evaluation: {len(candidates)}')
for reason, count in summary.items():
    print(f'  {reason}: {count}')
"
```

## Step 3: LLM Evaluation (YOU DO THIS)

Read `data/candidates.json` and evaluate EACH job against this profile:

### Candidate Profile

```
ROLE: Multidisciplinary scientist investigating stability and physicochemical
properties of antibody and ADC formulations. Supports early-stage clinical
development and IND submissions. Expertise in liquid and lyophilized biologic
formulation and drug product manufacturing. Technology transfer to CMOs.

TARGET TITLES: Drug Product Scientist, Formulations Scientist, Senior Scientist,
Scientist II, Associate Principal Scientist, Principal Scientist

EDUCATION: PhD with ~2+ years industry experience (flexible)
```

### Decision Rules (RECALL over precision — include borderline cases)

✅ **FIT** if:
- Involves formulation, drug product, stability in biologics/antibodies/ADCs
- Mid-level seniority (not entry-level lab tech, not Director/VP)
- Core work: stability studies, lyophilization, tech transfer, CMO collaboration

❌ **NOT A FIT** if:
- Different domain: small molecules only, devices, sales, QC/QA testing only
- Wrong level: lab technician or VP/Director/Head
- Title matched but actual work is unrelated to formulation

### Bay Area Classification

For EACH job you evaluate, also determine `is_bay_area` (true/false):

**Bay Area = TRUE** if the location is in the SF Bay Area:
- San Francisco, South San Francisco, Daly City, Brisbane
- Peninsula: San Mateo, Redwood City, Palo Alto, Menlo Park, Foster City, San Carlos
- South Bay: San Jose, Sunnyvale, Santa Clara, Mountain View, Cupertino, Milpitas, Fremont
- East Bay: Oakland, Berkeley, Emeryville, Alameda, Hayward, Union City, Pleasanton, Dublin
- North Bay: San Rafael, Novato, Mill Valley

**Bay Area = FALSE** if:
- Location is elsewhere (e.g., "Boston, MA", "San Diego, CA", "Remote")
- Location is unspecified or unclear

### Evaluation Process

1. Read candidates.json
2. For each job, read title + company + location + description
3. Decide: fit or not-fit
4. Determine: is_bay_area true or false
5. Collect all fits into a list with their is_bay_area values

## Step 4: Save Results

After evaluating, save matches. For each matched job, include `is_bay_area`:

```bash
cd "/Users/avadrevu/workspace/pharma positions/job-discovery"
.venv/bin/python -c "
import json
from pathlib import Path

data_dir = Path('data')

# Load candidates that were evaluated
with open(data_dir / 'candidates.json') as f:
    candidates = json.load(f)

# YOU MUST REPLACE THIS with the actual matched jobs
# Each entry needs: all original fields PLUS is_bay_area
# Example:
# matched_jobs = [
#     {**candidates[0], 'is_bay_area': True},
#     {**candidates[2], 'is_bay_area': False},
#     {**candidates[5], 'is_bay_area': True},
# ]
matched_jobs = []  # <-- FILL THIS IN

from src.storage import save_matched_jobs, mark_seen

if matched_jobs:
    save_matched_jobs(matched_jobs, data_dir)
    print(f'Saved {len(matched_jobs)} matched jobs to jobs.json and data.js')
else:
    print('No matching jobs this run')

# Mark ALL candidates as seen
all_urls = [c['url'] for c in candidates]
mark_seen(all_urls, data_dir)
print(f'Marked {len(all_urls)} URLs as seen')

from src.storage import get_all_matches
total = len(get_all_matches(data_dir))
print(f'Total matches in jobs.json: {total}')
"
```

## Summary

When user says "run the job discovery pipeline":

1. **Run** Step 1 (discovery script)
2. **Run** Step 2 (cheap filters script)  
3. **Do** Step 3 (read candidates.json, evaluate each job yourself, classify Bay Area)
4. **Run** Step 4 (save script with your matched jobs including is_bay_area)
5. **Report** final counts

**DO NOT stop after Step 1 or Step 2. The pipeline is not complete until jobs.json is updated.**
