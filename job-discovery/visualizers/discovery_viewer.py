#!/usr/bin/env python3
"""Discovery Log Viewer — generates a self-contained HTML dashboard.

Usage:
    python visualizers/discovery_viewer.py                      # uses default data/discovery_log.jsonl
    python visualizers/discovery_viewer.py --input path/to.jsonl
    python visualizers/discovery_viewer.py --open                # auto-open in browser

Reads the JSONL discovery log and generates a rich, interactive HTML file
with search, filtering, sorting, stats, and more.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "data" / "discovery_log.jsonl"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "output" / "discovery_viewer.html"


def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file, skipping malformed lines."""
    entries = []
    with open(path, "r") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  Warning: skipped malformed line {i}", file=sys.stderr)
    return entries


def generate_html(entries: list[dict], generated_at: str) -> str:
    """Generate the full self-contained HTML page."""
    data_json = json.dumps(entries, ensure_ascii=False)
    return HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_json).replace(
        "__GENERATED_AT__", generated_at
    )


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Discovery Log Viewer</title>
<style>
:root {
  --bg: #0f1117;
  --bg-card: #1a1d27;
  --bg-hover: #22253a;
  --bg-input: #1e2130;
  --bg-stripe: #14161f;
  --border: #2d3148;
  --border-subtle: rgba(45,49,72,0.4);
  --text: #e4e6f0;
  --text-dim: #8b8fa3;
  --text-muted: #5c6078;
  --accent: #6c7aff;
  --accent-dim: #4a55cc;
  --accent-bg: rgba(108,122,255,0.08);
  --green: #4ade80;
  --amber: #fbbf24;
  --red: #f87171;
  --cyan: #22d3ee;
  --pink: #f472b6;
  --orange: #fb923c;
  --radius: 8px;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
  overflow-x: hidden;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
::selection { background: var(--accent); color: #fff; }

/* ── Header ─────────────────────────────────────────── */
.header {
  background: var(--bg-card); border-bottom: 1px solid var(--border);
  padding: 12px 24px; display: flex; align-items: center; gap: 16px;
  position: sticky; top: 0; z-index: 100;
}
.header h1 {
  font-size: 15px; font-weight: 600; white-space: nowrap;
  color: var(--text-dim); letter-spacing: -0.3px;
}
.header h1 span { color: var(--accent); }
.header .meta { font-size: 11px; color: var(--text-muted); margin-left: auto; white-space: nowrap; }

/* ── Search bar ─────────────────────────────────────── */
.search-bar { flex: 1; max-width: 480px; position: relative; }
.search-bar svg {
  position: absolute; left: 11px; top: 50%; transform: translateY(-50%);
  color: var(--text-muted); width: 15px; height: 15px;
}
.search-bar input {
  width: 100%; padding: 9px 32px 9px 36px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-input); color: var(--text);
  font-size: 13px; outline: none; transition: border-color 0.2s, box-shadow 0.2s;
}
.search-bar input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(108,122,255,0.15); }
.search-bar input::placeholder { color: var(--text-muted); }
.search-bar .clear-btn {
  position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
  background: var(--bg); border: 1px solid var(--border); color: var(--text-muted);
  cursor: pointer; font-size: 11px; display: none; padding: 2px 6px;
  border-radius: 3px; line-height: 1;
}
.search-bar .clear-btn.show { display: block; }
.search-bar .clear-btn:hover { color: var(--text); border-color: var(--text-muted); }

/* ── Layout ─────────────────────────────────────────── */
.container { display: flex; min-height: calc(100vh - 49px); }

