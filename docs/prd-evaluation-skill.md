# PRD: Job Evaluation Skill

**Parent:** [High-Level PRD](high-level-prd.md)

---

## Overview

The job evaluation skill is a Claude Code skill that acts as the decision-maker in the pipeline. It reads `data/candidates.json` (written by the matching module after cheap filtering) and evaluates each job one by one. The decision is binary: **fit** or **not a fit**. No numeric scoring.

The skill optimizes for **recall over precision** — it's better to surface a borderline job the user can quickly dismiss than to miss a good one.

---

## How It Works

### Step-by-step flow

```
1. Read data/candidates.json (written by the matching module)

2. Load the candidate profile and criteria from config.yaml

3. For each job in the file, one at a time:
   a. Read the title, company, location, and full description
   b. Decide: fit or not a fit
   c. If fit: save to the store (data/jobs.json)
   d. If not a fit: skip, move on

4. Mark all processed URLs as seen in seen_urls.json

5. Report a summary: X jobs evaluated, Y accepted, Z rejected
```

### Why one at a time

The skill evaluates jobs sequentially. Each job gets its own focused read. This matters because:

- Job descriptions are long (500-2000 words). Batching would dilute attention.
- If something goes wrong with one job (garbled description, unreadable page), the skill moves on without affecting others.
- Sequential evaluation is easy to follow in the logs.

---

## What the Skill Reads

### Input file: `data/candidates.json`

Written by the matching module after cheap filters. Contains one entry per job with:

- Job title, company, location, department
- Date posted (if available)
- Source (which scraper found it)
- Full job description text

### From config.yaml

The candidate profile, target titles, education guideline, and key domain terms. Loaded once at the start.

The skill does not fetch anything from the internet. All text has already been collected by earlier pipeline stages.

---

## How the Skill Decides

The decision is binary. For each job, the skill asks: **does this job fit the candidate profile?**

### What makes a job a fit

- It involves formulation, drug product development, stability, or closely related work in biologics / antibodies / ADCs.
- The seniority is roughly in the right range — not entry-level, not Director/VP.
- The core responsibilities overlap with the candidate's skills (stability studies, lyophilization, tech transfer, CMO management, cross-functional leadership).

### What makes a job NOT a fit

- It's in a completely different domain (small molecules, devices, sales, manufacturing operations, QC/QA testing).
- It's clearly the wrong level (entry-level lab tech, or VP/Director running a department).
- The title matched the keyword filter but the actual description has nothing to do with formulation or drug product work.

### Recall over precision

The skill errs on the side of inclusion. If there's a reasonable argument the job could be relevant, include it. The user would rather quickly dismiss a few borderline jobs than miss a good one.

This means:
- A job with a vague description that *might* be formulation-related → **include it**
- A job that's slightly more senior than ideal but in the right domain → **include it**
- A job that says "MS required" but describes exactly the right work → **include it**
- A job in the right domain but clearly too senior (VP) or too junior (lab tech) → **reject it**
- A job that's just in a completely different field → **reject it**

---

## Skill Definition

The skill lives at `skills/evaluate-jobs/SKILL.md`.

### Trigger

1. **As part of the pipeline** — called after the matching module writes `data/candidates.json`.
2. **Standalone** — the user says "evaluate the candidate jobs" or similar.

### SKILL.md contents

The SKILL.md instructs the agent to:

1. Read `data/candidates.json`.
2. Load the candidate profile from `config.yaml`.
3. For each job:
   - Read the description.
   - Decide fit or not a fit.
   - If fit, save to the store.
4. Mark all URLs as seen.
5. Report results.

It includes the candidate profile and this guidance:

```
CANDIDATE PROFILE:
Multidisciplinary scientist responsible for investigating the stability
and physicochemical properties of antibody and ADC formulations to support
early-stage clinical development and IND submissions. Expertise in liquid
and lyophilized biologic formulation and drug product manufacturing
processes supporting technology transfer to internal manufacturing sites
and CMOs. Leads cross-functional teams and develops junior scientists in
a matrixed structure.

TARGET TITLES:
Drug Product Scientist, Formulations Scientist, Senior Scientist,
Scientist II, Associate Principal Scientist, Principal Scientist

EDUCATION GUIDELINE: PhD with roughly 2+ years of industry experience.
This is approximate — many postings list flexible requirements and
should still be considered.

DECISION:
For each job, decide: fit or not a fit. That's it.

Optimize for RECALL, not precision. The user would rather see a few
borderline jobs than miss a good one. If there's a reasonable argument
that the job could be relevant, include it.
```

---

## Edge Cases

| Scenario | How the skill handles it |
|---|---|
| Job description is very short | Decide based on what's available; when in doubt, include it |
| Job description is in a different language | Skip it |
| Job title says "Scientist" but description is clearly sales/BD | Reject — the cheap filter let it through but the description doesn't fit |
| Job seems perfect but is at a company not on the tracked list (found via BioSpace) | Include it — company doesn't matter, fit does |
| Job says "MS required" but describes exactly the right formulation work | Include it — education listings are guidelines |
| `candidates.json` is empty | Report "0 candidates to evaluate" and finish |

---

## Pipeline Integration

```
Discovery → raw jobs (all sources)
    ↓
Log all to discovery_log.jsonl
    ↓
CHEAP FILTERS (matching module, Python):
    Duplicate check → Age filter → Title keywords
    ↓
Write data/candidates.json
    ↓
LLM EVALUATION (this skill):
    Read candidates.json
    For each job: fit or not a fit
    ↓
Fits saved to data/jobs.json
All URLs marked seen in seen_urls.json
    ↓
Notification step picks up unnotified matches
```
