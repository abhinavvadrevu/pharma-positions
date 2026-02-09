# PRD: Job Matching

**Parent:** [High-Level PRD](high-level-prd.md)

---

## Overview

Once jobs are discovered, we need to decide which ones are worth surfacing. This happens in two stages:

1. **Cheap filters** — fast deterministic checks that run in Python. Eliminates duplicates, stale postings, and obviously irrelevant titles. No LLM involved.
2. **LLM evaluation** — the orchestrator (Claude Code agent) reads each surviving job and decides whether it fits. Binary yes/no — either the job is relevant or it isn't.

The cheap filters are handled by this module. It writes the surviving jobs to a file on disk, which the orchestrator skill then reads and evaluates one by one.

---

## Candidate Profile

The system is configured for the following profile:

**Summary:**
Multidisciplinary scientist responsible for investigating the stability and physicochemical properties of antibody and ADC formulations to support early-stage clinical development and IND submissions. Expertise in liquid and lyophilized biologic formulation and drug product manufacturing processes supporting technology transfer to internal manufacturing sites and CMOs. Leads cross-functional teams and develops junior scientists in a matrixed structure.

**Target titles (any of these indicate a likely fit):**
- Drug Product Scientist
- Formulations Scientist / Lead
- Senior Scientist (formulation / drug product context)
- Scientist II (formulation / drug product context)
- Associate Principal Scientist
- Principal Scientist

**Education:** PhD with roughly 2+ years of industry experience (this is a guideline, not a hard cutoff — many postings list flexible requirements like "PhD with 2+ years or MS with 6+ years" and would still be a fit)

**Key domain terms:** drug product, formulation, biologics, antibody, ADC, lyophilization, stability, IND, CMO, technology transfer, drug substance, biopharmaceutical, parenteral

This profile is stored in `config.yaml` so it can be edited without touching code.

---

## Stage 1: Cheap Filters

Fast deterministic checks that run in Python. No LLM, no API calls. These process hundreds of jobs in under a second.

### Filter 1: Duplicate Check

Check each job URL against `data/seen_urls.json`. If we've already processed this URL in a previous run, skip it.

This is the first filter because it's the cheapest (dictionary lookup) and eliminates the most jobs on repeat runs.

### Filter 2: Age

Discard any job posting older than **2 weeks** (14 days).

Why 2 weeks: postings older than this are likely already filled or deep in the interview process. Surfacing them wastes the user's time. Two weeks is a reasonable window — recent enough to be actionable, long enough that we don't miss jobs posted on a Friday that we first see Monday.

**How to determine posting age:**
- **Best case:** The source provides a `date_posted` field (BioSpace includes this, Greenhouse API returns `updated_at`).
- **Fallback:** If no date is available, include the job. We'd rather surface an undated posting than drop a good match.
- **Edge case:** Some sites show relative dates ("30+ days ago"). Parse what we can; if ambiguous, include the job.

### Filter 3: Title Keywords

Check the job title for signals that it's in the right ballpark. This is deliberately loose — we optimize for recall here, not precision. The LLM will handle the nuanced decisions.

**Include if the title contains any of:**
- `formulation`
- `drug product`
- `scientist` (broad, but catches most relevant titles)
- `principal scientist`
- `CMC`
- `biologics`
- `lyophil` (catches lyophilization, lyophilized, etc.)
- `stability`

**Exclude if the title contains any of:**
- `intern`
- `co-op`
- `entry level`
- `associate scientist` (too junior — distinct from "associate principal scientist")
- `director` or `VP` or `vice president` (too senior)
- `manufacturing operator`
- `QC analyst` / `quality control analyst`

These keyword lists are configurable in `config.yaml`.

### Cheap filter output

Each job is tagged with one of:
- `PASS` — write to candidates file for LLM evaluation
- `REJECTED_DUPLICATE` — already in database
- `REJECTED_AGE` — older than 2 weeks
- `REJECTED_TITLE` — title didn't match include/exclude keywords

Rejection reasons are logged for debugging.

---

## Handoff to the LLM

Jobs that pass cheap filtering are written to a file on disk: `data/candidates.json`. This file contains everything the orchestrator needs to evaluate each job.

**File:** `data/candidates.json`

**Format:**
```json
[
  {
    "title": "Senior Scientist, Drug Product",
    "company": "BridgeBio",
    "url": "https://job-boards.greenhouse.io/bridgebio/jobs/...",
    "location": "San Francisco, CA",
    "department": "Manufacturing",
    "date_posted": "2026-02-01",
    "source": "greenhouse:bridgebio",
    "description": "Full text of the job posting..."
  },
  ...
]
```

