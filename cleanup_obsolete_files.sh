#!/bin/bash
#
# Cleanup Script for NotebookLM Directory
# Removes obsolete files, keeping only production-ready code
#
# Usage: bash cleanup_obsolete_files.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================================"
echo "  NotebookLM Directory Cleanup"
echo "========================================================================"
echo ""
echo "This script will remove obsolete files and keep only production code."
echo ""
echo "Files to be removed:"
echo "  - 6 old/deprecated script versions"
echo "  - 5 unused library modules"
echo "  - 3 utility scripts"
echo "  - 2 shell scripts"
echo "  - 4 outdated documentation files"
echo "  - All temporary files"
echo ""
echo "Total: ~25 files"
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup cancelled."
    exit 0
fi

echo ""
echo "Creating backup first..."

# Create backup
BACKUP_DIR="${SCRIPT_DIR}/../notebooklm_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r . "$BACKUP_DIR/"
echo "✅ Backup created: $BACKUP_DIR"
echo ""

echo "Removing obsolete files..."
echo ""

# Track removed files
REMOVED=0

# Function to safely remove file
remove_file() {
    if [ -f "$1" ]; then
        rm -f "$1"
        echo "  ✓ Removed: $1"
        REMOVED=$((REMOVED + 1))
    fi
}

# Remove old script versions
echo "1. Removing old script versions..."
remove_file "deep_v2_optimized.py"
remove_file "deep_v2_clean.py"
remove_file "new_deep_optimized.py"
remove_file "new_deep.py"
remove_file "deep_optimized_v2.py"
remove_file "deep_optimized_minimal.py"
echo ""

# Remove unused lib modules
echo "2. Removing unused library modules..."
remove_file "lib/checkpoint.py"
remove_file "lib/circuit_breaker.py"
remove_file "lib/config_loader.py"
remove_file "lib/rate_limiter.py"
remove_file "lib/session_manager.py"
echo ""

# Remove utility scripts
echo "3. Removing utility scripts..."
remove_file "pdf_consolidator.py"
remove_file "test_optimizations.py"
remove_file "apply_optimizations.sh"
echo ""

# Remove shell scripts
echo "4. Removing helper shell scripts..."
remove_file "clean_start.sh"
remove_file "kill_all.sh"
echo ""

# Remove outdated docs
echo "5. Removing outdated documentation..."
remove_file "OPTIMIZATION_IMPLEMENTATION_GUIDE.md"
remove_file "OPTIMIZATION_SUMMARY.md"
remove_file "RUN_OPTIMIZED_DEEP.md"
remove_file "SIMPLE_START.md"
echo ""

# Remove temp files
echo "6. Removing temporary files..."
TEMP_COUNT=0
for f in .temp_*; do
    if [ -f "$f" ]; then
        rm -f "$f"
        echo "  ✓ Removed: $f"
        TEMP_COUNT=$((TEMP_COUNT + 1))
        REMOVED=$((REMOVED + 1))
    fi
done
if [ $TEMP_COUNT -eq 0 ]; then
    echo "  (no temp files found)"
fi
echo ""

# Clean up pycache
echo "7. Cleaning Python cache..."
if [ -d "lib/__pycache__" ]; then
    rm -rf lib/__pycache__
    echo "  ✓ Removed: lib/__pycache__"
fi
if [ -d "__pycache__" ]; then
    rm -rf __pycache__
    echo "  ✓ Removed: __pycache__"
fi
echo ""

echo "========================================================================"
echo "  Cleanup Complete!"
echo "========================================================================"
echo ""
echo "Summary:"
echo "  Files removed: $REMOVED"
echo "  Backup location: $BACKUP_DIR"
echo ""
echo "Production files remaining:"
echo ""

# List remaining Python files
echo "Python Scripts:"
ls -1 *.py 2>/dev/null | grep -v "^\." | sed 's/^/  - /'
echo ""

echo "Prompt Files:"
ls -1 *.txt 2>/dev/null | grep -v "^\." | head -11 | sed 's/^/  - /'
echo ""

echo "Documentation:"
ls -1 *.md 2>/dev/null | sed 's/^/  - /'
echo ""

echo "Library Modules:"
ls -1 lib/*.py 2>/dev/null | grep -v "__pycache__" | grep -v "/__" | sed 's/^/  - /'
echo ""

echo "========================================================================"
echo ""
echo "✅ Your directory is now clean and production-ready!"
echo ""
echo "To verify everything still works:"
echo "  python fast.py"
echo "  python deep_v3_optimized.py"
echo ""
echo "To restore from backup if needed:"
echo "  cp -r $BACKUP_DIR/* ."
echo ""
