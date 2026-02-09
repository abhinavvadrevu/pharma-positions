# High-Level PRD: Pharma Job Position Tracker

## 1. Problem Statement

Monitoring pharmaceutical company career pages for relevant job openings is a manual, repetitive, and error-prone process. Postings appear and disappear quickly, and manually checking dozens of pages across multiple companies is unsustainable. There is a need for an automated system that continuously monitors target companies, intelligently evaluates job fit using an LLM, and delivers actionable summaries via email.

---

## 2. Goals

1. **Automated Discovery** — Regularly scrape career pages of specified pharma companies and BioSpace for new job postings.
2. **Intelligent Matching** — Apply cheap filters (duplicates, age, title keywords), then have the orchestrator (Claude Code agent) read each remaining job and make a binary fit/not-fit decision, optimizing for recall.
3. **Persistent Storage** — Log every job encountered for debugging/analytics, and save qualifying matches with core details for notification tracking.
4. **Email Notification** — Send a formatted email digest summarizing newly matched positions.
5. **Modularity** — Each concern (fetch, filter, store, notify) lives in its own module/function, independently testable and replaceable.
6. **Skill-Based Orchestration** — The system is designed as a set of Claude Code skills so the LLM agent can run the full pipeline or individual steps on demand.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Orchestrator (Claude Code Agent)           │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐       │
│  │ Fetcher  │→ │ Matcher  │→ │ candidates.json      │       │
│  │ Module   │  │ Module   │  │ (on disk)             │       │
│  │          │  │(cheap    │  └──────────┬───────────┘       │
│  │          │  │ filters) │             ↓                    │
│  └──────────┘  └──────────┘  Orchestrator reads each job    │
│       ↓                      and decides: fit or not fit     │
│  BioSpace +                          ↓                       │
│  company career              ┌────────┐  ┌────────┐         │
│  page scrapers               │  Store  │→ │ Notify │         │
│                              │ Module  │  │ Module │         │
│                              └────────┘  └────────┘         │
│                                   ↓           ↓              │
│                              JSON files   Email via          │
│                              (local)      SMTP               │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. System Modules

Each module has its own detailed PRD linked below.

| Module | Responsibility | Detailed PRD |
|---|---|---|
| **Discovery** | Scrape BioSpace and company career pages for raw job postings | [prd-job-discovery.md](prd-job-discovery.md) |
| **Matching** | Cheap filters (dedup, age, title keywords) + write candidates file for LLM | [prd-job-matching.md](prd-job-matching.md) |
| **Evaluation Skill** | Claude Code skill that reads candidates file and makes fit/not-fit decisions | [prd-evaluation-skill.md](prd-evaluation-skill.md) |
| **Storage** | Discovery log, matched jobs, and seen URL deduplication index | [prd-storage.md](prd-storage.md) |

---

## 5. Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Rich ecosystem for scraping, email |
| HTTP client | `httpx` | Modern async-capable HTTP client |
| HTML parsing | `beautifulsoup4` | Industry standard, robust |
| JS rendering | `playwright` | Handles SPA career pages (Workday, SuccessFactors, etc.) |
| LLM | Claude Code agent (orchestrator) | Evaluates job fit directly — no separate API calls needed |
| Data storage | JSON files + JSON Lines log | Zero setup, human-readable |
| Email | `smtplib` / SMTP | Standard, no external dependencies |
| Config | `pyyaml` | Clean, readable configuration |
| Scheduling | External (cron / launchd) | Keep the tool simple; scheduling is an OS concern |
| Logging | Python `logging` | Standard library, file + console output |

---

## 6. Directory Structure

