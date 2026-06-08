#!/bin/bash
# Apply Optimizations to Deep Mode Script
# This script creates an optimized version of your deep mode pipeline

set -e

echo "========================================================================="
echo " APPLYING DEEP MODE OPTIMIZATIONS"
echo "========================================================================="
echo

# Check if new_deep_optimized.py exists
if [ ! -f "new_deep_optimized.py" ]; then
    echo "❌ Error: new_deep_optimized.py not found"
    echo "   Expected location: $(pwd)/new_deep_optimized.py"
    exit 1
fi

echo "✓ Found existing deep mode script"

# Create backup
BACKUP_FILE="new_deep_optimized.backup.$(date +%Y%m%d_%H%M%S).py"
cp new_deep_optimized.py "$BACKUP_FILE"
echo "✓ Created backup: $BACKUP_FILE"

# Create optimized version
OUTPUT_FILE="deep_v2_optimized.py"
echo "✓ Creating optimized version: $OUTPUT_FILE"

# Copy original file
cp new_deep_optimized.py "$OUTPUT_FILE"

# Apply optimizations using sed
echo "  Applying optimizations..."

# 1. Add imports at the top (after other imports)
sed -i.tmp '19a\
# ==== OPTIMIZATION: Import new modules ====\
from lib.sync_rate_limiter import SyncRateLimiter\
from lib.client_session import SessionPool\
from lib.async_url_validator import validate_and_filter_urls_sync, get_cache_stats\
' "$OUTPUT_FILE"

# 2. Replace deep_research_lock initialization
sed -i.tmp 's/deep_research_lock = threading.Semaphore(1)/# OPTIMIZED: Use rate limiter instead of lock\
deep_rate_limiter = SyncRateLimiter(requests_per_minute=10, burst=2)\
session_pool = SessionPool(storage_dir=SCRIPT_DIR)/' "$OUTPUT_FILE"

# Clean up temp files
rm -f "${OUTPUT_FILE}.tmp"

echo "✓ Optimizations applied"
echo
echo "========================================================================="
echo " WHAT WAS CHANGED"
echo "========================================================================="
echo
echo "1. Added optimization module imports"
echo "2. Replaced deep_research_lock with SyncRateLimiter"
echo "3. Added SessionPool for persistent storage"
echo
echo "NOTE: You still need to manually update these sections:"
echo "  - Replace 'with deep_research_lock:' with 'deep_rate_limiter.acquire()'"
echo "  - Replace storage file creation with session.get_storage_path()"
echo "  - Replace validate_and_filter_urls with validate_and_filter_urls_sync"
echo
echo "See OPTIMIZATION_IMPLEMENTATION_GUIDE.md for detailed instructions."
echo
echo "========================================================================="
echo " NEXT STEPS"
echo "========================================================================="
echo
echo "1. Review the changes in: $OUTPUT_FILE"
echo "2. Complete manual integration (see guide)"
echo "3. Test with 1-2 clients:"
echo "     python $OUTPUT_FILE"
echo
echo "Original backup saved as: $BACKUP_FILE"
echo "========================================================================="
