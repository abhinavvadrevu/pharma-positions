---
name: run-pipeline
description: "**[REQUIRED]** Use for ALL pharma job discovery tasks. Runs the COMPLETE pipeline end-to-end: scraping → filtering → LLM evaluation → saving → notifications. MUST complete all steps. Triggers: run pipeline, find jobs, discover jobs, scrape jobs, job search, check for jobs, pharma jobs, job discovery, run the pipeline, execute pipeline, search for jobs."
---

# Run Pipeline Skill

**CRITICAL: You MUST complete ALL steps below in a single execution. Do NOT stop after discovery.**

## Step 1: Discovery (Scrape Jobs)

```bash
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
.venv/bin/python -m src.main --output-dir data
```

Note the output file path (e.g., `data/jobs_TIMESTAMP.json`).

## Step 2: Apply Cheap Filters

Run this Python script to filter and prepare candidates:

```bash
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
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
# Discovery output is a dict: {"discovered_at": "...", "total_jobs": N, "jobs": [...]}
if isinstance(raw_jobs, dict):
    raw_jobs = raw_jobs['jobs']
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

## Step 3: LLM Evaluation with Incremental Saving

**IMPORTANT: This step saves progress after EACH candidate. If interrupted, it will resume from where it left off.**

### Step 3a: Get Remaining Candidates

First, run this script to get candidates that haven't been evaluated yet:

```bash
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
.venv/bin/python -c "
import json
from pathlib import Path
from src.storage import load_seen_urls, normalize_url

data_dir = Path('data')

# Load all candidates
with open(data_dir / 'candidates.json') as f:
    all_candidates = json.load(f)

# Filter out already-evaluated candidates
seen_urls = set(load_seen_urls(data_dir).keys())
remaining = []
for i, c in enumerate(all_candidates):
    if normalize_url(c['url']) not in seen_urls:
        remaining.append({'index': i, **c})

print(f'Total candidates: {len(all_candidates)}')
print(f'Already evaluated: {len(all_candidates) - len(remaining)}')
print(f'Remaining to evaluate: {len(remaining)}')

# Save remaining candidates for evaluation
with open(data_dir / 'remaining_candidates.json', 'w') as f:
    json.dump(remaining, f, indent=2)

if not remaining:
    print('\\n✅ All candidates already evaluated!')
"
```

If there are remaining candidates, proceed to Step 3b. If all are evaluated, skip to Step 5.

### Step 3b: Evaluate Each Candidate (ONE AT A TIME)

Read `data/remaining_candidates.json` and evaluate candidates **one at a time**.

⚠️ **CRITICAL: DO NOT BATCH OR PARALLELIZE EVALUATIONS** ⚠️
- Evaluate exactly ONE candidate per response
- Run the save script ONCE per candidate
- Do NOT create scripts that loop through multiple candidates
- Do NOT run multiple save scripts in parallel
- This ensures progress is saved and visible after each candidate

**For EACH candidate**, you must:
1. Read the job details and description
2. Make your FIT / NOT A FIT decision
3. Determine is_bay_area (true/false)
4. **Immediately run the save script below** (with that ONE candidate's values)
5. Wait for the script to complete and show output
6. Then move to the next candidate

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

**Bay Area = TRUE** if location is in SF Bay Area:
- San Francisco, South San Francisco, Daly City, Brisbane
- Peninsula: San Mateo, Redwood City, Palo Alto, Menlo Park, Foster City, San Carlos
- South Bay: San Jose, Sunnyvale, Santa Clara, Mountain View, Cupertino, Milpitas, Fremont
- East Bay: Oakland, Berkeley, Emeryville, Alameda, Hayward, Union City, Pleasanton, Dublin
- North Bay: San Rafael, Novato, Mill Valley

**Bay Area = FALSE** if: elsewhere, remote, or unspecified

### Step 3c: Save Script (RUN AFTER EACH EVALUATION)

After evaluating EACH candidate, immediately run this script to save progress:

```bash
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
.venv/bin/python -c "
import json
from pathlib import Path
from src.storage import save_matched_jobs, mark_seen, get_all_matches

data_dir = Path('data')

# Load the candidate being evaluated
with open(data_dir / 'remaining_candidates.json') as f:
    remaining = json.load(f)

# === FILL IN THESE VALUES ===
candidate_index = 0  # <-- Index in remaining_candidates.json (0, 1, 2, ...)
is_fit = False       # <-- True if FIT, False if NOT A FIT
is_bay_area = False  # <-- True if Bay Area, False otherwise
# ============================

candidate = remaining[candidate_index]
total_remaining = len(remaining)

# Save if it's a fit
if is_fit:
    job_with_bay_area = {**candidate, 'is_bay_area': is_bay_area}
    del job_with_bay_area['index']  # Remove the index field
    save_matched_jobs([job_with_bay_area], data_dir)
    bay_tag = ' (Bay Area)' if is_bay_area else ''
    print(f'[{candidate_index + 1}/{total_remaining}] ✅ FIT{bay_tag}: {candidate[\"title\"]} @ {candidate[\"company\"]}')
