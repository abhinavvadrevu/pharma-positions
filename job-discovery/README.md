# Pharma Job Discovery

Automated job discovery pipeline for pharma/biotech positions. Scrapes job postings from BioSpace (industry aggregator) and 10 company career pages across multiple ATS platforms.

## Supported Sources

| Source | Platform | Difficulty | Status |
|---|---|---|---|
| BioSpace | Aggregator (RSS + HTML) | Easy | Working |
| BridgeBio | Greenhouse JSON API | Easy | Working |
| Revolution Medicines | Greenhouse JSON API | Easy | Working |
| AbbVie | Attrax (HTML) | Moderate | Working |
| Amgen | TalentBrew | Moderate | Working |
| Genentech | Phenom People | Moderate-Hard | Working |
| Merck | Phenom People | Moderate-Hard | Working |
| Gilead | Workday API | Hard | Working |
| Bristol Myers Squibb | Workday API | Hard | Working |
| Novo Nordisk | SuccessFactors | Hard | Working |
| Astellas | SuccessFactors | Hard | Working |
| Hinge Bio | None | N/A | Aggregator-only |

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Run the full pipeline (all enabled sources)
python -m src.main

# Run a single source
python -m src.main --source biospace
python -m src.main --source bridgebio
python -m src.main --source gilead

# Dry run — validate config and list sources
python -m src.main --dry-run

# Verbose logging
python -m src.main -v

# Custom config file
python -m src.main --config my-config.yaml

# Custom output directory
python -m src.main --output-dir ./my-output
```

## Configuration

All sources are configured in `config.yaml`. Each source specifies:

- **name** — human-readable label
- **scraper_type** — which scraper class to use
- **enabled** — toggle sources on/off
- **url** — base URL for the career site
- **company** — company name for output
- **keywords** — search keyword filters
- **params** — scraper-specific parameters

To add a new company, add an entry to `config.yaml` with the appropriate `scraper_type`. If the site uses a platform already supported (Greenhouse, Workday, etc.), no code changes are needed.

## Architecture

```
src/
├── main.py              # CLI entry point
├── config.py            # YAML config loader
├── models.py            # JobPosting data model
├── discovery.py         # Pipeline orchestrator (run, merge, dedup)
└── scrapers/
    ├── base.py          # Abstract base (HTTP, rate limiting, retries)
    ├── biospace.py      # RSS feed + HTML pagination
    ├── greenhouse.py    # Public JSON API
    ├── attrax.py        # Server-rendered HTML parsing
    ├── talentbrew.py    # JSON API + HTML fallback
    ├── phenom.py        # API discovery + HTML fallback
    ├── workday.py       # Undocumented internal API
    └── successfactors.py # API discovery + HTML fallback
```

### Key design decisions

- **Config-driven**: Adding sources is a YAML change, not a code change
- **Error isolation**: Each scraper runs independently — one failure doesn't stop others
- **Deduplication**: Jobs found on both BioSpace and a company page are merged, preferring the company-page version
- **Rate limiting**: Configurable delay between requests to be polite to servers
- **Retry logic**: Automatic retries with exponential backoff on HTTP failures

## Output

Results are saved as timestamped JSON files in the `output/` directory:

```json
{
  "discovered_at": "2026-02-07T...",
  "total_jobs": 342,
  "jobs": [
    {
      "title": "Senior Scientist, Biology",
      "company": "BridgeBio",
      "url": "https://...",
      "source": "greenhouse:bridgebio",
      "location": "San Francisco, CA",
      "description": "...",
      "fingerprint": "a1b2c3d4e5f6"
    }
  ]
}
```

## Testing

```bash
pytest tests/ -v
```
