#!/bin/bash
# Clean start script - removes all state and starts fresh

echo "🧹 Cleaning all state files..."

# Stop any running processes
pkill -f "python.*fast.py" 2>/dev/null
pkill -f "notebooklm" 2>/dev/null

# Wait for processes to stop
sleep 2

# Remove state files
rm -f pipeline_state.json
rm -f pipeline_metrics.json
rm -f .storage_*.json
rm -f .temp_prompt_*.txt

# Remove lock files
rm -f ..storage*.lock
rm -f ..storage*.rotate.lock

echo "✓ State cleared"
echo ""
echo "🚀 Starting fresh pipeline..."
echo "   (You'll be prompted to login to NotebookLM)"
echo ""

# Start fresh - script will handle login
python fast.py
