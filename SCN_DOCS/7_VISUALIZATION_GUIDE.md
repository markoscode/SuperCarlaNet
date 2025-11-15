# Real-Time Visualization Guide - Seeing Your AV Drive

**Purpose:** Step-by-step guide to set up real-time visualization of Pylot's AV pipeline, showing camera feeds with bounding boxes, trajectories, and pipeline state.

---

## What You'll See

When working, you get a **pygame window** displaying:
- ✅ Live camera feed from the car's perspective
- ✅ Bounding boxes around detected objects (cars, pedestrians)
- ✅ Text overlay: speed, steering angle, position, FPS
- ✅ Real-time updates as the car drives autonomously

**Controls:**
- Press **'n'**: Cycle through visualization modes (RGB camera → detected obstacles → tracked objects → predicted trajectories → waypoints)
- Press **ESC** or **Ctrl+C**: Exit

---

## Prerequisites

### On Your Local Machine (Laptop/Desktop)

**Mac Users:**
1. Install **XQuartz** (X11 server for Mac):
   ```bash
   # Using Homebrew (recommended):
   brew install --cask xquartz

   # Or download from: https://www.xquartz.org/
   ```

2. **Log out and log back in** (or restart) after installing XQuartz

3. Start XQuartz manually (first time only):
   ```bash
   open -a XQuartz
   ```
   You should see "XQuartz" in your menu bar.

**Linux Users:**
- X11 should work out of the box
- Ensure you have `xauth` installed: `sudo apt-get install xauth`

**Windows Users:**
- Install **MobaXterm** (has built-in X server): https://mobaxterm.mobatek.net/
- Or install **VcXsrv**: https://sourceforge.net/projects/vcxsrv/

---

## Setup Process

### Step 1: Connect with X11 Forwarding

**From your local machine, SSH to GPU server with X11 enabled:**

```bash
# Mac/Linux:
ssh -Y -C username@gpu-server-address

# -Y: Enable trusted X11 forwarding (required for Mac)
# -C: Compress data (faster graphics over network)

# Example:
ssh -Y -C dsanyal7@sysml-01.cc.gatech.edu
```

**Verify X11 is working:**
```bash
echo $DISPLAY      # Should show "localhost:10.0" or similar
xeyes              # Should pop up a window with eyes following your mouse
```

If `$DISPLAY` is empty or `xeyes` doesn't work, **stop here** and troubleshoot:
- Reconnect with `-Y` flag (Mac requires trusted forwarding)
- Ensure XQuartz is running on Mac
- Check SSH server allows X11: `grep X11Forwarding /etc/ssh/sshd_config` (should say "yes")

---

### Step 2: Create Container with X11 Support

**On the GPU server, use the automated reset script:**

```bash
# Navigate to SuperCarlaNet directory:
cd /path/to/SuperCarlaNet

# Run automated reset script (handles everything):
bash reset_container.sh
```

**The script automatically:**
- ✅ Stops and removes old container (if exists)
- ✅ Creates fresh container with X11 and host networking
- ✅ Copies shutdown scripts (start_carla.sh, stop_carla.sh, stop_pylot.sh)
- ✅ Configures SSH server on port 20025
- ✅ Sets erdos password to "erdos"

---

### Step 3: SSH into Container with X11 (CRITICAL!)

**Why this step is necessary:** Direct `docker exec` doesn't properly forward X11 through SSH tunnels. We need to SSH *into* the container to establish proper X11 forwarding.

**SSH into the container with X11 forwarding:**
```bash
ssh -Y -p 20025 erdos@localhost
# Password: erdos
```

**You should see your prompt change to:** `erdos@<container-id>:~$`

**Verify X11 works inside container:**
```bash
echo $DISPLAY
# Should show: <container-id>:10.0 (e.g., 09f375df0603:10.0)

# Test with xeyes:
xeyes  # Should pop up window on your Mac/local machine
# Press Ctrl+C to close
```

---

### Step 4: Start CARLA Simulator

**Inside the container SSH session (from Step 3):**

```bash
cd /home/erdos/workspace/pylot

# Verify CARLA_HOME is set:
echo $CARLA_HOME
# Should show: /home/erdos/workspace/pylot/dependencies/CARLA_0.9.10.1

# Start CARLA in background:
nohup bash scripts/run_simulator.sh > /tmp/carla.log 2>&1 &

# Wait for CARLA to initialize (30 seconds):
sleep 30

# Verify CARLA is running:
ps aux | grep CarlaUE4 | grep -v grep
# Should show 2 CarlaUE4 processes (shell + actual simulator)
```

**If CARLA fails to start:**
```bash
# Check the log:
cat /tmp/carla.log

# Common issue: CARLA_HOME not set
# Fix: Exit and reconnect, or manually:
export CARLA_HOME=/home/erdos/workspace/pylot/dependencies/CARLA_0.9.10.1
```

---

### Step 5: Run Pylot with Visualization

**Inside the container (same SSH session):**

