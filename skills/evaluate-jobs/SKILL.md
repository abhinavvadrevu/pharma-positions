---
name: evaluate-jobs
description: "Evaluate candidate jobs from candidates.json and decide fit/not-fit. Use standalone or after running discovery. Triggers: evaluate jobs, evaluate candidates, check job fit, review candidates."
---

# Evaluate Jobs Skill

Evaluate candidate jobs and decide which ones fit the candidate profile. This skill can run:
- **Standalone** — evaluate existing `data/candidates.json`
- **As part of pipeline** — after discovery and cheap filtering

## Quick Start

```python
import sys
sys.path.insert(0, "/Users/avadrevu/workspace/pharma positions/job-discovery")

from pathlib import Path
from src.matcher import load_candidates
from src.storage import save_matched_jobs, mark_seen

data_dir = Path("/Users/avadrevu/workspace/pharma positions/job-discovery/data")
candidates = load_candidates(data_dir)
print(f"{len(candidates)} candidates to evaluate")
```

## Candidate Profile

```
ROLE: Multidisciplinary scientist investigating stability and physicochemical
properties of antibody and ADC formulations. Supports early-stage clinical
development and IND submissions. Expertise in liquid and lyophilized biologic
formulation and drug product manufacturing. Technology transfer to CMOs.
Leads cross-functional teams.

TARGET TITLES:
- Drug Product Scientist
- Formulations Scientist / Lead
- Senior Scientist (formulation context)
- Scientist II (formulation context)
- Associate Principal Scientist
- Principal Scientist

EDUCATION: PhD with ~2+ years industry experience (flexible guideline)

KEY TERMS: drug product, formulation, biologics, antibody, ADC, lyophilization,
stability, IND, CMO, technology transfer, parenteral
```

## Decision Framework

**OPTIMIZE FOR RECALL** — when in doubt, include the job.

### ✅ Include (FIT) if:

| Criterion | Examples |
|-----------|----------|
| Right domain | Formulation, drug product, stability, biologics, ADCs |
| Right level | Senior Scientist, Scientist II, Principal Scientist |
| Right work | Stability studies, lyophilization, tech transfer, CMO management |
| Borderline but plausible | Vague description that *might* be formulation |
| Slightly senior | Staff Scientist in right domain |
| Flexible education | "MS required" but describes right work |

### ❌ Exclude (NOT A FIT) if:

| Criterion | Examples |
|-----------|----------|
| Wrong domain | Small molecules, devices, sales, manufacturing ops, QC/QA testing |
| Wrong level | Lab tech, Associate Scientist (too junior), VP/Director (too senior) |
| Misleading title | "Scientist" title but description is sales/BD |
| Different language | Non-English job description |

## Evaluation Workflow

### Step 1: Load Candidates

```python
candidates = load_candidates(data_dir)
if not candidates:
    print("No candidates to evaluate. Run discovery first.")
```

### Step 2: Evaluate Each Job

For each candidate, read the FULL description and decide:

```python
matched_jobs = []

for i, job in enumerate(candidates, 1):
    print(f"\n[{i}/{len(candidates)}] {job['title']} @ {job['company']}")
    print(f"Location: {job['location']}")
    print(f"Source: {job['source']}")
    print(f"\nDescription:\n{job['description']}\n")
    
    # === YOUR DECISION ===
    # Read the description above
    # Decide: FIT or NOT A FIT
    # If FIT, add to matched_jobs:
    #   matched_jobs.append(job)
```

### Step 3: Save Results

```python
# Save matches to jobs.json
if matched_jobs:
    save_matched_jobs(matched_jobs, data_dir)
    print(f"\nSaved {len(matched_jobs)} matched jobs")

# Mark ALL URLs as seen (matches AND non-matches)
all_urls = [c["url"] for c in candidates]
mark_seen(all_urls, data_dir)
print(f"Marked {len(all_urls)} URLs as seen")

# Summary
print(f"\n{'='*40}")
print(f"Evaluated: {len(candidates)}")
print(f"Matched: {len(matched_jobs)}")
print(f"Rejected: {len(candidates) - len(matched_jobs)}")
```

## Example Evaluations

### Example 1: FIT ✅

**Title:** Senior Scientist, Drug Product Development  
**Company:** BridgeBio  
**Description:**
> Develop and optimize lyophilized formulations for antibody therapeutics. Conduct stability studies supporting IND submissions. Lead technology transfer to CMO partners.

**Decision:** ✅ FIT
- Domain: biologics, antibody therapeutics ✓
- Work: lyophilized formulations, stability, IND, CMO ✓
- Level: Senior Scientist ✓

---

### Example 2: NOT A FIT ❌

**Title:** Associate Scientist, Quality Control  
**Company:** Amgen  
**Description:**
> Perform routine analytical testing of in-process samples. Execute HPLC and UV-Vis methods. Document results in LIMS.

**Decision:** ❌ NOT A FIT
- Domain: QC testing, not development
- Level: Associate Scientist (too junior)
- Work: Routine testing, not formulation

---

### Example 3: FIT (borderline) ✅

**Title:** Scientist II, Biologics  
**Company:** Gilead  
**Description:**
> Support biologics development programs. Work cross-functionally with manufacturing and quality teams.

**Decision:** ✅ FIT (include due to recall priority)
- Domain: Biologics ✓
- Level: Scientist II ✓
- Description vague but plausibly formulation-related

## Files

| File | Read/Write | Purpose |
|------|------------|---------|
| `data/candidates.json` | Read | Input: jobs to evaluate |
| `data/jobs.json` | Write | Output: matched jobs |
| `data/seen_urls.json` | Write | Mark evaluated URLs |