/* ── Sidebar ────────────────────────────────────────── */
.sidebar {
  width: 240px; min-width: 240px; background: var(--bg-card);
  border-right: 1px solid var(--border); padding: 12px;
  overflow-y: auto; max-height: calc(100vh - 49px); position: sticky; top: 49px;
}
.sidebar h3 {
  font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px;
  color: var(--text-muted); margin: 14px 0 6px; font-weight: 600;
  padding: 0 6px;
}
.sidebar h3:first-child { margin-top: 4px; }
.filter-group { margin-bottom: 1px; }
.filter-btn {
  display: flex; align-items: center; gap: 6px; width: 100%;
  padding: 5px 6px; border: none; background: none; color: var(--text-dim);
  font-size: 12px; cursor: pointer; border-radius: 4px; text-align: left;
  transition: background 0.12s, color 0.12s; line-height: 1.3;
}
.filter-btn:hover { background: var(--bg-hover); color: var(--text); }
.filter-btn.active { background: var(--accent-dim); color: #fff; }
.filter-btn .name {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.filter-btn .count {
  flex-shrink: 0; font-size: 10px; color: var(--text-muted);
  background: var(--bg); padding: 0 5px; border-radius: 8px; font-variant-numeric: tabular-nums;
}
.filter-btn.active .count { background: rgba(255,255,255,0.15); color: rgba(255,255,255,0.8); }
.filter-btn.zero-count { opacity: 0.35; }
.clear-filters {
  display: block; width: 100%; margin-top: 12px; padding: 5px 10px; font-size: 11px;
  border: 1px solid var(--border); border-radius: 4px; background: none;
  color: var(--text-dim); cursor: pointer; transition: all 0.15s; text-align: center;
}
.clear-filters:hover { border-color: var(--accent); color: var(--accent); }
.show-more-btn { color: var(--accent) !important; font-size: 11px !important; }

/* ── Active filter chips ────────────────────────────── */
.active-chips {
  display: flex; gap: 6px; flex-wrap: wrap; padding: 10px 24px 0;
}
.active-chips:empty { display: none; }
.chip {
  display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px 3px 8px;
  background: var(--accent-bg); border: 1px solid rgba(108,122,255,0.25);
  border-radius: 20px; font-size: 11px; color: var(--accent); cursor: default;
}
.chip .chip-x {
  cursor: pointer; margin-left: 2px; opacity: 0.6;
  font-size: 13px; line-height: 1;
}
.chip .chip-x:hover { opacity: 1; }

/* ── Stats bar ──────────────────────────────────────── */
.stats-bar { display: flex; gap: 10px; padding: 14px 24px 6px; flex-wrap: wrap; }
.stat-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 10px 14px; min-width: 120px; flex: 1;
}
.stat-card .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.stat-card .value { font-size: 22px; font-weight: 700; margin-top: 2px; font-variant-numeric: tabular-nums; }
.stat-card .sub { font-size: 11px; color: var(--text-dim); margin-top: 1px; }

/* ── Main content ───────────────────────────────────── */
.main { flex: 1; padding: 0; overflow: hidden; display: flex; flex-direction: column; }
.table-wrap { flex: 1; overflow: auto; }
.toolbar {
  display: flex; align-items: center; gap: 10px; padding: 8px 24px;
  border-bottom: 1px solid var(--border); flex-wrap: wrap;
}
.toolbar .result-count { font-size: 12px; color: var(--text-dim); }
.toolbar .result-count strong { color: var(--text); font-weight: 600; }
.toolbar .spacer { flex: 1; }
.toolbar select {
  padding: 4px 8px; border-radius: 4px; border: 1px solid var(--border);
  background: var(--bg-input); color: var(--text); font-size: 11px; cursor: pointer;
}
.export-btn {
  padding: 5px 10px; font-size: 11px;
  border: 1px solid var(--border); border-radius: 4px; background: none;
  color: var(--text-dim); cursor: pointer; transition: all 0.15s;
}
.export-btn:hover { border-color: var(--accent); color: var(--accent); }

/* ── Table ──────────────────────────────────────────── */
.jobs-table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
.jobs-table thead th {
  position: sticky; top: 0; z-index: 10; background: var(--bg-card);
  padding: 8px 14px; text-align: left; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.6px; color: var(--text-muted); border-bottom: 2px solid var(--border);
  cursor: pointer; user-select: none; white-space: nowrap; font-weight: 600;
}
.jobs-table thead th:hover { color: var(--text); }
.jobs-table thead th .sort-arrow { font-size: 9px; opacity: 0.7; }
.jobs-table .th-title { width: 38%; }
.jobs-table .th-company { width: 14%; }
.jobs-table .th-location { width: 16%; }
.jobs-table .th-source { width: 10%; }
.jobs-table .th-posted { width: 10%; }
.jobs-table .th-seen { width: 12%; }

.jobs-table tbody tr.job-row {
  border-bottom: 1px solid var(--border-subtle); cursor: pointer;
  transition: background 0.08s;
}
.jobs-table tbody tr.job-row:nth-child(4n+3):not(:hover):not(.expanded),
.jobs-table tbody tr.job-row:nth-child(4n+4):not(:hover):not(.expanded) {
  /* zebra stripe — affects pairs because detail-row is also a <tr> */
}
.jobs-table tbody tr.job-row:hover { background: var(--bg-hover); }
.jobs-table tbody tr.job-row.expanded { background: var(--accent-bg); }
.jobs-table tbody td { padding: 0; vertical-align: top; }

/* ── Cell contents ──────────────────────────────────── */
.cell { padding: 10px 14px; }
.cell-title .title-text { font-weight: 500; color: var(--text); line-height: 1.35; }
.cell-title .desc-preview {
  font-size: 11px; color: var(--text-muted); margin-top: 2px;
  line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}
.cell-company { color: var(--text-dim); font-size: 12.5px; }
.cell-location { color: var(--text-muted); font-size: 12px; }
.cell-date { color: var(--text-muted); font-size: 11.5px; white-space: nowrap; }
.cell-date .date-exact { display: none; }
.cell-date:hover .date-relative { display: none; }
.cell-date:hover .date-exact { display: inline; }
.cell-seen { font-size: 11.5px; white-space: nowrap; }
.cell-seen .new-badge {
  display: inline-block; padding: 1px 6px; border-radius: 8px; font-size: 9px;
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
  background: rgba(74,222,128,0.15); color: var(--green);
}
.cell-seen .seen-date { color: var(--text-muted); }

/* ── Expand chevron ─────────────────────────────────── */
.cell-title .expand-hint {
  float: right; color: var(--text-muted); font-size: 11px;
  margin-left: 8px; margin-top: 2px; transition: transform 0.15s;
}
.expanded .cell-title .expand-hint { transform: rotate(90deg); color: var(--accent); }

/* ── Source badges ──────────────────────────────────── */
.badge {
  padding: 2px 7px; border-radius: 8px; font-size: 10px; font-weight: 500;
  display: inline-block; white-space: nowrap; letter-spacing: 0.2px;
}
.badge-biospace { background: rgba(34,211,238,0.12); color: var(--cyan); }
.badge-greenhouse { background: rgba(74,222,128,0.12); color: var(--green); }
.badge-attrax { background: rgba(251,191,36,0.12); color: var(--amber); }
.badge-workday { background: rgba(244,114,182,0.12); color: var(--pink); }
.badge-talentbrew { background: rgba(251,146,60,0.12); color: var(--orange); }
.badge-phenom { background: rgba(248,113,113,0.12); color: var(--red); }
.badge-successfactors { background: rgba(108,122,255,0.12); color: var(--accent); }

/* ── Expanded row detail ────────────────────────────── */
.detail-row td { padding: 0 !important; }
.detail-panel {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); margin: 0 14px 10px;
  padding: 14px 18px; animation: slideDown 0.12s ease;
}
@keyframes slideDown { from { opacity:0; max-height:0; } to { opacity:1; max-height:600px; } }
.detail-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px; margin-bottom: 10px;
}
.detail-field label {
  font-size: 9px; text-transform: uppercase; color: var(--text-muted);
  letter-spacing: 0.8px; display: block; margin-bottom: 1px; font-weight: 500;
}
.detail-field .val { font-size: 13px; word-break: break-word; }
.url-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.url-row a {
  font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.copy-btn {
  flex-shrink: 0; padding: 3px 8px; font-size: 10px; border: 1px solid var(--border);
  border-radius: 4px; background: none; color: var(--text-muted); cursor: pointer;
  transition: all 0.15s;
}
.copy-btn:hover { border-color: var(--accent); color: var(--accent); }
.copy-btn.copied { border-color: var(--green); color: var(--green); }
.description-box {
  background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
  padding: 10px 12px; font-size: 12px; line-height: 1.6; color: var(--text-dim);
  max-height: 160px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
}

/* ── Pagination ─────────────────────────────────────── */
.pagination {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 12px 24px; border-top: 1px solid var(--border); flex-shrink: 0;
}
.pagination button {
  padding: 5px 10px; border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg-card); color: var(--text-dim); cursor: pointer;
  font-size: 12px; transition: all 0.12s; min-width: 32px;
}
.pagination button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pagination button:disabled { opacity: 0.25; cursor: default; }
.pagination button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.pagination .page-info { font-size: 11px; color: var(--text-muted); margin: 0 6px; }