```bash
cd /home/erdos/workspace/pylot
source scripts/set_pythonpath.sh

# Run with visualization (reduced frame rate to prevent queue buildup):
python3 pylot.py \
  --flagfile=configs/detection.conf \
  --visualize_rgb_camera \
  --visualize_detected_obstacles \
  --simulator_fps=10 \
  --v=1 \
  --log_file_name=pylot_viz.log
```

**Important:** `--simulator_fps=10` reduces frame rate from default 20 FPS to 10 FPS, preventing "operator events queued" warnings. Detection + visualization over SSH cannot keep up with 20 FPS.

**A pygame window should pop up on your local machine!**

---

## Available Visualization Flags

All flags can be combined. Add to your Pylot command:

```bash
# Camera and sensor data:
--visualize_rgb_camera              # Show main camera feed
--visualize_depth_camera            # Show depth map
--visualize_lidar                   # Show LiDAR point cloud
--visualize_imu                     # Show IMU data overlay
--visualize_pose                    # Show vehicle pose

# Perception outputs:
--visualize_detected_obstacles      # Show bounding boxes on detections
--visualize_detected_traffic_lights # Show traffic light detections
--visualize_detected_lanes          # Show lane markings
--visualize_tracked_obstacles       # Show tracked object IDs + trajectories
--visualize_segmentation            # Show semantic segmentation overlay

# Planning outputs:
--visualize_waypoints               # Show planned waypoints
--visualize_prediction              # Show predicted trajectories
```

**Example - Full visualization:**
```bash
python3 pylot.py \
  --flagfile=configs/detection.conf \
  --visualize_rgb_camera \
  --visualize_detected_obstacles \
  --visualize_detected_lanes \
  --visualize_waypoints \
  --simulator_fps=10 \
  --v=1
```

**Performance tuning flags:**
```bash
--simulator_fps=10              # Reduce from default 20 FPS (prevents queue buildup)
--simulator_fps=5               # Even lower for very slow connections
--camera_image_width=800        # Reduce from default 1920 (faster rendering)
--camera_image_height=600       # Reduce from default 1080
```

---

## What Didn't Work (Troubleshooting Guide)

### ❌ Approach 1: Direct `docker exec` with X11
```bash
docker exec -it scn_pylot python3 pylot.py --visualize_rgb_camera
```

**Error:** `Fatal Python error: Segmentation fault` or `pygame.error: No available video device`

**Why it failed:**
- `docker exec` doesn't inherit SSH X11 forwarding tunnel
- Pygame can't access X11 display through the SSH tunnel
- Container's `$DISPLAY` points to wrong X11 socket

### ❌ Approach 2: Shared X11 Socket (Local X Server)
```bash
docker run -v /tmp/.X11-unix:/tmp/.X11-unix ...
xhost +local:docker
```

**Error:** `xhost: must be on local machine to add or remove hosts`

**Why it failed:**
- Works only if X server runs *locally* on GPU server
- We're using *remote* X11 forwarding (XQuartz on Mac → SSH → GPU server → Container)
- No actual X server running on GPU server (headless machine)

### ✅ What Works: Nested SSH with X11 Forwarding

**Why it works:**
1. First SSH hop: Mac → GPU server (establishes X11 tunnel)
2. Second SSH hop: GPU server → Container (extends X11 tunnel)
3. Container now has proper `$DISPLAY` pointing to SSH tunnel
4. Pygame connects through SSH tunnel → XQuartz on Mac

**Key insight:** Each SSH hop must explicitly forward X11 with `-Y` flag.

---

## Other Monitoring Options (Non-GUI)

If X11 is too complex, alternatives exist:

### 1. DOT Graph (Pipeline Architecture)

**Automatically generated** when Pylot runs:

```bash
# After running Pylot, copy graph:
docker cp scn_pylot:/home/erdos/workspace/pylot/pylot.dot ./

# Visualize:
dot -Tpng pylot.dot -o pylot_graph.png
# Or upload to: http://viz-js.com/
```

Shows operator dataflow graph (nodes = operators, edges = streams).

### 2. Chrome Trace (Performance Timeline)

```bash
python3 pylot.py \
  --flagfile=configs/detection.conf \
  --profile_file_name=pylot_profile.json

# Copy trace file:
docker cp scn_pylot:/home/erdos/workspace/pylot/pylot_profile.json ./

# Open in Chrome:
# chrome://tracing → Load → Select JSON file
```

Shows timeline of operator execution, watermarks, message passing.

### 3. Log-Based Timing Analysis

Uses SCN timing infrastructure (no visualization needed):

```bash
python3 pylot.py --flagfile=configs/detection.conf --v=1 --log_file_name=pylot.log

# Analyze offline:
docker exec scn_pylot bash -c 'cd /home/erdos/workspace/pylot && \
  bash scripts/scn_quick_timing_analysis.sh pylot.log timing_results 10'

# View results:
docker cp scn_pylot:/home/erdos/workspace/pylot/timing_results ./
cat timing_results/tier2_statistics.txt
```

See [3_DATA_COLLECTION.md](3_DATA_COLLECTION.md) for full analysis workflow.

