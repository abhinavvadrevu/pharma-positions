#!/bin/bash
#
# run_pipeline_if_stale.sh
#
# Checks if the job discovery pipeline was last run more than 12 hours ago.
# If so, invokes cortex to run the full pipeline.
# Sends email notification on errors.
#
# Usage:
#   ./scripts/run_pipeline_if_stale.sh
#
# Cron (every 12 hours at 8am and 8pm):
#   0 8,20 * * * "/Users/avadrevu/workspace/pharma positions/scripts/run_pipeline_if_stale.sh" >> ~/pharma-pipeline.log 2>&1

set -eE  # Exit on error, inherit ERR trap in functions

REPO_DIR="/Users/avadrevu/workspace/pharma positions"
DISCOVERY_LOG="$REPO_DIR/job-discovery/data/discovery_log.jsonl"
LOG_FILE="$HOME/pharma-pipeline.log"
STALE_HOURS=12

# Email settings
NOTIFY_EMAIL="abhinavvadrevu1@gmail.com"
CC_EMAIL="gauree.chendke@gmail.com"

# Send error notification email via Resend
send_error_email() {
    local error_msg="$1"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    # Get API key from cortex secret store
    local api_key=$(cortex secret get resend_api_key 2>/dev/null || echo "")
    
    if [[ -z "$api_key" ]]; then
        echo "ERROR: Could not retrieve Resend API key to send error notification"
        return 1
    fi
    
    # Get last 50 lines of log for context
    local log_tail=""
    if [[ -f "$LOG_FILE" ]]; then
        log_tail=$(tail -50 "$LOG_FILE" | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')
    fi
    
    local json_payload=$(cat <<EOF
{
    "from": "Pharma Jobs <onboarding@resend.dev>",
    "to": ["$NOTIFY_EMAIL"],
    "cc": ["$CC_EMAIL"],
    "subject": "⚠️ Pharma Pipeline Error - $timestamp",
    "html": "<div style='font-family:system-ui,sans-serif;max-width:600px;margin:0 auto;padding:20px;'><div style='background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:20px;margin-bottom:20px;'><h2 style='color:#dc2626;margin:0 0 10px 0;'>Pipeline Error</h2><p style='color:#7f1d1d;margin:0;'>The scheduled pharma job pipeline encountered an error.</p></div><div style='background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:20px;'><h3 style='margin:0 0 8px 0;color:#374151;'>Error Details</h3><pre style='background:#1f2937;color:#f9fafb;padding:12px;border-radius:6px;overflow-x:auto;font-size:13px;white-space:pre-wrap;'>$error_msg</pre></div><div style='background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;'><h3 style='margin:0 0 8px 0;color:#374151;'>Recent Log Output</h3><pre style='background:#1f2937;color:#f9fafb;padding:12px;border-radius:6px;overflow-x:auto;font-size:11px;max-height:300px;overflow-y:auto;white-space:pre-wrap;'>$log_tail</pre></div><p style='color:#9ca3af;font-size:12px;margin-top:20px;'>Timestamp: $timestamp</p></div>"
}
EOF
)

    curl -s -X POST "https://api.resend.com/emails" \
        -H "Authorization: Bearer $api_key" \
        -H "Content-Type: application/json" \
        -H "User-Agent: PharmaJobsPipeline/1.0" \
        -d "$json_payload" > /dev/null
    
    echo "Error notification sent to $NOTIFY_EMAIL"
}

# Error handler
on_error() {
    local exit_code=$?
    local line_no=$1
    local error_msg="Script failed at line $line_no with exit code $exit_code"
    
    echo ""
    echo "=== ERROR ==="
    echo "$error_msg"
    echo ""
    
    send_error_email "$error_msg"
    
    exit $exit_code
}

# Set up error trap
trap 'on_error $LINENO' ERR

# Get the timestamp of the last pipeline run
get_last_run_timestamp() {
    if [[ ! -f "$DISCOVERY_LOG" ]]; then
        echo "0"
        return
    fi
    
    # Get the last line's scraped_at timestamp and convert to Unix epoch
    tail -1 "$DISCOVERY_LOG" | python3 -c "
import json
import sys
from datetime import datetime

try:
    data = json.load(sys.stdin)
    ts = data.get('scraped_at', '')
    if ts:
        # Parse ISO format with timezone
        dt = datetime.fromisoformat(ts)
        print(int(dt.timestamp()))
    else:
        print(0)
except:
    print(0)
"
}

# Check if pipeline is stale (more than STALE_HOURS since last run)
is_stale() {
    local last_run=$1
    local now=$(date +%s)
    local stale_seconds=$((STALE_HOURS * 3600))
    local age=$((now - last_run))
    
    if [[ $age -gt $stale_seconds ]]; then
        return 0  # true, is stale
    else
        return 1  # false, not stale
    fi
}

# Format seconds as human-readable duration
format_duration() {
    local seconds=$1
    local hours=$((seconds / 3600))
    local minutes=$(((seconds % 3600) / 60))
    
    if [[ $hours -gt 0 ]]; then
        echo "${hours}h ${minutes}m"
    else
        echo "${minutes}m"
    fi
}

# Main
main() {
    echo ""
    echo "=========================================="
    echo "  Pharma Job Pipeline Scheduler"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="
    echo ""
    echo "Checking last run time..."
    
    last_run=$(get_last_run_timestamp)
    now=$(date +%s)
    age=$((now - last_run))
    
    if [[ $last_run -eq 0 ]]; then
        echo "No previous run found. Running pipeline..."
    else
        echo "Last run: $(format_duration $age) ago"
        echo "Threshold: ${STALE_HOURS}h"
        
        if ! is_stale $last_run; then
            echo "Pipeline is fresh. Skipping."
            echo ""
            exit 0
        fi
        
        echo "Pipeline is stale. Running..."
    fi
    
    echo ""
    echo "=== Starting Pipeline ==="
    echo ""
    
    # Run cortex with explicit instructions
    cd "$REPO_DIR"
    
    cortex --print "Run the pharma job discovery pipeline. This MUST complete ALL steps:

1. SCRAPE: Run the discovery script to scrape all job boards
2. FILTER: Apply cheap filters to get candidates  
3. EVALUATE: Read candidates.json and evaluate each job against the candidate profile
4. SAVE: Save matched jobs to jobs.json (include is_bay_area for each)
5. NOTIFY: If there were new matches, run the notification script to git push and send email

Use the run-pipeline skill. Do NOT stop until all 5 steps are complete and notifications are sent (if there were matches).

IMPORTANT: For Step 5 (notifications), use secret_env to inject the Resend API key:
secret_env: {\"RESEND_API_KEY\": \"resend_api_key\"}" --bypass

    echo ""
    echo "=== Pipeline Complete ==="
    echo ""
}

main "$@"