/* ── Highlight ──────────────────────────────────────── */
mark { background: rgba(108,122,255,0.3); color: var(--text); border-radius: 2px; padding: 0 1px; }

/* ── Keyboard hint ──────────────────────────────────── */
.kbd-hint {
  position: fixed; bottom: 12px; right: 12px; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px;
  font-size: 10px; color: var(--text-muted); display: flex; gap: 10px; z-index: 50;
  opacity: 0.7; transition: opacity 0.2s;
}
.kbd-hint:hover { opacity: 1; }
.kbd-hint kbd {
  background: var(--bg); border: 1px solid var(--border); border-radius: 3px;
  padding: 0 4px; font-family: inherit; font-size: 9px;
}

/* ── Empty state ────────────────────────────────────── */
.empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); }
.empty-state p { font-size: 13px; margin-top: 8px; }

/* ── Toast ──────────────────────────────────────────── */
.toast {
  position: fixed; bottom: 60px; left: 50%; transform: translateX(-50%);
  background: var(--bg-card); border: 1px solid var(--green); color: var(--green);
  padding: 8px 16px; border-radius: 6px; font-size: 12px; z-index: 200;
  animation: toastIn 0.2s ease, toastOut 0.2s ease 1.5s forwards;
}
@keyframes toastIn { from { opacity:0; transform:translateX(-50%) translateY(10px); } to { opacity:1; transform:translateX(-50%) translateY(0); } }
@keyframes toastOut { from { opacity:1; } to { opacity:0; } }