---

## Quick Reference Commands

**Complete workflow:**

```bash
# 1. Mac/Linux → GPU server (with X11):
ssh -Y -C dsanyal7@sysml-01.cc.gatech.edu

# 2. Create container:
cd /home/dsanyal7/marko/SuperCarlaNet && bash reset_container.sh

# 3. SSH into container (with X11):
ssh -Y -p 20025 erdos@localhost  # Password: erdos

# 4. Start CARLA + Run Pylot:
cd /home/erdos/workspace/pylot
bash start_carla.sh && sleep 30
source scripts/set_pythonpath.sh
python3 pylot.py --flagfile=configs/detection.conf \
  --visualize_rgb_camera --visualize_detected_obstacles \
  --simulator_fps=10 --v=1

# 5. When done (Ctrl+C then):
bash stop_pylot.sh  # Graceful SIGTERM → SIGKILL, detects D-state
```

---

## 🚨 Stopping Visualization (CRITICAL)

**Use the automated script:**

```bash
# After Ctrl+C in Pylot:
bash stop_pylot.sh
```

**What stop_pylot.sh does (prevents D-state hangs):**
1. Sends **SIGTERM** to CARLA (graceful - allows GPU cleanup)
2. Waits 5 seconds for clean shutdown
3. Sends SIGKILL only if still running
4. Kills Python processes (SIGTERM first, then SIGKILL)
5. Detects D-state hangs and warns you

**⚠️ NEVER manually use `pkill -9 CarlaUE4`** - causes unkillable D-state (GPU driver stuck in kernel). See [ROOT_CAUSE_ANALYSIS.md](../ROOT_CAUSE_ANALYSIS.md) for technical details.

### If D-State Detected

Script output will show:
```
⚠️  Found 1 processes in 'D' state (kernel I/O hang - requires container restart)
❌ Container is in broken state. Run: bash reset_container.sh
```

**Recovery:**
```bash
exit  # Leave container
cd /home/dsanyal7/marko/SuperCarlaNet && bash reset_container.sh
```

---

## Troubleshooting

**Problem:** `$DISPLAY` is empty after SSH
- **Fix:** Reconnect with `ssh -Y` (not `-X` on Mac)
- **Fix:** Ensure XQuartz is running: `open -a XQuartz`

**Problem:** `xeyes` doesn't pop up window
- **Fix:** Check SSH server config: `grep X11Forwarding /etc/ssh/sshd_config` (must say "yes")
- **Fix:** Restart XQuartz on Mac

**Problem:** Pygame segfault in container
- **Fix:** Don't use `docker exec` - must SSH into container

**Problem:** "No available video device"
- **Fix:** Verify `$DISPLAY` is set inside container: `echo $DISPLAY`
- **Fix:** Ensure you SSH'd into container with `-Y` flag

**Problem:** "Connection refused" when SSH to localhost:20025
- **Fix:** SSH may not be running or configured correctly in container
- **Fix:** Reconfigure SSH to use port 20025:
  ```bash
  docker exec scn_pylot bash -c '
    sudo sed -i "s/^Port 22/Port 20025/" /etc/ssh/sshd_config
    sudo service ssh restart
  '
  ```
- **Fix:** Or just run `bash reset_container.sh` to start fresh

**Problem:** "WARN: N operator events queued in lattice" warnings flooding terminal
- **Root cause:** Pipeline can't keep up with CARLA frame rate (detection + X11 overhead too slow)
- **Fix:** Add `--simulator_fps=10` flag (reduces from default 20 FPS)
- **Fix:** Lower further if still happening: `--simulator_fps=5`
- **Note:** This is expected with visualization over SSH - not a bug

**Problem:** CARLA won't start - "Exit 127" or "No such file or directory"
- **Root cause:** Not in correct directory or CARLA_HOME not set
- **Fix:** Always run CARLA commands from `/home/erdos/workspace/pylot`
- **Fix:** Verify: `echo $CARLA_HOME` (should show `/home/erdos/workspace/pylot/dependencies/CARLA_0.9.10.1`)

**Problem:** Pygame window is slow/laggy
- **Expected:** Graphics over SSH+X11 forwarding is slower than native
- **Tip:** Use `-C` flag for compression: `ssh -Y -C`
- **Tip:** Lower resolution: `--camera_image_width=800 --camera_image_height=600`
- **Tip:** Reduce frame rate: `--simulator_fps=5`

---

**Version:** 3.0
**Date:** 2025-11-15
**Validated On:** sysml-01.cc.gatech.edu (Ubuntu), Mac with XQuartz

**Changes in v3.0:**
- Fixed D-state hang bug (stop_pylot.sh now uses SIGTERM before SIGKILL)
- Removed wasteful SCN_DOCS copying to container
- Streamlined quick reference (4 commands instead of 8)
- Automated shutdown with stop_pylot.sh script

**Changes in v2.0:**
- Added automated reset_container.sh script
- Fixed host networking + SSH port 20025
- Added --simulator_fps=10 flag
