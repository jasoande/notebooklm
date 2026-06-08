#!/bin/bash
# Kill all fast.py and notebooklm processes

echo "🛑 Stopping all Project APE processes..."

# Kill fast.py
pkill -f "python.*fast.py"
if [ $? -eq 0 ]; then
    echo "✓ Stopped fast.py"
fi

# Kill deep.py
pkill -f "python.*deep.py"
if [ $? -eq 0 ]; then
    echo "✓ Stopped deep.py"
fi

# Kill any lingering notebooklm processes
pkill -f "notebooklm"
if [ $? -eq 0 ]; then
    echo "✓ Stopped notebooklm processes"
fi

# Wait a moment for cleanup
sleep 1

# Check if anything is still running
if pgrep -f "python.*fast.py" > /dev/null; then
    echo "⚠️  Force killing remaining fast.py processes..."
    pkill -9 -f "python.*fast.py"
fi

if pgrep -f "notebooklm" > /dev/null; then
    echo "⚠️  Force killing remaining notebooklm processes..."
    pkill -9 -f "notebooklm"
fi

echo "✓ All processes stopped"
