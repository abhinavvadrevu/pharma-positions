"""Notification module for the job discovery pipeline.

Provides two notification mechanisms:
1. Git commit and push to GitHub
2. Email notification via Resend API

Both are designed to be called as standalone scripts or imported.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Path constants
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "job-discovery" / "data"
GITHUB_PAGES_URL = "https://abhinavvadrevu.github.io/pharma-positions/"


def git_commit_and_push(new_jobs: list[dict]) -> tuple[bool, str]:
    """Commit updated data files and push to GitHub.
    
    Args:
        new_jobs: List of newly matched jobs (for commit message)
        
    Returns:
        (success, message) tuple
    """
    os.chdir(REPO_ROOT)
    
    # Check if there are changes to commit
    status = subprocess.run(
        ["git", "status", "--porcelain", "job-discovery/data/", "data.js", "index.html"],
        capture_output=True, text=True
    )
    
    if not status.stdout.strip():
        return True, "No changes to commit"
    
    # Copy data files to root for GitHub Pages
    try:
        import shutil
        shutil.copy(DATA_DIR / "data.js", REPO_ROOT / "data.js")
        shutil.copy(DATA_DIR / "viewer.html", REPO_ROOT / "index.html")
    except Exception as e:
        return False, f"Failed to copy files to root: {e}"
    
    # Stage changes
    subprocess.run(["git", "add", "job-discovery/data/", "data.js", "index.html"], check=True)
    
    # Build commit message
    job_count = len(new_jobs)
    if job_count == 0:
        msg = "Update job data (pipeline run)"
    elif job_count == 1:
        job = new_jobs[0]
        msg = f"Add 1 new job: {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}"
    else:
        companies = list(set(j.get('company', 'Unknown') for j in new_jobs))
        if len(companies) <= 3:
            msg = f"Add {job_count} new jobs from {', '.join(companies)}"
        else:
            msg = f"Add {job_count} new jobs from {len(companies)} companies"
    
    # Commit
    result = subprocess.run(
        ["git", "commit", "-m", msg],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        return False, f"Commit failed: {result.stderr}"
    
    # Push
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        return False, f"Push failed: {result.stderr}"
    
    return True, f"Committed and pushed: {msg}"


def send_email_notification(
    new_jobs: list[dict],
    to_email: str = "abhinavvadrevu1@gmail.com",
    api_key: Optional[str] = None,
) -> tuple[bool, str]:
    """Send email notification about new jobs via Resend API.
    
    Args:
        new_jobs: List of newly matched jobs
        to_email: Recipient email address
        api_key: Resend API key (reads from RESEND_API_KEY env var if not provided)
        
    Returns:
        (success, message) tuple
    """
    if not new_jobs:
        return True, "No new jobs to notify about"
    
    api_key = api_key or os.environ.get("RESEND_API_KEY")
    if not api_key:
        return False, "RESEND_API_KEY not set"
    
    # Build email content
    subject = _build_subject(new_jobs)
    html_body = _build_html_body(new_jobs)
    
    # Send via Resend API
    try:
        import urllib.request
        import urllib.error
        
        payload = json.dumps({
            "from": "Pharma Jobs <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }).encode("utf-8")
        
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "PharmaJobsPipeline/1.0",
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
            return True, f"Email sent: {response_data.get('id', 'OK')}"
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        return False, f"Resend API error {e.code}: {error_body}"
    except Exception as e:
        return False, f"Failed to send email: {e}"


def _build_subject(new_jobs: list[dict]) -> str:
    """Build email subject line."""
    count = len(new_jobs)
    bay_area_count = sum(1 for j in new_jobs if j.get("is_bay_area"))
    
    if count == 1:
        job = new_jobs[0]
        location_tag = " (Bay Area)" if job.get("is_bay_area") else ""
        return f"New pharma job: {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}{location_tag}"
    else:
        if bay_area_count == count:
            return f"{count} new pharma jobs found (all Bay Area)"
        elif bay_area_count > 0:
            return f"{count} new pharma jobs found ({bay_area_count} in Bay Area)"
        else:
            return f"{count} new pharma jobs found"


def _build_html_body(new_jobs: list[dict]) -> str:
    """Build HTML email body."""
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")
    
    # Sort: Bay Area first, then by company
    sorted_jobs = sorted(new_jobs, key=lambda j: (not j.get("is_bay_area", False), j.get("company", "")))
    
    jobs_html = ""
    for job in sorted_jobs:
        bay_badge = '<span style="background:#fef3c7;color:#d97706;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;margin-left:8px;">BAY AREA</span>' if job.get("is_bay_area") else ""
        
        description = job.get("description", "")
        if description:
            # Truncate and clean description
            desc_preview = description[:300].replace("\n", " ").strip()
            if len(description) > 300:
                desc_preview += "..."
            desc_html = f'<p style="color:#6b7280;font-size:13px;margin:8px 0 0 0;line-height:1.5;">{_escape_html(desc_preview)}</p>'
        else:
            desc_html = ""
        
        location = job.get("location", "")
        location_html = f'<span style="color:#6b7280;"> · {_escape_html(location)}</span>' if location else ""
        
        jobs_html += f'''
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
            <div style="margin-bottom:4px;">
                <a href="{_escape_html(job.get('url', '#'))}" style="color:#2563eb;text-decoration:none;font-weight:600;font-size:15px;">{_escape_html(job.get('title', 'Unknown Title'))}</a>
                {bay_badge}
            </div>
            <div style="color:#374151;font-size:14px;">
                {_escape_html(job.get('company', 'Unknown Company'))}{location_html}
            </div>
            {desc_html}
        </div>
        '''
    
    bay_area_count = sum(1 for j in new_jobs if j.get("is_bay_area"))
    stats_html = f"{len(new_jobs)} new job{'s' if len(new_jobs) != 1 else ''}"
    if bay_area_count > 0:
        stats_html += f" · {bay_area_count} in Bay Area"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#ffffff;">
        <div style="margin-bottom:24px;">
            <h1 style="color:#111827;font-size:22px;margin:0 0 8px 0;">New Pharma Jobs Found</h1>
            <p style="color:#6b7280;font-size:13px;margin:0;">Pipeline run: {now}</p>
            <p style="color:#6b7280;font-size:13px;margin:4px 0 0 0;">{stats_html}</p>
        </div>
        
        {jobs_html}
        
        <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;">
            <a href="{GITHUB_PAGES_URL}" style="display:inline-block;background:#2563eb;color:#ffffff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:500;font-size:14px;">View All Jobs</a>
        </div>
        
        <p style="color:#9ca3af;font-size:11px;margin-top:24px;">
            This email was sent by the pharma job discovery pipeline.
        </p>
    </body>
    </html>
    '''


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def run_notifications(new_jobs: list[dict], api_key: Optional[str] = None) -> dict:
    """Run all notifications (git push + email).
    
    Args:
        new_jobs: List of newly matched jobs
        api_key: Resend API key (optional, can be set via env var)
        
    Returns:
        Dict with results for each notification type
    """
    results = {}
    
    # Git commit and push
    success, message = git_commit_and_push(new_jobs)
    results["git"] = {"success": success, "message": message}
    print(f"Git: {message}")
    
    # Email notification
    if new_jobs:
        success, message = send_email_notification(new_jobs, api_key=api_key)
        results["email"] = {"success": success, "message": message}
        print(f"Email: {message}")
    else:
        results["email"] = {"success": True, "message": "No new jobs to notify about"}
        print("Email: Skipped (no new jobs)")
    
    return results


# CLI interface for standalone execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Send notifications for new jobs")
    parser.add_argument("--jobs-file", type=Path, help="JSON file with new jobs to notify about")
    parser.add_argument("--git-only", action="store_true", help="Only do git commit/push")
    parser.add_argument("--email-only", action="store_true", help="Only send email")
    args = parser.parse_args()
    
    # Load jobs
    if args.jobs_file:
        with open(args.jobs_file) as f:
            new_jobs = json.load(f)
    else:
        # Default: read from jobs.json and get the most recent ones
        jobs_path = DATA_DIR / "jobs.json"
        if jobs_path.exists():
            with open(jobs_path) as f:
                all_jobs = json.load(f)
            # Get jobs from the last hour as "new"
            cutoff = datetime.now(timezone.utc).isoformat()[:13]  # Same hour
            new_jobs = [j for j in all_jobs if (j.get("date_found", "") or "")[:13] == cutoff]
        else:
            new_jobs = []
    
    print(f"Found {len(new_jobs)} new jobs")
    
    if args.git_only:
        success, msg = git_commit_and_push(new_jobs)
        print(f"Git: {msg}")
        sys.exit(0 if success else 1)
    elif args.email_only:
        success, msg = send_email_notification(new_jobs)
        print(f"Email: {msg}")
        sys.exit(0 if success else 1)
    else:
        results = run_notifications(new_jobs)
        all_success = all(r["success"] for r in results.values())
        sys.exit(0 if all_success else 1)