```
pharma positions/
├── docs/                               # Project documentation
│   ├── high-level-prd.md               # This document
│   ├── prd-job-discovery.md            # Discovery module
│   ├── prd-job-matching.md             # Cheap filters + handoff
│   ├── prd-evaluation-skill.md         # LLM evaluation skill
│   └── prd-storage.md                  # Storage & deduplication
├── config.yaml                         # Company list, candidate profile, match criteria
├── config.example.yaml                 # Template with placeholder values
├── requirements.txt                    # Python dependencies
├── src/
│   ├── __init__.py
│   ├── models.py                       # Dataclasses (RawJobPosting, etc.)
│   ├── config.py                       # Config loading and validation
│   ├── fetcher.py                      # Fetcher dispatcher (routes to adapters)
│   ├── fetchers/                       # Scraper adapters by platform
│   │   ├── __init__.py
│   │   ├── base.py                     # Base adapter interface
│   │   ├── biospace.py                 # BioSpace aggregator
│   │   ├── greenhouse.py              # BridgeBio, Revolution Medicines
│   │   ├── attrax.py                  # AbbVie
│   │   ├── talentbrew.py             # Amgen
│   │   ├── phenom.py                  # Genentech, Merck
│   │   ├── workday.py                 # Gilead, Bristol Myers Squibb
│   │   └── successfactors.py          # Novo Nordisk, Astellas
│   ├── matcher.py                      # Cheap filters + write candidates file
│   ├── store.py                        # Persistence layer
│   └── notifier.py                     # Email composition and sending
├── skills/                             # Claude Code skill definitions
│   ├── run-pipeline/
│   │   └── SKILL.md
│   ├── evaluate-jobs/
│   │   └── SKILL.md
│   └── send-digest/
│       └── SKILL.md
├── data/                               # Runtime data (gitignored except structure)
│   ├── discovery_log.jsonl             # Append-only log of every job encountered
│   ├── candidates.json                 # Working file: jobs for LLM to evaluate
│   ├── jobs.json                       # Matched jobs + notification tracking
│   ├── seen_urls.json                  # Deduplication index
│   └── logs/                           # Pipeline run logs
│       └── .gitkeep
└── tests/
    ├── test_fetcher.py
    ├── test_matcher.py
    └── test_store.py
```

---

## 7. Key Workflows

### 7.1 Full Pipeline Run
```
1. Load config.yaml
2. Fetch jobs from BioSpace and all enabled company career pages
3. Log ALL discovered jobs to data/discovery_log.jsonl
4. Cheap filters (matcher module):
   a. Duplicate check against seen_urls.json
   b. Age filter: discard postings older than 2 weeks
   c. Title keyword filter: include/exclude lists
5. Write surviving jobs to data/candidates.json
6. Evaluation skill reads candidates.json, one job at a time:
   a. Read the job description
   b. Decide: fit or not a fit (binary, optimize for recall)
   c. If fit: save to data/jobs.json
7. Mark all new URLs as seen in seen_urls.json
8. Load un-notified matches from jobs.json
9. If any exist: send email digest
10. Mark notified jobs
11. Log summary
```

### 7.2 Adding a New Company
```
1. User provides company name and careers page URL
2. Skill inspects the page structure (via playwright + LLM)
3. Determines if an existing adapter works or a custom one is needed
4. If custom: generates adapter in src/fetchers/
5. Updates config.yaml with the new company entry
6. Runs a test fetch to validate
```

---

## 8. Error Handling & Resilience

| Scenario | Handling |
|---|---|
| Career page down / timeout | Log warning, skip company, continue pipeline |
| Career page structure changed | Adapter returns empty + logs error |
| Orchestrator can't determine fit | Log the job details, skip, continue |
| Email send failure | Retry once; log error; do NOT mark jobs as notified |
| Corrupt data file | Load from backup (auto-created before each write) |
| Duplicate pipeline run | Dedup via seen_urls.json ensures no duplicates |

---

## 9. Future Enhancements (Out of Scope for V1)

- **Web dashboard** for browsing matched jobs interactively
- **SQLite/PostgreSQL** migration for better querying
- **Salary extraction** and comparison
- **Application tracking** (applied / interviewed / rejected)
- **Slack/Teams notifications** in addition to email
- **RSS feed generation** of matched jobs
- **Automated cover letter drafting** via LLM for high-fit matches
- **Multi-candidate support** (different profiles for different people)
- **LinkedIn, Indeed, Glassdoor** aggregator support (currently excluded due to anti-scraping)

---

## 10. Success Criteria

1. Pipeline runs end-to-end without manual intervention
2. At least 3 pharma company career pages are successfully scraped
3. LLM matching surfaces relevant jobs — the user rarely misses a good posting (recall-focused)
4. Email digest arrives with correct, well-formatted content
5. Running the pipeline twice in succession does not produce duplicate entries or emails
6. Each module can be tested independently with mock data
