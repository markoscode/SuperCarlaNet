#!/bin/bash
# Clean CARLA shutdown using tracked PID

CARLA_PID_FILE="/tmp/carla.pid"

if [ ! -f "$CARLA_PID_FILE" ]; then
    echo "⚠️  No PID file found at $CARLA_PID_FILE"
    echo "CARLA may not have been started with start_carla.sh"
    echo ""
    echo "Attempting fallback kill..."
    pkill -9 -f "CarlaUE4-Linux-Shipping"
    pkill -9 -f "CarlaUE4.sh"
    exit 0
fi

CARLA_PID=$(cat "$CARLA_PID_FILE")

if ! ps -p "$CARLA_PID" > /dev/null 2>&1; then
    echo "⚠️  CARLA process (PID: $CARLA_PID) is not running"
    rm -f "$CARLA_PID_FILE"
    echo "Cleaned up stale PID file"
    exit 0
fi

echo "Stopping CARLA (PID: $CARLA_PID)..."

# Try graceful shutdown first
kill -TERM "$CARLA_PID" 2>/dev/null
echo "Sent SIGTERM, waiting 5 seconds..."
sleep 5

# Check if still running
if ps -p "$CARLA_PID" > /dev/null 2>&1; then
    echo "CARLA still running, sending SIGKILL..."
    kill -9 "$CARLA_PID" 2>/dev/null
    sleep 2
fi

# Cleanup any remaining child processes
pkill -9 -f "CarlaUE4-Linux-Shipping" 2>/dev/null
pkill -9 -f "CarlaUE4.sh" 2>/dev/null

# Check if successfully killed
if ps -p "$CARLA_PID" > /dev/null 2>&1; then
    STATE=$(ps -o state= -p "$CARLA_PID")
    if [ "$STATE" = "D" ]; then
        echo "❌ CARLA stuck in 'D' state (kernel I/O hang)"
        echo "This is a GPU driver issue - container restart required"
    else
        echo "⚠️  CARLA still running but should exit soon"
    fi
else
    echo "✅ CARLA stopped successfully"
    rm -f "$CARLA_PID_FILE"
fi
