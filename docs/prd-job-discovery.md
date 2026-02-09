# PRD: Job Discovery

**Parent:** [High-Level PRD](high-level-prd.md)

---

## Overview

Job discovery is the first step in the pipeline. We need to find relevant job postings from two types of sources:

1. **BioSpace** — a pharma/biotech-specific job aggregator that covers the industry broadly.
2. **Company career pages** — the careers/jobs section on each target company's own website.

Using both gives us the best coverage. BioSpace casts a wide net and catches postings we might miss (including from companies like Hinge Bio that don't have their own job board), while company career pages are the authoritative source and often have listings before they appear on aggregators.

---

## Job Listing Aggregator Sites

### BioSpace
- **URL:** biospace.com/jobs
- **Scraping difficulty: EASY**
- **Notes:** Pharma/biotech-specific job board. ~2,800 active listings. Highly relevant — almost every listing is in our target industry.
- **Anti-scraping:** Minimal. The job listing page is **server-rendered HTML** — jobs load directly in the page with no JavaScript required. Clean HTML structure with job cards containing title, company, location, salary, and a description snippet. Pagination is simple URL-based (`/jobs/2/`, `/jobs/3/`, etc.). Also offers an **RSS feed** (`/jobsrss/`) which would be the easiest path.
- **Approach:** Simple HTTP GET + BeautifulSoup parsing. The RSS feed is an even simpler option. This is our primary aggregator and first to implement.

---

## Company Career Pages

We will directly check career pages for the following 11 companies. Research into each site reveals they fall into a few distinct platform categories:

### Greenhouse-Based (EASY)

These companies use Greenhouse for their job board, which is the best-case scenario. Greenhouse provides **server-rendered HTML** with structured job data (title, department, location, links) and also exposes a **public JSON API** at `boards-api.greenhouse.io`.

| Company | Job Board URL | Jobs Found | Notes |
|---|---|---|---|
| BridgeBio | job-boards.greenhouse.io/bridgebio | ~72 | Clean HTML, departments and locations in page. Greenhouse API available. |
| Revolution Medicines | boards.greenhouse.io/embed/job_board?for=revolutionmedicines | ~120 | Full job list renders in HTML, organized by department. Also links through revmed.com/careers-list. Greenhouse API available. |

**Approach:** Use the Greenhouse Harvest API (`boards-api.greenhouse.io/v1/boards/{company}/jobs`) to get structured JSON directly. No browser needed, no anti-scraping issues. This is the easiest and most reliable method.

### Attrax-Based (MODERATE)

| Company | Career Page | Jobs Found | Notes |
|---|---|---|---|
| AbbVie | careers.abbvie.com | Many | Uses **Attrax** (Azure-hosted ATS), not Workday. Jobs render in the initial HTML with structured data — title, salary range, location, job ID, and description snippet are all present in the page source. URL-based search: `/en/jobs?q=keyword&options=...` |

**Approach:** HTTP GET + BeautifulSoup. The page appears to render job data server-side. Search is URL-parameterized so we can filter by keyword directly. Moderate difficulty — need to handle pagination and parse the Attrax HTML structure.

### TalentBrew-Based (MODERATE)

| Company | Career Page | Jobs Found | Notes |
|---|---|---|---|
| Amgen | careers.amgen.com | Many | Uses **TalentBrew** (by Radancy/TMP Worldwide). Landing page has a search form. Actual results are at `careers.amgen.com/search-jobs`. Job search may require JS rendering, but the search results URL pattern is predictable. |

**Approach:** May need Playwright if search results are JS-rendered. Alternatively, inspect network requests for an underlying API that the frontend calls.

### Phenom People-Based (MODERATE-HARD)

| Company | Career Page | Jobs Found | Notes |
|---|---|---|---|
| Genentech | gene.com/careers | Unknown | Uses **Phenom People** platform. The careers page is a marketing landing page; actual job search lives at a separate URL. Phenom sites are typically JavaScript SPAs. |
| Merck | jobs.merck.com | Unknown | Also uses **Phenom People**. Same platform as Genentech. Job search is at `jobs.merck.com/us/en/search-results`. |

**Approach:** Both use Phenom People which is a JS-heavy SPA. Will need Playwright to render. However, Phenom People sites often have an underlying API (look for XHR requests to `api.phenompeople.com` or similar). If we can find the API, we can call it directly and skip the browser.

### Workday-Based (HARD)

| Company | Career Page | Jobs Found | Notes |
|---|---|---|---|
| Gilead | gilead.wd1.myworkdayjobs.com/gileadcareers | ~262 | Direct **Workday** portal. Minimal HTML returned — the page is a JS SPA that fetches job data via internal API calls. Very little useful content in the raw HTML. |
| Bristol Myers Squibb | bristolmyerssquibb.wd5.myworkdayjobs.com/en-US/BMS | Unknown | **Workday** portal. Same architecture as Gilead — JS SPA with minimal server-rendered content. Marketing site at careers.bms.com (WordPress) links here. |

**Approach:** Workday portals are the hardest to scrape. The page is a full JavaScript SPA. However, Workday sites make predictable API calls under the hood (POST to `/wday/cxs/{tenant}/...`). If we can reverse-engineer these API endpoints, we can call them directly for structured JSON. There are open-source examples of Workday scraping that document these endpoints. Since two companies share this platform, one Workday adapter would cover both.

### SuccessFactors-Based (HARD)

| Company | Career Page | Jobs Found | Notes |
|---|---|---|---|
| Novo Nordisk | careers.novonordisk.com | Unknown | Uses **SAP SuccessFactors**. The page returned almost no content — just a search box. All job data is loaded via JavaScript. Internal career site at `career2.successfactors.eu`. |
| Astellas | careers.astellas.com or astellascareers.jobs | Unknown | Appears to use **SuccessFactors** as well. The Workday URL timed out entirely during testing. Multiple career URLs exist which adds confusion. |

**Approach:** SuccessFactors portals are JS-heavy SPAs. Will need Playwright or API reverse-engineering. SuccessFactors has a known API pattern that can sometimes be called directly. Since both companies share this platform, one adapter could cover both.

### No Structured Job Board (SPECIAL CASE)

| Company | Career Page | Jobs Found | Notes |
|---|---|---|---|
| Hinge Bio | hingebio.com | 0 | Very small company (~20-50 employees). **No careers page or job board exists.** The website has no `/careers` route. Hiring inquiries go to info@hingebio.com. |

**Approach:** Cannot scrape what doesn't exist. Options: (1) check BioSpace for Hinge Bio listings, (2) periodically check if they've added a careers page. For now, rely on BioSpace to catch any Hinge Bio postings.

---

## Difficulty Summary

| Company | Platform | Difficulty | Server-Rendered? | API Available? |
|---|---|---|---|---|
| BridgeBio | Greenhouse | Easy | Yes | Yes (public JSON API) |
| Revolution Medicines | Greenhouse | Easy | Yes | Yes (public JSON API) |
| AbbVie | Attrax | Moderate | Yes | No (HTML parsing) |
| Amgen | TalentBrew | Moderate | Partially | Maybe (check XHR) |
| Genentech | Phenom People | Moderate-Hard | No (JS SPA) | Maybe (check XHR) |
| Merck | Phenom People | Moderate-Hard | No (JS SPA) | Maybe (check XHR) |
| Gilead | Workday | Hard | No (JS SPA) | Yes (undocumented) |
| Bristol Myers Squibb | Workday | Hard | No (JS SPA) | Yes (undocumented) |
| Novo Nordisk | SuccessFactors | Hard | No (JS SPA) | Maybe |
| Astellas | SuccessFactors | Hard | No (JS SPA) | Maybe |
| Hinge Bio | None | N/A | N/A | N/A |

---

## Recommended Implementation Order

Based on the research above, we should build scrapers in this order:

1. **BioSpace** (aggregator) — easiest, RSS feed available, covers the whole industry
2. **BridgeBio + Revolution Medicines** (Greenhouse) — public JSON API, trivial to implement, one adapter covers both
3. **AbbVie** (Attrax) — server-rendered HTML, straightforward parsing
4. **Amgen** (TalentBrew) — likely needs some investigation of the search results page
5. **Genentech + Merck** (Phenom People) — need to find underlying API or use Playwright
6. **Gilead + Bristol Myers Squibb** (Workday) — reverse-engineer Workday API, one adapter covers both
7. **Novo Nordisk + Astellas** (SuccessFactors) — reverse-engineer SuccessFactors API, one adapter covers both
8. **Hinge Bio** — rely on aggregator coverage; monitor for a careers page

This order gives us maximum coverage early (BioSpace + 3 company sites in steps 1-3) while deferring the harder JS SPA work.

---

## Discovery Flow

```
1. Fetch jobs from BioSpace:
   - Run the search with configured keywords/filters
   - Collect results (title, company, location, URL)

2. For each company career page:
   - Navigate to the career page or call its API with configured search params
   - Extract job listings (title, location, URL, description)

3. Merge results from both source types
   - Deduplicate by URL
   - If the same job appears on BioSpace and a company page,
     prefer the company page version (more complete description)

4. Pass the merged list to the next pipeline step (matching)
```

---

## What We Capture Per Job

At minimum, every discovered job should have:

- **Title** — the job title as listed
- **Company** — which company posted it
- **URL** — direct link to the full posting
- **Location** — city/state/remote if available
- **Source** — where we found it (e.g., "biospace", "greenhouse:bridgebio", "workday:gilead")
- **Description** — full text if available, or a snippet if we need a second fetch to get the full version

---

## Configuration

Each source is configured in `config.yaml`. The user specifies which aggregator sites and which company pages to check, along with the search terms and filters for each.

This keeps the system flexible — adding a new company or a new aggregator site is just a config change, not a code change (unless the site needs a custom scraper).

---

## Implementation Status

> **Last updated:** 2026-02-07
> **Code location:** `job-discovery/`

### Overall Progress: 7 of 11 sources producing results (969 total jobs)

| Source | Platform | Status | Jobs Found | Notes |
|---|---|---|---|---|
| BioSpace | Aggregator | **Working** | 400 | HTML scraping with pagination. RSS feed is dead (404). Parses `<h3>` job titles, company from logo alt text, location/salary/description from card text. 20 pages x 20 jobs. |
| BridgeBio | Greenhouse | **Working** | 71 | Public JSON API. Reliable. |
| Revolution Medicines | Greenhouse | **Working** | 206 | Same Greenhouse API. Reliable. |
| AbbVie | Attrax | **Working** | 200 | Server-rendered HTML. Structured fields (title, salary, location, function, job ID, description). Pagination via `?page=N`. 20 pages scraped. |
| Amgen | TalentBrew | **Partial** | 12 | First page of server-rendered results only. TalentBrew AJAX pagination requires JavaScript execution — the `/search-jobs/results` endpoint returns empty HTML without browser context. Full 1,223 results need Playwright. |
| Genentech | Phenom People | **Needs Playwright** | 0 | Pure JS SPA (site ID: GENEUS). Page returns template placeholders without JS. Phenom content delivery API requires auth tokens generated client-side. |
| Merck | Phenom People | **Needs Playwright** | 0 | Pure JS SPA (site ID: MERCUS). Same architecture as Genentech. |
| Gilead | Workday | **Working** | 40 | Undocumented Workday API (`POST /wday/cxs/...`). Reliable. |
| Bristol Myers Squibb | Workday | **Working** | 40 | Same Workday API pattern. Reliable. |
| Novo Nordisk | SuccessFactors | **Needs Playwright** | 0 | SuccessFactors NES platform (career2.successfactors.eu). Search results loaded via JS after page load. No accessible JSON API. |
| Astellas | SuccessFactors | **Needs Playwright** | 0 | SuccessFactors NES platform (career8.successfactors.com, company: astellasT5). Same architecture as Novo Nordisk. |

### What's working

- **BioSpace aggregator** — HTML scraping with 20-page pagination. Covers the entire pharma/biotech industry. 400 jobs per run.
- **Greenhouse adapter** — Public JSON API. Covers BridgeBio (71 jobs) and Revolution Medicines (206 jobs).
- **Attrax adapter** — Server-rendered HTML parsing with labeled field extraction. Covers AbbVie (200 jobs, 20 pages).
- **Workday adapter** — Undocumented internal API. Covers Gilead (40 jobs) and BMS (40 jobs).
- **TalentBrew adapter** — First-page HTML parsing. Covers Amgen (12 jobs from server-rendered page).
- **Pipeline infrastructure** — Config loading, CLI, deduplication, timestamped JSON output, error isolation, rate limiting, retries.
- **Test suite** — 14 passing tests.

### What needs Playwright

| Blocker | Affected Sources | Investigation Details |
|---|---|---|
| Phenom People JS SPA | Genentech, Merck | Sites return template placeholders (`${pageStateData...}`, "Lorem Ipsum") without JavaScript. The Phenom content delivery API at `content-us.phenompeople.com` requires client-side auth tokens. No workaround without browser rendering. |
| SuccessFactors NES JS SPA | Novo Nordisk, Astellas | Sites use the SuccessFactors "New External Sites" framework. The HTML shell loads jQuery + search.js, but job data is fetched via AJAX after page load. SuccessFactors OData API requires authentication. |
| TalentBrew AJAX pagination | Amgen (pages 2+) | First page is server-rendered (12 jobs). Subsequent pages load via AJAX endpoint `/search-jobs/results` which returns `{"results":""}` without browser context. Full 1,223 results need Playwright. |
| No career page | Hinge Bio | Not a bug — rely on BioSpace aggregator coverage. |

### Recommended next steps

1. **Add Playwright** — Install `playwright` and create a browser-based scraper base class. This would unlock Genentech, Merck, Novo Nordisk, Astellas, and full Amgen pagination.
2. **Amgen full pagination** — With Playwright, load the search page and click through all result pages to get all 1,223 jobs.
3. **Genentech + Merck** — With Playwright, render the Phenom People SPA and extract job data from the DOM.
4. **Novo Nordisk + Astellas** — With Playwright, render the SuccessFactors NES search and extract results.
