# Setup and Run Guide

## Installation

### Docker (Recommended)

**1. Create container with GPU support:**
```bash
docker run -itd \
  --gpus all \
  --shm-size=16g \
  --name scn_pylot \
  -p 20025:22 \
  erdosproject/pylot \
  /bin/bash
```

**2. Fix pylot.utils package structure:**
```bash
# Convert utils.py to utils/__init__.py for proper package structure
docker exec scn_pylot bash -c "mkdir -p /home/erdos/workspace/pylot/pylot/utils && \
  cp /home/erdos/workspace/pylot/pylot/utils.py /home/erdos/workspace/pylot/pylot/utils/__init__.py"
```

**3. Copy SCN timing files:**
```bash
docker cp pylot/utils/scn_timing.py scn_pylot:/home/erdos/workspace/pylot/pylot/utils/
docker cp pylot/utils/scn_timing_config.py scn_pylot:/home/erdos/workspace/pylot/pylot/utils/
```

**4. Copy analysis scripts:**
```bash
docker cp scripts/scn_analyze_timing.py scn_pylot:/home/erdos/workspace/pylot/scripts/
docker cp scripts/scn_plot_cumulative_cdf.py scn_pylot:/home/erdos/workspace/pylot/scripts/
docker cp scripts/scn_quick_timing_analysis.sh scn_pylot:/home/erdos/workspace/pylot/scripts/
```

**5. Copy all 14 modified operators:**
```bash
# Detection (4)
docker cp pylot/perception/detection/detection_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/perception/detection/
docker cp pylot/perception/detection/efficientdet_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/perception/detection/
docker cp pylot/perception/detection/lanenet_detection_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/perception/detection/
docker cp pylot/perception/detection/traffic_light_det_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/perception/detection/

# Segmentation (1), Tracking (1)
docker cp pylot/perception/segmentation/segmentation_drn_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/perception/segmentation/
docker cp pylot/perception/tracking/object_tracker_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/perception/tracking/

# Localization (1)
docker cp pylot/localization/localization_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/localization/

# Prediction (2)
docker cp pylot/prediction/linear_predictor_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/prediction/
docker cp pylot/prediction/r2p2_predictor_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/prediction/

# Planning (2)
docker cp pylot/planning/planning_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/planning/
docker cp pylot/planning/behavior_planning_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/planning/

# Control (2)
docker cp pylot/control/pid_control_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/control/
docker cp pylot/control/mpc/mpc_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/control/mpc/

# Camera driver (1)
docker cp pylot/drivers/carla_camera_driver_operator.py scn_pylot:/home/erdos/workspace/pylot/pylot/drivers/
```

### Manual
```bash
./install.sh
pip install -e ./

# Set environment
export PYLOT_HOME=$(pwd)
export CARLA_HOME=$PYLOT_HOME/dependencies/CARLA_0.9.10.1/
source scripts/set_pythonpath.sh
```

## Environment Setup

### Required Variables
```bash
export PYLOT_HOME=/path/to/pylot
export CARLA_HOME=$PYLOT_HOME/dependencies/CARLA_0.9.10.1/
CARLA_EGG=$(ls $CARLA_HOME/PythonAPI/carla/dist/carla*py3*egg)
export PYTHONPATH="${PYTHONPATH}:${PYLOT_HOME}:${CARLA_EGG}:${PYLOT_HOME}/dependencies/:${CARLA_HOME}/PythonAPI/carla/:${PYLOT_HOME}/dependencies/lanenet/"
```

### Conda (Recommended)
```bash
conda create -n pylot_py38 python=3.8
conda activate pylot_py38
pip install -r requirements.txt
pip install -e ./
```

**Note:** Python 3.8 required (TensorFlow GPU 2.5.1 compatibility)

## Running Pylot

### Start CARLA Simulator
```bash
docker exec scn_pylot bash -c 'export CARLA_HOME=/home/erdos/workspace/pylot/dependencies/CARLA_0.9.10.1 && \
  nohup bash /home/erdos/workspace/pylot/scripts/run_simulator.sh > /tmp/carla.log 2>&1 &'

# Wait 30 seconds for CARLA to initialize
sleep 30
```

### Run Pylot with Timing
```bash
docker exec scn_pylot bash -c 'export PYLOT_HOME=/home/erdos/workspace/pylot && \
  export CARLA_HOME=/home/erdos/workspace/pylot/dependencies/CARLA_0.9.10.1 && \
  source /home/erdos/workspace/pylot/scripts/set_pythonpath.sh && \
  cd /home/erdos/workspace/pylot && \
  python3 pylot.py --flagfile=configs/detection.conf --v=1 --log_file_name=pylot_timing.log'

# Or run in background:
docker exec scn_pylot bash -c 'export PYLOT_HOME=/home/erdos/workspace/pylot && \
  export CARLA_HOME=/home/erdos/workspace/pylot/dependencies/CARLA_0.9.10.1 && \
  source /home/erdos/workspace/pylot/scripts/set_pythonpath.sh && \
  cd /home/erdos/workspace/pylot && \
  nohup python3 pylot.py --flagfile=configs/detection.conf --v=1 --log_file_name=pylot_timing.log > /tmp/pylot_run.log 2>&1 &'

# Stop Pylot when done:
docker exec scn_pylot pkill -f "python3 pylot.py"
```

### Verify Timing
```bash
docker exec scn_pylot bash -c "grep 'TIMING' /home/erdos/workspace/pylot/pylot_timing.log | head -5"
# Should see: TIMING tier=2 stage=detection ts=...
```

## Analyzing Data

### One Command (Inside Container)
```bash
docker exec scn_pylot bash -c "cd /home/erdos/workspace/pylot && \
  bash scripts/scn_quick_timing_analysis.sh pylot_timing.log timing_results 10"

# Copy results to host
docker cp scn_pylot:/home/erdos/workspace/pylot/timing_results ./
docker cp scn_pylot:/home/erdos/workspace/pylot/pylot_timing.log ./

# View results
cat timing_results/tier2_statistics.txt
```

### Manual Analysis (Inside Container)
```bash
docker exec scn_pylot bash -c "cd /home/erdos/workspace/pylot && \
  python3 scripts/scn_analyze_timing.py pylot_timing.log --output timing_results/ --skip-warmup 10"
```

## Troubleshooting

**No TIMING logs:**
- Use `--v=1` (INFO level)
- Check instrumentation: `grep "scn_timing" pylot/*/detection/detection_operator.py`

**Import errors:**
- Set `PYTHONPATH` correctly
- Source `scripts/set_pythonpath.sh`

**CARLA connection failed:**
- Start CARLA: `./scripts/run_simulator.sh`
- Check port: `--carla_port=2000`

**GPU memory:**
- Reduce fraction: `--obstacle_detection_gpu_memory_fraction=0.3`
