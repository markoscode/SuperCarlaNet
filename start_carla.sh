#!/bin/bash
# Better CARLA startup wrapper
# Tracks PID and enables proper cleanup

CARLA_PID_FILE="/tmp/carla.pid"
CARLA_LOG="/tmp/carla.log"

# Check if CARLA is already running
if [ -f "$CARLA_PID_FILE" ]; then
    OLD_PID=$(cat "$CARLA_PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "⚠️  CARLA is already running (PID: $OLD_PID)"
        echo "Kill it first: kill -9 $OLD_PID"
        exit 1
    else
        rm -f "$CARLA_PID_FILE"
    fi
fi

# Verify CARLA_HOME is set
if [ -z "$CARLA_HOME" ]; then
    echo "❌ \$CARLA_HOME is not set"
    echo "Are you in the correct directory?"
    exit 1
fi

echo "Starting CARLA simulator..."
echo "Log: $CARLA_LOG"

# Start CARLA and capture PID
SDL_VIDEODRIVER=offscreen ${CARLA_HOME}/CarlaUE4.sh \
    -opengl -windowed -ResX=800 -ResY=600 \
    -carla-server -world-port=2000 \
    -benchmark -fps=20 -quality-level=Epic \
    > "$CARLA_LOG" 2>&1 &

CARLA_PID=$!
echo $CARLA_PID > "$CARLA_PID_FILE"

echo "✅ CARLA started (PID: $CARLA_PID)"
echo "   PID file: $CARLA_PID_FILE"
echo ""
echo "Wait 30 seconds for initialization:"
echo "   sleep 30"
echo ""
echo "To stop CARLA cleanly:"
echo "   kill -TERM $CARLA_PID"
echo "   # Or use stop_carla.sh"