else:
    print(f'[{candidate_index + 1}/{total_remaining}] ❌ SKIP: {candidate[\"title\"]} @ {candidate[\"company\"]}')

# Mark URL as seen (whether fit or not)
mark_seen([candidate['url']], data_dir)

# Progress summary
total_matches = len(get_all_matches(data_dir))
evaluated = candidate_index + 1
print(f'    Progress: {evaluated}/{total_remaining} evaluated, {total_matches} total matches')
"
```

**Repeat Step 3c for each candidate** in `remaining_candidates.json`, incrementing `candidate_index` each time.

⚠️ **REMINDER: ONE candidate at a time. Do NOT batch. Do NOT parallelize. Do NOT loop in Python.**

### Step 3d: Evaluation Complete

After all candidates are evaluated, run this to confirm:

```bash
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
.venv/bin/python -c "
import json
from pathlib import Path
from src.storage import get_all_matches, load_seen_urls, normalize_url

data_dir = Path('data')

# Check completion
with open(data_dir / 'candidates.json') as f:
    all_candidates = json.load(f)

seen_urls = set(load_seen_urls(data_dir).keys())
remaining = [c for c in all_candidates if normalize_url(c['url']) not in seen_urls]

if remaining:
    print(f'⚠️  {len(remaining)} candidates still need evaluation')
else:
    print('✅ All candidates evaluated!')

# Summary
total_matches = len(get_all_matches(data_dir))
print(f'Total matches in jobs.json: {total_matches}')
"
```

## Step 4: Get New Matches for Notification

Get the list of jobs that were matched in this run (for notification):

```bash
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
.venv/bin/python -c "
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

data_dir = Path('data')

# Get jobs matched in the last hour (this run)
from src.storage import get_all_matches
all_matches = get_all_matches(data_dir)

cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
new_matches = [j for j in all_matches if j.get('date_found', '') >= cutoff]

print(f'New matches this run: {len(new_matches)}')
for j in new_matches:
    bay_tag = ' (Bay Area)' if j.get('is_bay_area') else ''
    print(f'  - {j[\"title\"]} @ {j[\"company\"]}{bay_tag}')

# Save for notification step
with open(data_dir / 'new_matches.json', 'w') as f:
    json.dump(new_matches, f, indent=2)
"
```

## Step 5: Notify (Git Push + Email)

**ONLY run this step if there were new matched jobs in Step 4.**

This step commits and pushes to GitHub, then sends an email notification.

Use the Bash tool with `secret_env` to inject the Resend API key securely:

```bash
# Run with secret_env: {"RESEND_API_KEY": "resend_api_key"}
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
.venv/bin/python -c "
import json
from pathlib import Path
from src.notify import run_notifications

data_dir = Path('data')

# Load new matches from Step 4
with open(data_dir / 'new_matches.json') as f:
    matched_jobs = json.load(f)

if not matched_jobs:
    print('No new matches to notify about')
else:
    results = run_notifications(matched_jobs)
    
    # Report results
    for name, result in results.items():
        status = '✓' if result['success'] else '✗'
        print(f'{status} {name}: {result[\"message\"]}')
"
```

**IMPORTANT:** When running the notification script, you MUST use the `secret_env` parameter in the Bash tool call to inject the API key:

```json
{
  "command": "cd ... && .venv/bin/python -c '...'",
  "secret_env": {"RESEND_API_KEY": "resend_api_key"}
}
```

This securely injects the stored secret without exposing it in the command or logs.

**If the `secret_env` approach fails** (i.e. the key is passed as a literal string rather than the real value), use this fallback:

```bash
cd "/Users/avadrevu/workspace/personal/pharma-positions/job-discovery"
RESEND_API_KEY=$(cat ~/.snowflake/cortex/secrets/resend_api_key.secret) .venv/bin/python -c "..."
```

The secret file is at `~/.snowflake/cortex/secrets/resend_api_key.secret`. This fallback was confirmed working in run ab0818f2 (April 22).

## Summary

When user says "run the job discovery pipeline":

1. **Run** Step 1 (discovery script)
2. **Run** Step 2 (cheap filters script)  
3. **Do** Step 3:
   - 3a: Get remaining candidates (resumes from where you left off)
   - 3b: Read ONE candidate's details
   - 3c: **Run save script for that ONE candidate** → see progress output
   - **Repeat 3b-3c for each remaining candidate** (do NOT batch or parallelize!)
   - 3d: Confirm all evaluated
4. **Run** Step 4 (get new matches for notification)
5. **Run** Step 5 (notify - ONLY if there were matches)
6. **Report** final counts

⚠️ **CRITICAL**: Step 3 must be done ONE CANDIDATE AT A TIME. Each evaluation = one save script call = one progress line. Do NOT write Python loops or batch multiple candidates. This is intentional to prevent timeouts and ensure incremental saving.

**INCREMENTAL SAVING:** Progress is saved after each candidate. If interrupted, re-run the pipeline and it will resume from where it left off.

**DO NOT stop early. The pipeline is not complete until notifications are sent (if there were matches).**