/* ── Scrollbar ──────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 1100px) {
  .sidebar { width: 200px; min-width: 200px; }
}
@media (max-width: 900px) {
  .sidebar { display: none; }
  .stats-bar { padding: 10px 16px; }
  .stat-card { min-width: 90px; }
}
</style>
</head>
<body>

<div class="header">
  <h1><span>&#9679;</span> Discovery Log</h1>
  <div class="search-bar">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
    <input type="text" id="searchInput" placeholder="Search title, company, location, source..." autofocus>
    <button class="clear-btn" id="clearSearch" title="Clear (Esc)">ESC</button>
  </div>
  <div class="meta">__GENERATED_AT__</div>
</div>

<div class="container">
  <aside class="sidebar" id="sidebar">
    <h3>Sources</h3>
    <div id="sourceFilters"></div>
    <h3>Companies</h3>
    <div id="companyFilters"></div>
    <h3>Departments</h3>
    <div id="deptFilters"></div>
    <button class="clear-filters" id="clearFilters" style="display:none">Clear all filters</button>
  </aside>

  <div class="main">
    <div class="stats-bar" id="statsBar"></div>
    <div class="active-chips" id="activeChips"></div>
    <div class="toolbar">
      <span class="result-count" id="resultCount"></span>
      <span class="spacer"></span>
      <select id="sortSelect">
        <option value="first_seen-desc">First seen (newest)</option>
        <option value="first_seen-asc">First seen (oldest)</option>
        <option value="title-asc">Title A-Z</option>
        <option value="title-desc">Title Z-A</option>
        <option value="company-asc">Company A-Z</option>
        <option value="company-desc">Company Z-A</option>
        <option value="date_posted-desc">Date posted (newest)</option>
        <option value="date_posted-asc">Date posted (oldest)</option>
      </select>
      <select id="perPageSelect">
        <option value="50">50</option>
        <option value="100" selected>100</option>
        <option value="250">250</option>
      </select>
      <button class="export-btn" id="exportBtn">Export CSV</button>
    </div>
    <div class="table-wrap" id="tableWrap">
      <table class="jobs-table">
        <thead>
          <tr>
            <th class="th-title" data-col="title">Title <span class="sort-arrow"></span></th>
            <th class="th-company" data-col="company">Company <span class="sort-arrow"></span></th>
            <th class="th-location" data-col="location">Location <span class="sort-arrow"></span></th>
            <th class="th-source" data-col="source">Source <span class="sort-arrow"></span></th>
            <th class="th-posted" data-col="date_posted">Posted <span class="sort-arrow"></span></th>
            <th class="th-seen" data-col="first_seen">First Seen <span class="sort-arrow"></span></th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <div class="pagination" id="pagination"></div>
  </div>
</div>

<div class="kbd-hint">
  <span><kbd>/</kbd> Search</span>
  <span><kbd>Esc</kbd> Clear</span>
  <span><kbd>&larr;</kbd><kbd>&rarr;</kbd> Pages</span>
</div>

<script>
// ── Data ──────────────────────────────────────────────
const RAW_DATA = __DATA_PLACEHOLDER__;

// ── URL Normalization for dedup ───────────────────────
function normalizeUrl(url) {
  if (!url) return '';
  try {
    let u = url.trim();
    // Remove protocol
    u = u.replace(/^https?:\/\//, '');
    // Remove www.
    u = u.replace(/^www\./, '');
    // Lowercase
    u = u.toLowerCase();
    // Strip trailing slash
    u = u.replace(/\/+$/, '');
    // Remove tracking params
    const trackingParams = new Set([
      'utm_source','utm_medium','utm_campaign','utm_term','utm_content',
      'source','ref','src','trk','linksource','linkSource','LinkSource',
      'gh_jid','gh_src'
    ]);
    if (u.includes('?')) {
      const [path, qs] = u.split('?', 2);
      const params = new URLSearchParams(qs);
      const clean = [];
      for (const [k, v] of params) {
        if (!trackingParams.has(k) && !trackingParams.has(k.toLowerCase())) {
          clean.push(k + '=' + v);
        }
      }
      u = clean.length ? path + '?' + clean.join('&') : path;
    }
    return u;
  } catch { return url.trim().toLowerCase(); }
}

// ── Compute first-seen map ────────────────────────────
// Groups by normalized URL, finds earliest scraped_at for each
const firstSeenMap = {};
for (const d of RAW_DATA) {
  const key = normalizeUrl(d.url);
  if (!key) continue;
  const ts = d.scraped_at || d.run_id || '';
  if (!firstSeenMap[key] || ts < firstSeenMap[key]) {
    firstSeenMap[key] = ts;
  }
}
const totalUniqueUrls = Object.keys(firstSeenMap).length;

// ── State ─────────────────────────────────────────────
let state = {
  search: '',
  sourceFilter: null,
  companyFilter: null,
  deptFilter: null,
  sortCol: 'first_seen',
  sortDir: 'desc',
  page: 1,
  perPage: 100,
  expandedIdx: null,
};

// ── Precompute ────────────────────────────────────────
const data = RAW_DATA.map((d, i) => {
  const normUrl = normalizeUrl(d.url);
  return {
    ...d,
    _idx: i,
    _search: [d.title, d.company, d.location, d.source, d.department, d.description_snippet || ''].join('\x00').toLowerCase(),
    _sourceBase: (d.source || '').split(':')[0],
    _dept: d.department || '',
    _normUrl: normUrl,
    first_seen: firstSeenMap[normUrl] || d.scraped_at || '',
  };
});

// ── Sidebar counts (dynamic based on current filter) ──
function countBy(arr, key) {
  const m = {};
  for (const d of arr) { const v = d[key] || '(none)'; m[v] = (m[v]||0)+1; }
  return Object.entries(m).sort((a,b) => b[1]-a[1]);
}

// Full counts for sidebar ordering
const allSourceCounts = countBy(data, '_sourceBase');
const allCompanyCounts = countBy(data, 'company');
const allDeptCounts = countBy(data, '_dept');

// ── Render sidebar filters with dynamic counts ────────
function renderFilters(containerId, allCounts, filteredCounts, stateKey) {
  const el = document.getElementById(containerId);
  const filteredMap = Object.fromEntries(filteredCounts);
  const limit = 15;
  const hasMore = allCounts.length > limit;
  let html = '';

  allCounts.forEach(([val], i) => {
    const cnt = filteredMap[val] || 0;
    const hidden = i >= limit ? ' style="display:none" data-overflow' : '';
    const zeroClass = cnt === 0 ? ' zero-count' : '';
    const activeClass = state[stateKey] === val ? ' active' : '';
    html += `<div class="filter-group"${hidden}>
      <button class="filter-btn${activeClass}${zeroClass}" data-key="${stateKey}" data-val="${esc(val)}">
        <span class="name">${esc(val)}</span><span class="count">${cnt}</span>
      </button></div>`;
  });
  if (hasMore) {
    html += `<button class="filter-btn show-more-btn" data-container="${containerId}">
      <span class="name">Show all ${allCounts.length}...</span></button>`;
  }
  el.innerHTML = html;
}

// ── Get filtered data (without a specific filter key) ─
function getFilteredExcluding(excludeKey) {
  let arr = data;
  if (state.search) {
    const terms = state.search.toLowerCase().split(/\s+/).filter(Boolean);
    arr = arr.filter(d => terms.every(t => d._search.includes(t)));
  }
  if (excludeKey !== 'sourceFilter' && state.sourceFilter)
    arr = arr.filter(d => d._sourceBase === state.sourceFilter);
  if (excludeKey !== 'companyFilter' && state.companyFilter)
    arr = arr.filter(d => d.company === state.companyFilter);
  if (excludeKey !== 'deptFilter' && state.deptFilter)
    arr = arr.filter(d => (d._dept || '(none)') === state.deptFilter);
  return arr;
}

// ── Filter / Sort / Search ────────────────────────────
function getFiltered() {
  let arr = getFilteredExcluding(null);
  const col = state.sortCol;
  const dir = state.sortDir === 'asc' ? 1 : -1;
  arr = [...arr].sort((a, b) => {
    let va = (a[col] || '').toLowerCase();
    let vb = (b[col] || '').toLowerCase();
    if (va < vb) return -1 * dir;
    if (va > vb) return 1 * dir;
    return 0;
  });
  return arr;
}

// ── Render stats ──────────────────────────────────────
function renderStats(filtered) {
  const companies = new Set(filtered.map(d => d.company).filter(Boolean)).size;
  const sources = new Set(filtered.map(d => d._sourceBase)).size;
  const uniqueUrls = new Set(filtered.map(d => d._normUrl).filter(Boolean)).size;

  document.getElementById('statsBar').innerHTML = `
    <div class="stat-card"><div class="label">Showing</div>
      <div class="value">${filtered.length.toLocaleString()}</div>
      <div class="sub">of ${data.length.toLocaleString()} log entries</div></div>
    <div class="stat-card"><div class="label">Unique Jobs</div>
      <div class="value">${uniqueUrls.toLocaleString()}</div>
      <div class="sub">by URL (${totalUniqueUrls.toLocaleString()} total)</div></div>
    <div class="stat-card"><div class="label">Companies</div>
      <div class="value">${companies}</div>
      <div class="sub">${sources} source${sources!==1?'s':''}</div></div>
    <div class="stat-card"><div class="label">With Descriptions</div>
      <div class="value">${filtered.filter(d=>d.description_snippet).length.toLocaleString()}</div>
      <div class="sub">${((filtered.filter(d=>d.description_snippet).length/Math.max(filtered.length,1))*100).toFixed(0)}% coverage</div></div>
  `;
}

// ── Active chips ──────────────────────────────────────
function renderChips() {
  const el = document.getElementById('activeChips');
  let html = '';
  if (state.search) html += `<div class="chip">Search: "${esc(state.search)}" <span class="chip-x" data-clear="search">&times;</span></div>`;
  if (state.sourceFilter) html += `<div class="chip">Source: ${esc(state.sourceFilter)} <span class="chip-x" data-clear="sourceFilter">&times;</span></div>`;
  if (state.companyFilter) html += `<div class="chip">Company: ${esc(state.companyFilter)} <span class="chip-x" data-clear="companyFilter">&times;</span></div>`;
  if (state.deptFilter) html += `<div class="chip">Dept: ${esc(state.deptFilter)} <span class="chip-x" data-clear="deptFilter">&times;</span></div>`;
  el.innerHTML = html;
}

// ── Badge helper ──────────────────────────────────────
function badgeClass(source) { return 'badge badge-' + (source || '').split(':')[0]; }

// ── Highlight helper ──────────────────────────────────
function highlight(text, search) {
  if (!search || !text) return esc(text || '');
  const terms = search.toLowerCase().split(/\s+/).filter(Boolean);
  let result = esc(text);
  for (const term of terms) {
    const re = new RegExp('(' + escRegex(term) + ')', 'gi');
    result = result.replace(re, '<mark>$1</mark>');
  }
  return result;
}
function esc(s) { if(!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

// ── Date formatting ───────────────────────────────────
function relativeDate(d) {
  if (!d) return '';
  try {
    const dt = new Date(d);
    if (isNaN(dt)) return esc(d);
    const now = new Date();
    const diffMs = now - dt;
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffDays < 0) return fmtDate(d);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return diffDays + 'd ago';
    if (diffDays < 30) return Math.floor(diffDays/7) + 'w ago';
    if (diffDays < 365) return Math.floor(diffDays/30) + 'mo ago';
    return Math.floor(diffDays/365) + 'y ago';
  } catch { return esc(d); }
}
function fmtDate(d) {
  if (!d) return '';
  try {
    const dt = new Date(d);
    if (isNaN(dt)) return esc(d);
    return dt.toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
  } catch { return esc(d); }
}
function fmtDateTime(d) {
  if (!d) return '';
  try {
    const dt = new Date(d);
    if (isNaN(dt)) return esc(d);
    return dt.toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric', hour:'numeric', minute:'2-digit' });
  } catch { return esc(d); }
}

// ── Render table ──────────────────────────────────────
function render() {
  const filtered = getFiltered();
  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / state.perPage));
  if (state.page > pages) state.page = pages;
  const start = (state.page - 1) * state.perPage;
  const pageData = filtered.slice(start, start + state.perPage);

  renderStats(filtered);
  renderChips();

  // Dynamic sidebar counts
  const srcData = getFilteredExcluding('sourceFilter');
  const coData = getFilteredExcluding('companyFilter');
  const deptData = getFilteredExcluding('deptFilter');
  renderFilters('sourceFilters', allSourceCounts, countBy(srcData, '_sourceBase'), 'sourceFilter');
  renderFilters('companyFilters', allCompanyCounts, countBy(coData, 'company'), 'companyFilter');
  renderFilters('deptFilters', allDeptCounts, countBy(deptData, '_dept'), 'deptFilter');

  document.getElementById('clearFilters').style.display =
    (state.sourceFilter || state.companyFilter || state.deptFilter) ? '' : 'none';

  // Result count
  const rcEl = document.getElementById('resultCount');
  if (state.search || state.sourceFilter || state.companyFilter || state.deptFilter) {
    rcEl.innerHTML = `<strong>${total.toLocaleString()}</strong> results`;
  } else {
    rcEl.innerHTML = `<strong>${total.toLocaleString()}</strong> log entries`;
  }

  // Table body
  const tbody = document.getElementById('tableBody');
  let html = '';
  if (pageData.length === 0) {
    html = `<tr><td colspan="6"><div class="empty-state">
      <p style="font-size:32px;margin-bottom:8px">No results</p>
      <p>Try adjusting your search or filters</p></div></td></tr>`;
  }
  for (const job of pageData) {
    const expanded = state.expandedIdx === job._idx;
    const descPreview = (job.description_snippet || '').replace(/<[^>]*>/g, '').substring(0, 120);
    html += `<tr data-idx="${job._idx}" class="job-row${expanded?' expanded':''}">
      <td><div class="cell cell-title">
        <span class="expand-hint">${expanded?'&#9660;':'&#9654;'}</span>
        <div class="title-text">${highlight(job.title, state.search)}</div>
        ${descPreview ? `<div class="desc-preview">${highlight(descPreview, state.search)}</div>` : ''}
      </div></td>
      <td><div class="cell cell-company">${highlight(job.company, state.search)}</div></td>
      <td><div class="cell cell-location">${highlight(job.location, state.search) || ''}</div></td>
      <td><div class="cell"><span class="${badgeClass(job.source)}">${esc(job.source)}</span></div></td>
      <td><div class="cell cell-date">${job.date_posted ?
          `<span class="date-relative">${relativeDate(job.date_posted)}</span><span class="date-exact">${fmtDate(job.date_posted)}</span>` : ''}</div></td>
      <td><div class="cell cell-seen">
        <span class="seen-date" title="${esc(job.first_seen)}">${relativeDate(job.first_seen)}</span>
      </div></td>
    </tr>`;
    if (expanded) {
      html += `<tr class="detail-row"><td colspan="6">
        <div class="detail-panel">
          <div class="detail-grid">
            <div class="detail-field"><label>Title</label><div class="val">${esc(job.title)}</div></div>
            <div class="detail-field"><label>Company</label><div class="val">${esc(job.company)}</div></div>
            <div class="detail-field"><label>Location</label><div class="val">${esc(job.location) || '<span style="color:var(--text-muted)">Not specified</span>'}</div></div>
            <div class="detail-field"><label>Source</label><div class="val"><span class="${badgeClass(job.source)}">${esc(job.source)}</span></div></div>
            <div class="detail-field"><label>Department</label><div class="val">${esc(job.department) || '<span style="color:var(--text-muted)">Not specified</span>'}</div></div>
            <div class="detail-field"><label>Date Posted</label><div class="val">${fmtDate(job.date_posted) || '<span style="color:var(--text-muted)">Unknown</span>'}</div></div>
            <div class="detail-field"><label>First Seen</label><div class="val">${fmtDateTime(job.first_seen)}</div></div>
            <div class="detail-field"><label>Scraped At</label><div class="val" style="font-size:11px;color:var(--text-dim)">${fmtDateTime(job.scraped_at)}</div></div>
          </div>
          <div class="url-row">
            <label style="font-size:9px;text-transform:uppercase;color:var(--text-muted);letter-spacing:0.8px;font-weight:500;flex-shrink:0">URL</label>
            <a href="${esc(job.url)}" target="_blank" rel="noopener">${esc(job.url)}</a>
            <button class="copy-btn" data-url="${esc(job.url)}">Copy</button>
          </div>
          ${(job.description_snippet) ? `<div class="detail-field">
            <label>Description</label>
            <div class="description-box">${esc(job.description_snippet)}</div>
          </div>` : ''}
        </div>
      </td></tr>`;
    }
  }
  tbody.innerHTML = html;

  // Pagination
  renderPagination(pages, total);

  // Sort arrows
  document.querySelectorAll('.jobs-table thead th').forEach(th => {
    const col = th.dataset.col;
    const arrow = th.querySelector('.sort-arrow');
    if (col === state.sortCol) {
      arrow.textContent = state.sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
    } else {
      arrow.textContent = '';
    }
  });
}

// ── Pagination rendering ──────────────────────────────
function renderPagination(pages, total) {
  const el = document.getElementById('pagination');
  if (pages <= 1) { el.innerHTML = ''; return; }
  let html = `<button id="prevPage" ${state.page<=1?'disabled':''}>&#8592;</button>`;
  const show = new Set([1, pages]);
  for (let i = Math.max(1,state.page-2); i <= Math.min(pages,state.page+2); i++) show.add(i);
  const sorted = [...show].sort((a,b)=>a-b);
  let last = 0;
  for (const p of sorted) {
    if (p - last > 1) html += `<span class="page-info">\u2026</span>`;
    html += `<button class="${p===state.page?'active':''}" data-page="${p}">${p}</button>`;
    last = p;
  }
  html += `<button id="nextPage" ${state.page>=pages?'disabled':''}>&#8594;</button>`;
  html += `<span class="page-info">${((state.page-1)*state.perPage+1).toLocaleString()}\u2013${Math.min(state.page*state.perPage,total).toLocaleString()} of ${total.toLocaleString()}</span>`;
  el.innerHTML = html;
}

// ── Toast ─────────────────────────────────────────────
function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast'; t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 1800);
}

// ── Event listeners ───────────────────────────────────
const searchInput = document.getElementById('searchInput');
const clearBtn = document.getElementById('clearSearch');
let searchTimeout;
searchInput.addEventListener('input', () => {
  clearTimeout(searchTimeout);
  clearBtn.classList.toggle('show', searchInput.value.length > 0);
  searchTimeout = setTimeout(() => {
    state.search = searchInput.value;
    state.page = 1; state.expandedIdx = null;
    render();
  }, 120);
});
clearBtn.addEventListener('click', () => {
  searchInput.value = ''; clearBtn.classList.remove('show');
  state.search = ''; state.page = 1;
  render(); searchInput.focus();
});

// Sidebar filters
document.getElementById('sidebar').addEventListener('click', e => {
  const btn = e.target.closest('.filter-btn[data-key]');
  if (btn) {
    const key = btn.dataset.key, val = btn.dataset.val;
    state[key] = state[key] === val ? null : val;
    state.page = 1; state.expandedIdx = null;
    render(); return;
  }
  const showMore = e.target.closest('.show-more-btn');
  if (showMore) {
    const container = document.getElementById(showMore.dataset.container);
    container.querySelectorAll('[data-overflow]').forEach(el => el.style.display = '');
    showMore.style.display = 'none';
  }
});

document.getElementById('clearFilters').addEventListener('click', () => {
  state.sourceFilter = null; state.companyFilter = null; state.deptFilter = null;
  state.page = 1; state.expandedIdx = null; render();
});

// Active chips removal
document.getElementById('activeChips').addEventListener('click', e => {
  const x = e.target.closest('.chip-x');
  if (!x) return;
  const key = x.dataset.clear;
  if (key === 'search') { searchInput.value = ''; clearBtn.classList.remove('show'); state.search = ''; }
  else { state[key] = null; }
  state.page = 1; state.expandedIdx = null; render();
});

// Sort select
document.getElementById('sortSelect').addEventListener('change', e => {
  const [col, dir] = e.target.value.split('-');
  state.sortCol = col; state.sortDir = dir;
  state.page = 1; state.expandedIdx = null; render();
});

// Column header sort
document.querySelector('.jobs-table thead').addEventListener('click', e => {
  const th = e.target.closest('th[data-col]');
  if (!th) return;
  const col = th.dataset.col;
  if (state.sortCol === col) { state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc'; }
  else { state.sortCol = col; state.sortDir = 'asc'; }
  const opt = document.querySelector(`#sortSelect option[value="${col}-${state.sortDir}"]`);
  if (opt) document.getElementById('sortSelect').value = opt.value;
  state.page = 1; render();
});

// Per page
document.getElementById('perPageSelect').addEventListener('change', e => {
  state.perPage = parseInt(e.target.value); state.page = 1; render();
});

// Row expand + copy URL
document.getElementById('tableBody').addEventListener('click', e => {
  // Copy button
  const copyBtn = e.target.closest('.copy-btn');
  if (copyBtn) {
    navigator.clipboard.writeText(copyBtn.dataset.url).then(() => {
      copyBtn.textContent = 'Copied!'; copyBtn.classList.add('copied');
      setTimeout(() => { copyBtn.textContent = 'Copy'; copyBtn.classList.remove('copied'); }, 1500);
    });
    return;
  }
  // Don't toggle if clicking a link
  if (e.target.tagName === 'A') return;
  const row = e.target.closest('tr.job-row');
  if (!row) return;
  const idx = parseInt(row.dataset.idx);
  state.expandedIdx = state.expandedIdx === idx ? null : idx;
  render();
});

// Pagination clicks
document.getElementById('pagination').addEventListener('click', e => {
  const btn = e.target.closest('button');
  if (!btn || btn.disabled) return;
  if (btn.id === 'prevPage') state.page--;
  else if (btn.id === 'nextPage') state.page++;
  else if (btn.dataset.page) state.page = parseInt(btn.dataset.page);
  state.expandedIdx = null; render();
  document.getElementById('tableWrap').scrollTop = 0;
});

// Keyboard
document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement !== searchInput) {
    e.preventDefault(); searchInput.focus(); searchInput.select();
  }
  if (e.key === 'Escape') {
    if (state.search) {
      searchInput.value = ''; clearBtn.classList.remove('show');
      state.search = ''; state.page = 1; render();
    }
    searchInput.blur();
  }
  if (document.activeElement === searchInput) return;
  if (e.key === 'ArrowLeft' && state.page > 1) { state.page--; state.expandedIdx = null; render(); }
  if (e.key === 'ArrowRight') {
    const pages = Math.ceil(getFiltered().length / state.perPage);
    if (state.page < pages) { state.page++; state.expandedIdx = null; render(); }
  }
});

// CSV export
document.getElementById('exportBtn').addEventListener('click', () => {
  const filtered = getFiltered();
  const cols = ['title','company','url','location','department','source','date_posted','first_seen','description_snippet'];
  let csv = cols.join(',') + '\n';
  for (const job of filtered) {
    csv += cols.map(c => '"' + (job[c]||'').replace(/"/g,'""') + '"').join(',') + '\n';
  }
  const blob = new Blob([csv], {type:'text/csv'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'discovery_jobs_export.csv';
  a.click(); URL.revokeObjectURL(url);
  showToast(`Exported ${filtered.length} jobs`);
});

// ── Initial render ────────────────────────────────────
render();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate Discovery Log Viewer HTML")
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(DEFAULT_INPUT),
        help=f"Path to discovery_log.jsonl (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=str(DEFAULT_OUTPUT),
        help=f"Path for output HTML (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Auto-open the generated HTML in the default browser",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {input_path}...")
    entries = load_jsonl(input_path)
    print(f"  Loaded {len(entries)} log entries")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = generate_html(entries, generated_at)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)
    print(f"  Wrote {output_path} ({len(html)//1024} KB)")

    if args.open:
        url = f"file://{output_path.resolve()}"
        print(f"  Opening in browser...")
        webbrowser.open(url)
    else:
        print(f"  Open in browser: file://{output_path.resolve()}")


if __name__ == "__main__":
    main()
