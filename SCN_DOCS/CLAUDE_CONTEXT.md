# Context for Claude: SCN Timing System

**Purpose:** Quick context for future Claude sessions working with this codebase.

---

## What This Is

SCN timing instrumentation for Pylot AV pipeline. Measures:
- **Tier 2:** Per-operator response time (13 operators)
- **Tier 3:** End-to-end sensor→actuator latency
- **Overhead:** System overhead (message passing, scheduling)

**Based on:** D3 paper (EuroSys '22) - Dynamic Deadline-Driven execution model for AVs.

---

## 🚨 CRITICAL: Zombie Process Prevention

**ALWAYS use graceful shutdown for Pylot visualization, or the container WILL become unusable.**

### The Zombie Process Problem

**What happens if you Ctrl+C Pylot improperly:**
1. Parent Python process exits, but ERDOS operator executors keep running
2. Each operator executor becomes a zombie process
3. Zombies continue processing queued messages at 100% CPU
4. Multiple runs create 20+ zombie processes consuming 10+ GB RAM
5. When CARLA starts, ALL zombies connect and flood logs simultaneously
6. Terminal becomes unusable with spam from dozens of processes

**Real incident (Nov 12, 2024):**
- 20+ zombie Pylot processes found running
- 3 processes pegged at 99.9% CPU for 4199+ hours
- Total RAM consumption: 10+ GB
- Terminal spam was unfixable without full container reset

### Prevention: ALWAYS Exit Gracefully

**Correct shutdown order:**

```bash
# ALWAYS use this procedure (ESC often doesn't work):

# 1. Ctrl+C in Pylot terminal
# 2. IMMEDIATELY run BOTH kill commands:
pkill -9 CarlaUE4 && pkill -9 python3

# 3. Verify everything is dead:
ps aux | grep -E "(python|CarlaUE4)" | grep -v grep
# Should return NOTHING

# 4. If any processes remain:
pkill -9 -f pylot.py
```

**Why you MUST kill python3:**
- Killing only CARLA leaves ERDOS operator executors running
- These Python processes become zombies at 100% CPU
- They accumulate with each run (20+ zombies possible)
- **Killing CARLA alone is NOT enough** - this was the root cause of the Nov 12 incident

**If container becomes zombie-infested:**

```bash
# On GPU server:
cd /home/dsanyal7/marko/SuperCarlaNet
bash reset_container.sh  # Automated clean reset
```

The reset script:
1. Stops/removes old container
2. Creates fresh container with X11 support
3. Copies SCN_DOCS
4. Sets up SSH server
5. Ready for new SSH connection

**Never try to fix zombie processes manually** - just reset the container.

---

## Critical Bug Fix Applied

**File:** `pylot/utils/scn_timing.py:100-107`

**Issue:** Decorator crashed on watermark callbacks (watermark IS timestamp, not msg.timestamp).

**Fix:**
```python
# Before (BROKEN):
tracker.start_operator(stage, msg.timestamp)

# After (FIXED):
timestamp = msg.timestamp if hasattr(msg, 'timestamp') else msg
tracker.start_operator(stage, timestamp)
```

**Why:** ERDOS has two callback types:
- Message callbacks: `on_msg(self, msg, ...)` where `msg.timestamp` exists
- Watermark callbacks: `on_watermark(self, timestamp, ...)` where first arg IS the timestamp

---

## Docker Setup Required

**Critical:** Vanilla pylot Docker has `utils.py` as a file, not package. Must convert:

```bash
docker exec scn_pylot bash -c "mkdir -p /home/erdos/workspace/pylot/pylot/utils && \
  cp /home/erdos/workspace/pylot/pylot/utils.py /home/erdos/workspace/pylot/pylot/utils/__init__.py"
```

This allows both:
- `from pylot.utils import Location` (original utils.py functionality)
- `from pylot.utils.scn_timing import track_operator_time` (new SCN files)

---

## Execution Results (Validated)

**Setup:** CARLA 0.9.10.1, detection.conf, Faster-RCNN, 250 pedestrians, 20 vehicles

**Data Collected:** 1,523 timing measurements, 5-6 min runtime

**Results:**
| Operator | Samples | Mean | P99 | % of Total |
|----------|---------|------|-----|------------|
| Detection | 660 | 248ms | 274ms | 92.8% |
| Planning | 416 | 19ms | 27ms | 7.1% |
| Behavior Planning | 417 | 0.4ms | 0.9ms | 0.1% |

**Key Finding:** Detection is the bottleneck (93% of operator time).

**Note:** No Tier 3 data - detection.conf uses `simulator_auto_pilot`, bypassing control pipeline. For Tier 3, use configs with PID/MPC control.

---

## Comparison with Pylot-Remote

**Pylot-remote** (research fork):
- Measures algorithm time only (incorrect per D3)
- 9 operators instrumented
- No Tier 3, no system overhead analysis
- Hard-coded timing in operators

**Our implementation** (superior):
- Measures operator response time (D3-compliant)
- 13 operators instrumented (100% coverage)
- Tier 2 + Tier 3 + overhead analysis
- Configuration-driven (central registry)
- One-command analysis script

**Critical difference:**
```python
# Pylot-remote (WRONG):
start = time.time()
result = model.inference(frame)  # Only algorithm time
logger.info(f'TIMING {(time.time()-start)*1000}ms')

# Our approach (CORRECT):
@track_operator_time('detection')
def on_msg_camera_stream(self, msg, stream):
    # Entire callback timed: algorithm + message passing + overhead
    result = model.inference(frame)
    stream.send(result)
```

---

## Files Structure

**Code (2 files):**
- `pylot/utils/scn_timing.py` - Core timing tracker (fixed decorator)
- `pylot/utils/scn_timing_config.py` - Operator registry

**Analysis (3 files):**
- `scripts/scn_analyze_timing.py` - Generate statistics + plots
- `scripts/scn_plot_cumulative_cdf.py` - Cumulative CDF
- `scripts/scn_quick_timing_analysis.sh` - One-command wrapper

**Operators (14 modified):**
- Detection (4), Segmentation (1), Tracking (1), Localization (1)
- Prediction (2), Planning (2), Control (2), Camera driver (1)

**Docs (5 core + this):**
- 0_START_HERE.md - Entry point
- 1_SETUP_AND_RUN.md - Docker setup + running
- 2_TECHNICAL_DESIGN.md - Architecture
- 3_DATA_COLLECTION.md - Analysis workflow
- 4_REFERENCE.md - API reference

---

## Codebase Navigation Shortcuts

**Entry point:** `pylot.py:221` generates `pylot.dot` (pipeline visualization)

**Pipeline construction pattern:**
- High-level: `pylot/component_creator.py` (chains multi-operator components)
- Low-level: `pylot/operator_creator.py` (instantiates single operators via `erdos.connect()`)
- Main flow: `pylot.py:130-179` (parallel detection layers → sequential planning chain)

**Key operator locations:**
- Detection: `pylot/perception/detection/detection_operator.py:93-150` (`on_msg_camera_stream`)
- Location finder: `pylot/perception/detection/obstacle_location_finder_operator.py:67-130` (2D→3D via LiDAR frustum)
- Tracking: `pylot/perception/tracking/*_tracker_operator.py` (5 variants: SORT, DeepSORT, DaSiamRPN, CenterTrack, QDTrack)
- Prediction: `pylot/prediction/linear_predictor_operator.py` (8ms, constant velocity) vs `pylot/prediction/r2p2_predictor_operator.py` (50ms, scene-aware)
- Planning: `pylot/planning/planning_operator.py:58-61` (watermark sync on 6 inputs)
- Control: `pylot/control/pid_control_operator.py:94` (Tier 3 exit point: `mark_pipeline_stage('actuator_output')`)

**Configuration system:**
- Master flags: `pylot/flags.py` (pipeline switches, deadlines, execution modes)
- Module flags: `pylot/{perception,planning,control}/flags.py` (model paths, algorithm params)
- Config files: `configs/*.conf` (23 total)
  - **challenge.conf**: Paper §7 (50km CARLA challenge, Faster-RCNN + SORT + Linear + Waypoint + PID)
  - **e2e.conf**: Full pipeline baseline (perfect tracking/segmentation, real detection/lanes/TL)
  - **detection.conf**: Fig 2a experiments (EDet1-7 variants, autopilot - no Tier 3)
  - **tracking.conf**: Fig 2b experiments (SORT/DeepSORT/DaSiamRPN comparisons)

**Runtime-accuracy tradeoffs (from paper data):**
- Detection: Faster-RCNN (50ms, mAP 40) → EDet-D2 (45ms, mAP 43) → EDet-D6 (250ms, mAP 52)
- Tracking: SORT (12ms, Kalman+Hungarian) → QDTrack (60ms, quasi-dense matching)
- Prediction: Linear (8ms, physics) → R2P2 (50ms, GAN-based)
- Planning: Waypoint (5ms, follow route) → Hybrid A* (200ms, grid search)

**Synchronization mechanism:**
- `erdos.add_watermark_callback([input_streams], [output_streams], callback)` ensures all inputs at same timestamp available before execution
- Planning waits for: pose, prediction, obstacles, lanes, time_to_decision, route (6 streams)
- Control waits for: pose, waypoints (2 streams)

**LiDAR+Camera fusion flow:**
1. Detection: 2D bbox in image (`detection_operator.py`)
2. Project: 2D→3D frustum using camera intrinsics (`obstacle_location_finder_operator.py:82-95`)
3. Filter: LiDAR points inside frustum
4. Cluster: 3D centroid from point cloud
5. Transform: World coordinates via vehicle pose
6. Output: `Obstacle` with 3D location for planning

**Perfect bypass modes (simulator ground truth):**
- `--perfect_obstacle_detection` (bypasses detection + location finder)
- `--perfect_obstacle_tracking` (bypasses tracker)
- `--perfect_segmentation` (bypasses semantic segmentation)
- `--perfect_traffic_light_detection` (bypasses TL detector)
- `--simulator_localization` (bypasses SLAM)

**Common pitfalls:**
- **Watermark vs message callbacks**: First arg is either `msg` (with `.timestamp`) or `timestamp` directly (decorator handles both)
- **No Tier 3 with autopilot**: Configs using `--simulator_auto_pilot` skip control operator, can't measure E2E latency
- **Module ordering matters**: Location finder MUST follow detection (needs 2D bboxes), tracking MUST follow location finder (needs 3D obstacles)
- **Config file stacking**: Later flags override earlier ones (e.g., `--flagfile=base.conf --obstacle_detection_model_names=ssd` changes base model)

---

## Quick Commands

```bash
# Setup container
docker run -itd --gpus all --shm-size=16g --name scn_pylot erdosproject/pylot /bin/bash
# Copy files + fix utils (see 1_SETUP_AND_RUN.md for all steps)

# Run
docker exec scn_pylot bash -c 'cd /home/erdos/workspace/pylot && \
  source scripts/set_pythonpath.sh && \
  python3 pylot.py --flagfile=configs/detection.conf --v=1 --log_file_name=pylot.log'

# Analyze
docker exec scn_pylot bash -c 'cd /home/erdos/workspace/pylot && \
  bash scripts/scn_quick_timing_analysis.sh pylot.log timing_results 10'

# Copy results
docker cp scn_pylot:/home/erdos/workspace/pylot/timing_results ./
```

---

## Real-Time Visualization (Critical Technical Notes)

**For Agents:** Visualization setup is COMPLEX due to X11 forwarding over SSH. Read carefully.

### Architecture Understanding

**User context:** Mac/Windows → SSH → GPU server → Docker container → Pylot (pygame)
**Display chain:** XQuartz (Mac) ← SSH X11 tunnel ← GPU server ← SSH tunnel ← Container

**Key insight:** X11 must be forwarded through TWO SSH hops.

### What DOES NOT WORK (and Why)

#### ❌ Approach 1: `docker exec` with visualization flags
```bash
docker exec -it scn_pylot python3 pylot.py --visualize_rgb_camera
```

**Errors:**
- `Fatal Python error: Segmentation fault` (pygame trying hardware acceleration)
- `pygame.error: No available video device`

**Root cause:**
- `docker exec` launches process INSIDE container but doesn't establish X11 forwarding
- Even with `-e DISPLAY=$DISPLAY` and volume mounts, pygame can't access the SSH X11 tunnel
- The DISPLAY variable points to a socket that doesn't exist in container's namespace

**Technical detail:** SSH X11 forwarding creates a proxy X server on `localhost:10.0` (forwarded through SSH). Docker exec doesn't inherit this SSH tunnel - it only has access to the container's network namespace.

#### ❌ Approach 2: `xhost +local:docker` on remote server
```bash
xhost +local:docker  # On GPU server
docker run -v /tmp/.X11-unix:/tmp/.X11-unix ...
```

**Error:** `xhost: must be on local machine to add or remove hosts`

**Root cause:**
- `xhost` modifies X server access control list
- Only works if X server runs LOCALLY on the GPU server
- In our case, X server is XQuartz running on user's Mac (via SSH forwarding)
- GPU server has NO actual X server (headless)
- `/tmp/.X11-unix/` on GPU server is EMPTY (no local X sockets)

**Technical detail:** This approach works for local Docker (laptop running X11 locally), NOT for remote SSH X11 forwarding.

#### ❌ Approach 3: Setting SDL environment variables
```bash
export SDL_VIDEODRIVER=x11
export SDL_AUDIODRIVER=dummy
python3 pylot.py --visualize_rgb_camera
```

**Error:** Still `No available video device`

**Root cause:**
- SDL environment variables force pygame to use X11 backend (vs Wayland)
- Doesn't fix the fundamental issue: pygame can't ACCESS the X11 display through SSH tunnel
- SDL correctly tries to use X11, but the DISPLAY socket is unreachable

### ✅ What WORKS: Nested SSH with X11 Forwarding

**Working command sequence:**
```bash
# 1. User's terminal (with X11 forwarding to GPU server):
ssh -Y -C user@gpu-server  # DISPLAY=localhost:10.0

# 2. From GPU server, SSH into container (extends X11 tunnel):
ssh -Y -p 20025 erdos@localhost  # DISPLAY=<container-id>:10.0

# 3. Inside container, run Pylot:
python3 pylot.py --visualize_rgb_camera  # Works!
```

**Why this works:**
1. First SSH hop (Mac → GPU server): SSH creates X11 proxy on GPU server listening on localhost:10.0
2. Second SSH hop (GPU server → Container): SSH creates ANOTHER X11 proxy inside container
3. Container's DISPLAY=`<container-id>:10.0` points to this second proxy
4. Chain: pygame → container X11 proxy → GPU X11 proxy → SSH tunnel → XQuartz on Mac

**Critical flags:**
- `-Y` (not `-X`) on Mac: Trusted X11 forwarding (required for Mac/XQuartz)
- `-C`: Compression (speeds up graphics over network)

**Container must have SSH server:**
```bash
docker exec scn_pylot bash -c 'sudo service ssh start'
docker exec scn_pylot bash -c 'echo "erdos:erdos" | sudo chpasswd'  # Set password
```

**Port must be exposed:** `-p 20025:22` in docker run

### Debugging Strategy for Agents

**When visualization doesn't work, check in order:**

**1. Verify user has X11 forwarding to GPU server:**
```bash
# In user's SSH session to GPU server:
echo $DISPLAY  # Must show "localhost:10.0" or similar (NOT empty!)
xeyes          # Must pop up window on user's local machine
```
If empty/fails → User must reconnect with `ssh -Y -C` (Mac needs XQuartz installed)

**2. Verify container has DISPLAY set:**
```bash
docker exec scn_pylot bash -c 'echo $DISPLAY'
# Should show: localhost:10.0 (if docker run with -e DISPLAY=$DISPLAY)
```
If empty → Container wasn't created with `-e DISPLAY=$DISPLAY`

**3. Verify SSH into container establishes X11:**
```bash
ssh -Y -p 20025 erdos@localhost
echo $DISPLAY  # Must show: <container-id>:10.0 (e.g., 38dab7570269:10.0)
```
If empty → SSH server in container not configured for X11 forwarding
Check: `docker exec scn_pylot grep X11Forwarding /etc/ssh/sshd_config` (should be "yes")

**4. Test X11 inside container:**
```bash
# Inside container (after SSH):
DISPLAY=$DISPLAY xeyes  # Should pop up (if xeyes installed)
# Or test pygame directly:
python3 -c "import pygame; pygame.init(); print('Pygame OK')"
```

**5. Check CARLA is running:**
```bash
docker exec scn_pylot ps aux | grep CarlaUE4
```
If not running → `nohup bash scripts/run_simulator.sh > /tmp/carla.log 2>&1 &`

**6. Common pygame-specific issues:**
- **Segfault:** Usually hardware acceleration issue. Nested SSH fixes this.
- **No video device:** DISPLAY not set or unreachable.
- **Window appears but freezes:** Network latency. Use `-C` compression flag.

### Performance Considerations

**Visualization over SSH+X11 is SLOW:**
- Expected FPS: 10-15 (vs 30+ locally)
- Latency: 100-500ms for GUI updates
- Network bottleneck: Uncompressed graphics data over SSH

**CRITICAL: "operator events queued" warnings:**
- **Root cause:** Detection (100ms) + X11 overhead (50-100ms) = ~150-200ms per frame
- Pipeline can only process 5-7 FPS, but CARLA sends 20 FPS by default
- Queue builds up → thousands of events queued → terminal spam
- **Fix:** ALWAYS use `--simulator_fps=10` (or lower) with visualization

**Optimizations:**
- **REQUIRED:** `--simulator_fps=10` (reduces from default 20 FPS)
- Use `-C` flag for SSH compression
- Lower resolution: `--camera_image_width=800 --camera_image_height=600`
- Reduce visualization: Don't enable all `--visualize_*` flags at once
- Further reduce FPS if still seeing warnings: `--simulator_fps=5`
- Better network: Campus network > VPN > Home internet

**Command template with optimizations:**
```bash
python3 pylot.py --flagfile=configs/detection.conf \
  --visualize_rgb_camera --visualize_detected_obstacles \
  --simulator_fps=10 \
  --camera_image_width=800 --camera_image_height=600 \
  --v=1
```

**When to skip visualization:**
- For production benchmarking (adds overhead)
- For long runs (unreliable over hours)
- For data collection (use log analysis instead)
- When debugging non-visual issues

### Alternative Monitoring (No X11 Required)

**DOT graph (pipeline structure):**
- Auto-generated: `pylot.dot` in working directory
- Shows operator dataflow graph
- View: `dot -Tpng pylot.dot -o graph.png`

**Chrome trace (performance timeline):**
- Flag: `--profile_file_name=pylot_profile.json`
- View: chrome://tracing
- Shows operator execution timeline, watermarks, message passing

**Log-based timing (SCN infrastructure):**
- Flag: `--v=1 --log_file_name=pylot.log`
- Parse: `scripts/scn_quick_timing_analysis.sh`
- No GUI needed, works over SSH without X11

### Container Creation for Visualization

**RECOMMENDED: Use automated reset script:**
```bash
cd /path/to/SuperCarlaNet
bash reset_container.sh
```

The script handles:
- Stopping/removing old container
- Creating container with `--network=host` (required for GPU server multi-user environments)
- Configuring SSH on port 20025 (required with host networking)
- Copying SCN_DOCS files
- Setting erdos password

**Manual creation (if customization needed):**
```bash
docker run -itd \
  --name scn_pylot \
  --privileged \
  --gpus all \
  --network=host \                       # Required for shared GPU servers
  -e DISPLAY=$DISPLAY \                  # Forward DISPLAY var
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \  # X11 socket (won't work but harmless)
  erdosproject/pylot:latest

# Configure SSH on port 20025 (required with --network=host):
docker exec scn_pylot bash -c '
  sudo sed -i "s/#Port 22/Port 20025/" /etc/ssh/sshd_config
  sudo sed -i "s/^Port 22/Port 20025/" /etc/ssh/sshd_config
  echo "erdos:erdos" | sudo chpasswd
  sudo service ssh start
'

# Copy SCN_DOCS files:
docker cp SCN_DOCS scn_pylot:/home/erdos/workspace/pylot/
```

**Why port 20025?** With `--network=host`, container shares host's network namespace. Port 22 is already used by host SSH, so container SSH must use different port (20025).

**Note:** `-p 20025:22` flag is ignored with `--network=host` (port mapping doesn't apply).

---

## Known Issues

1. **Detection.conf** uses autopilot - no Tier 3 data. Use frenet_optimal_trajectory.conf for full pipeline.
2. **Utils package structure** must be fixed in Docker (see above).
3. **Decorator** handles both callback types (fixed).
4. **Visualization requires nested SSH** - `docker exec` approach will not work for X11 forwarding over SSH.
5. **CARLA startup requires correct directory** - Must `cd /home/erdos/workspace/pylot` before running `scripts/run_simulator.sh` (script needs $CARLA_HOME).
6. **Visualization MUST use --simulator_fps=10** - Default 20 FPS overwhelms pipeline (detection 100ms + X11 50-100ms = can't keep up). Without this flag, "operator events queued" warnings flood terminal.
7. **--network=host requires SSH port 20025** - Container can't use port 22 (host SSH already using it). Must configure SSH to listen on 20025.
8. **🔴 CRITICAL: NEVER use SIGKILL (-9) on CARLA directly** - Using `pkill -9` on CarlaUE4 while it's doing GPU operations causes unkillable D-state hang. Process gets stuck in NVIDIA driver code waiting for GPU DMA. Container becomes unusable, requires Docker daemon restart. ALWAYS use SIGTERM first (allows GPU cleanup), wait 5 seconds, then SIGKILL if necessary. Use `stop_carla.sh` or updated `stop_pylot.sh` which do this correctly. This was the root cause of Nov 15 Docker corruption incident.

---

## Documentation Structure

**User-facing guides:**
- 0_START_HERE.md - Entry point
- 1_SETUP_AND_RUN.md - Docker setup + running
- 2_TECHNICAL_DESIGN.md - Architecture
- 3_DATA_COLLECTION.md - Analysis workflow
- 4_REFERENCE.md - API reference
- 5_PIPELINE_FLOW.md - Complete dataflow
- 6_CONFIGURATION_GUIDE.md - All config options
- 7_VISUALIZATION_GUIDE.md - Real-time visualization setup

**Agent context (this file):**
- Technical details, debugging, what works/doesn't work

---

**Version:** 1.1
**Last verified:** 2025-11-12
**Status:** Production-ready, visualization validated on Mac+XQuartz → sysml-01.cc.gatech.edu → Docker
