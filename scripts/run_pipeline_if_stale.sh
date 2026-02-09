#!/bin/bash
#
# run_pipeline_if_stale.sh
#
# Checks if the job discovery pipeline was last run more than 6 hours ago.
# If so, invokes cortex to run the full pipeline.
#
# Usage:
#   ./scripts/run_pipeline_if_stale.sh
#
# Can be run via cron, launchd, or manually.

set -e

REPO_DIR="/Users/avadrevu/workspace/pharma positions"
DISCOVERY_LOG="$REPO_DIR/job-discovery/data/discovery_log.jsonl"
STALE_HOURS=6

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
    echo "=== Pharma Job Pipeline Scheduler ==="
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
            exit 0
        fi
        
        echo "Pipeline is stale. Running..."
    fi
    
    echo ""
    echo "=== Starting Pipeline ==="
    
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
}

main "$@"
