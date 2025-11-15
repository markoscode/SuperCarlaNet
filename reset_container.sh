#!/bin/bash
# Clean container reset script for Pylot visualization
# Usage: bash reset_container.sh

set -e

echo "========================================="
echo "Pylot Container Reset Script"
echo "========================================="

# Step 1: Stop and remove old container (or create with timestamp if stuck)
echo ""
echo "[1/5] Stopping and removing old container..."

# Try to stop/remove scn_pylot
if docker ps -a | grep -q "scn_pylot\$"; then
    docker stop -t 2 scn_pylot 2>/dev/null || true
    docker rm -f scn_pylot 2>/dev/null || true

    # Check if removal succeeded
    if docker ps -a | grep -q "scn_pylot\$"; then
        echo "⚠️  Old container stuck (D-state hang) - using new name: scn_pylot_$(date +%s)"
        CONTAINER_NAME="scn_pylot_$(date +%s)"
    else
        CONTAINER_NAME="scn_pylot"
        echo "✓ Old container removed"
    fi
else
    CONTAINER_NAME="scn_pylot"
    echo "✓ No existing container found"
fi

# Step 2: Create fresh container with X11 support
echo ""
echo "[2/5] Creating fresh container with X11 support..."
docker run -itd \
  --name $CONTAINER_NAME \
  --privileged \
  --gpus all \
  --network=host \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -p 20025:22 \
  erdosproject/pylot:latest

echo "✓ Container created: $CONTAINER_NAME"

# Step 3: Wait for container to initialize
echo ""
echo "[3/5] Waiting for container to initialize..."
sleep 5

# Step 4: Copy shutdown scripts to container
echo ""
echo "[4/5] Copying shutdown scripts to container..."
docker cp start_carla.sh $CONTAINER_NAME:/home/erdos/workspace/pylot/
docker cp stop_carla.sh $CONTAINER_NAME:/home/erdos/workspace/pylot/
docker cp stop_pylot.sh $CONTAINER_NAME:/home/erdos/workspace/pylot/
echo "✓ Shutdown scripts copied"

# Step 5: Set up SSH server in container
echo ""
echo "[5/5] Setting up SSH server..."
docker exec $CONTAINER_NAME bash -c '
  # Configure SSH to use port 20025 (host networking requires non-standard port)
  sudo sed -i "s/#Port 22/Port 20025/" /etc/ssh/sshd_config
  sudo sed -i "s/^Port 22/Port 20025/" /etc/ssh/sshd_config
  if ! grep -q "^Port 20025" /etc/ssh/sshd_config 2>/dev/null; then
    echo "Port 20025" | sudo tee -a /etc/ssh/sshd_config > /dev/null
  fi
  # Set password and start SSH
  echo "erdos:erdos" | sudo chpasswd
  sudo service ssh start
'
echo "✓ SSH server started on port 20025 (password: erdos)"

echo ""
echo "========================================="
echo "✅ Container reset complete!"
echo "========================================="
echo ""
echo "Container name: $CONTAINER_NAME"
echo ""
echo "Next steps:"
echo "1. In a NEW terminal on your Mac, connect with X11:"
echo "   ssh -Y -C dsanyal7@sysml-01.cc.gatech.edu"
echo ""
echo "2. SSH into the container:"
echo "   ssh -Y -p 20025 erdos@localhost"
echo "   Password: erdos"
echo ""
echo "3. Inside container, start CARLA:"
echo "   cd /home/erdos/workspace/pylot"
echo "   bash start_carla.sh"
echo "   sleep 30"
echo ""
echo "4. Run Pylot with visualization:"
echo "   source scripts/set_pythonpath.sh"
echo "   python3 pylot.py --flagfile=configs/detection.conf \\"
echo "     --visualize_rgb_camera --visualize_detected_obstacles \\"
echo "     --simulator_fps=10 --v=1"
echo ""
echo "5. When done (Ctrl+C in Pylot):"
echo "   bash stop_carla.sh"
echo "   pkill -9 python3"
echo ""
if [ "$CONTAINER_NAME" != "scn_pylot" ]; then
    echo "⚠️  NOTE: Previous container stuck - left as-is for admin cleanup"
    echo "   Your new container: $CONTAINER_NAME"
    echo ""
fi