This file is overwritten on each run (it's a working file, not a log). The orchestrator skill reads it, evaluates each job, and the results go to `data/jobs.json` via the store module.

### Why a file on disk

The matching module is Python code. The orchestrator is a Claude Code agent. They don't share memory. Writing to a file is the simplest way to pass structured data between them:

- The Python module writes `candidates.json` after cheap filtering.
- The skill's SKILL.md instructs the agent to read `data/candidates.json`.
- The agent iterates through the jobs, evaluating each one.

This is explicit, debuggable (you can inspect the file between runs), and doesn't require any IPC or shared state.

---

## Stage 2: LLM Evaluation

The orchestrator reads `data/candidates.json` and evaluates each job one by one. The decision is binary: **fit** or **not a fit**. No scoring rubric, no numeric scales.

The orchestrator is given the candidate profile and criteria (via the skill's SKILL.md) and asked to optimize for **recall over precision**. It's better to surface a marginal job the user can quickly dismiss than to miss a good one.

### What the LLM is told

The evaluation skill's SKILL.md includes the candidate profile, target titles, education guideline, and key domain terms (all from `config.yaml`). It also includes this guidance:

```
For each job, decide: does this job fit the candidate profile?

Optimize for RECALL, not precision. The user would rather see a few
borderline jobs than miss a good one. If there's a reasonable argument
that the job could be relevant, include it.

A job fits if:
- It involves formulation, drug product development, stability, or
  closely related work in biologics/antibodies/ADCs
- The seniority is roughly in the right range (not entry-level,
  not Director/VP)
- The core responsibilities overlap with the candidate's skills

A job does NOT fit if:
- It's in a completely different domain (small molecules, devices,
  sales, manufacturing operations, QC/QA)
- It's clearly the wrong level (entry-level lab tech, or VP/Director
  running a department)
- The title matched the keyword filter but the actual description
  has nothing to do with formulation or drug product work
```

For each job the LLM decides is a fit, it passes the structured job data to the store module for saving.

---

## Alternatives Considered

### Why not keyword-only matching (no LLM)?

Keyword matching would catch jobs titled "Senior Scientist, Drug Product Formulation" but would miss:
- "Scientist II, Biologics Development" (no "formulation" in title, but the description is all formulation work)
- "CMC Scientist, Antibody Therapeutics" (formulation role described differently)
- Roles where the title is generic but the responsibilities section clearly describes formulation/stability work

The LLM catches these semantic matches that keywords miss.

### Why not a separate LLM API call per job?

The orchestrator is already an LLM. Having it call another LLM to do the reading is unnecessary indirection and adds API cost. The orchestrator reads the job description directly.

### Why not embeddings / vector similarity?

Embeddings lose nuance. A Director-level formulation role would have high similarity to the candidate profile but is not a fit. The LLM can reason about level, domain, and skills together.

---

## Interface

```python
def cheap_filters(
    jobs: list[RawJobPosting],
    seen_urls: set[str],
    config: AppConfig,
) -> tuple[list[RawJobPosting], list[dict]]:
    """
    Apply duplicate check, age filter, and title filter.
    Returns (passed_jobs, rejection_log).
    """

def write_candidates(
    jobs: list[RawJobPosting],
    config: AppConfig,
    data_dir: str = "data",
) -> str:
    """
    Write filtered jobs to data/candidates.json for the orchestrator to read.
    Returns the path to the written file.
    """

def run_matching(
    jobs: list[RawJobPosting],
    seen_urls: set[str],
    config: AppConfig,
) -> tuple[str, list[dict]]:
    """
    Full matching module: cheap filters then write candidates file.
    Returns (candidates_file_path, rejection_log).
    The orchestrator reads the file and evaluates each job.
    """
```

---

## Configuration

All matching parameters live in `config.yaml`:

```yaml
candidate_profile: |
  Multidisciplinary scientist responsible for investigating the stability
  and physicochemical properties of antibody and ADC formulations...

match_criteria:
  max_age_days: 14
  title_include:
    - "formulation"
    - "drug product"
    - "scientist"
    - "principal scientist"
    - "CMC"
    - "biologics"
    - "lyophil"
    - "stability"
  title_exclude:
    - "intern"
    - "co-op"
    - "entry level"
    - "associate scientist"
    - "director"
    - "VP"
    - "vice president"
    - "manufacturing operator"
    - "QC analyst"
    - "quality control analyst"
  target_titles:
    - "Drug Product Scientist"
    - "Formulations Scientist"
    - "Senior Scientist"
    - "Scientist II"
    - "Associate Principal Scientist"
    - "Principal Scientist"
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| No `date_posted` available | Skip the age filter for that job; include it |
| Ambiguous date format | Parse best-effort; include if unparseable |
| Empty job description | Include in candidates file; orchestrator can decide with title/snippet alone |
| `candidates.json` write fails | Log error, raise to pipeline (no point continuing if we can't hand off to LLM) |
