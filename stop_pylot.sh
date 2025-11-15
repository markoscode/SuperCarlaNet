#!/bin/bash
# Clean shutdown helper for Pylot visualization
# Usage: Run this AFTER Ctrl+C in Pylot terminal
# Or: docker exec scn_pylot bash /home/erdos/workspace/pylot/stop_pylot.sh

echo "Stopping Pylot visualization..."
echo ""

# Step 1: Try graceful shutdown first (CRITICAL to prevent D-state)
echo "[1/5] Attempting graceful CARLA shutdown (SIGTERM)..."
pkill -TERM -f "CarlaUE4-Linux-Shipping" 2>/dev/null
pkill -TERM -f "CarlaUE4.sh" 2>/dev/null
pkill -TERM -f "run_simulator.sh" 2>/dev/null
echo "   Waiting 5 seconds for graceful shutdown..."
sleep 5

# Step 2: Force kill if still running (risk of D-state, but necessary)
echo "[2/5] Force killing CARLA if still running..."
pkill -9 -f "CarlaUE4.sh" 2>/dev/null
pkill -9 -f "CarlaUE4-Linux-Shipping" 2>/dev/null
pkill -9 -f "run_simulator.sh" 2>/dev/null
killall -9 CarlaUE4-Linux-Shipping 2>/dev/null
sleep 1

# Step 3: Kill Python processes (try graceful first)
echo "[3/5] Killing Python/Pylot processes..."
pkill -TERM python3 2>/dev/null
pkill -TERM -f pylot.py 2>/dev/null
sleep 2
# Force kill remaining
pkill -9 python3 2>/dev/null
pkill -9 -f pylot.py 2>/dev/null
sleep 1

# Find and report stuck processes (D state and zombies)
echo "[4/5] Checking for stuck processes..."
DEFUNCT=$(ps aux | grep '<defunct>' | grep -v grep | wc -l)
DSTATE=$(ps aux | awk '$8 ~ /D/ {print $0}' | grep -E "(CarlaUE4|python)" | wc -l)

if [ "$DEFUNCT" -gt 0 ]; then
    echo "⚠️  Found $DEFUNCT zombie processes (harmless, will be cleaned up)"
fi

if [ "$DSTATE" -gt 0 ]; then
    echo "⚠️  Found $DSTATE processes in 'D' state (kernel I/O hang - requires container restart)"
    ps aux | awk '$8 ~ /D/ {print $0}' | grep -E "(CarlaUE4|python)"
fi

# Verify clean shutdown
echo "[5/5] Verifying shutdown..."
REMAINING=$(ps aux | grep -E "(python|CarlaUE4)" | grep -v grep | grep -v stop_pylot | grep -v '<defunct>' | awk '$8 !~ /D/')

if [ -z "$REMAINING" ]; then
    if [ "$DEFUNCT" -eq 0 ] && [ "$DSTATE" -eq 0 ]; then
        echo ""
        echo "✅ Clean shutdown complete - no processes remaining"
    else
        echo ""
        echo "⚠️  Shutdown complete, but some processes are stuck:"
        if [ "$DEFUNCT" -gt 0 ]; then
            echo "   - $DEFUNCT zombie processes (will be auto-cleaned)"
        fi
        if [ "$DSTATE" -gt 0 ]; then
            echo "   - $DSTATE processes in 'D' state (REQUIRES CONTAINER RESTART)"
            echo ""
            echo "❌ Container is in broken state. Run: bash reset_container.sh"
        fi
    fi
else
    echo ""
    echo "⚠️  WARNING: Some processes still running:"
    echo "$REMAINING"
    echo ""
    echo "❌ Container may be in broken state. Run: bash reset_container.sh"
fi

echo ""
