#!/bin/bash
#
# Test Deep Mode with Rate Limit Fix
# Tests with conservative settings to validate fix works
#

echo "========================================================================="
echo " TESTING DEEP MODE - RATE LIMIT FIX VALIDATION"
echo "========================================================================="
echo ""
echo "This test runs deep mode with CONSERVATIVE settings to validate the"
echo "rate limit fix. Expected runtime: ~20 minutes for 1 client."
echo ""
echo "Configuration:"
echo "  - Rate Limit: 0.5 req/min (1 request per 2 minutes)"
echo "  - Workers: 1 (sequential execution)"
echo "  - Base Delay: 120s (2 minute retry delay)"
echo "  - Cooldowns: 90-150s after each deep research"
echo ""
echo "========================================================================="
echo ""

# Set conservative configuration (explicit for testing)
export DEEP_RATE_LIMIT_RPM=0.5
export DEEP_RATE_LIMIT_BURST=1
export DEEP_MAX_WORKERS=1
export DEEP_RESEARCH_BASE_DELAY=120.0
export DEEP_RESEARCH_COOLDOWN_MIN=90.0
export DEEP_RESEARCH_COOLDOWN_MAX=150.0

echo "Environment variables set:"
echo "  DEEP_RATE_LIMIT_RPM=$DEEP_RATE_LIMIT_RPM"
echo "  DEEP_RATE_LIMIT_BURST=$DEEP_RATE_LIMIT_BURST"
echo "  DEEP_MAX_WORKERS=$DEEP_MAX_WORKERS"
echo "  DEEP_RESEARCH_BASE_DELAY=$DEEP_RESEARCH_BASE_DELAY"
echo "  DEEP_RESEARCH_COOLDOWN_MIN=$DEEP_RESEARCH_COOLDOWN_MIN"
echo "  DEEP_RESEARCH_COOLDOWN_MAX=$DEEP_RESEARCH_COOLDOWN_MAX"
echo ""

# Check vars.py configuration
echo "Checking vars.py client configuration..."
CLIENTS=$(python3 -c "import vars; print(', '.join(vars.clients))" 2>/dev/null)
echo "  Configured clients: $CLIENTS"
echo ""

# Recommend testing with single client first
echo "========================================================================="
echo " RECOMMENDATION"
echo "========================================================================="
echo ""
echo "For initial validation, edit vars.py to test with just ONE client:"
echo ""
echo "  clients = ['merck_test']  # Or your first client"
echo ""
echo "This allows you to validate the fix works before running all clients."
echo ""
echo "========================================================================="
echo ""

read -p "Press ENTER to start deep mode, or Ctrl+C to cancel and edit vars.py..."

echo ""
echo "Starting deep mode..."
echo "Logs: tail -f pipeline_deep_execution.log"
echo ""

# Run deep mode
python3 deep_v3_optimized.py

# Check exit code
EXIT_CODE=$?

echo ""
echo "========================================================================="
echo " TEST COMPLETE"
echo "========================================================================="
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Deep mode completed successfully!"
    echo ""
    echo "Validation checks:"
    echo ""

    # Check for rate limit errors
    RATE_LIMIT_COUNT=$(grep -c "RateLimitError" pipeline_deep_execution.log 2>/dev/null || echo "0")
    if [ "$RATE_LIMIT_COUNT" -eq 0 ]; then
        echo "  ✅ No rate limit errors detected"
    else
        echo "  ⚠️  Warning: $RATE_LIMIT_COUNT rate limit errors found"
        echo "     Check logs: grep 'RateLimitError' pipeline_deep_execution.log"
    fi

    # Check for deep research success
    DEEP_SUCCESS_COUNT=$(grep -c "Deep research cooldown" pipeline_deep_execution.log 2>/dev/null || echo "0")
    echo "  ✅ Deep research completed: $DEEP_SUCCESS_COUNT times"

    # Check for auth refresh
    AUTH_REFRESH_COUNT=$(grep -c "Auth refreshed from default profile" pipeline_deep_execution.log 2>/dev/null || echo "0")
    echo "  ✅ Auth refreshed: $AUTH_REFRESH_COUNT times"

    echo ""
    echo "Next steps:"
    echo "  1. Review dashboard: open project_ape_dashboard.html"
    echo "  2. Check NotebookLM workspaces"
    echo "  3. If successful, run with all clients in vars.py"

else
    echo "❌ Deep mode failed with exit code: $EXIT_CODE"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check logs: tail -100 pipeline_deep_execution.log"
    echo "  2. Look for rate limit errors: grep 'RateLimitError' pipeline_deep_execution.log"
    echo "  3. Check auth status: grep 'Auth' pipeline_deep_execution.log | tail -20"
    echo "  4. Review RATE_LIMIT_FIX.md for tuning options"
fi

echo ""
echo "========================================================================="
