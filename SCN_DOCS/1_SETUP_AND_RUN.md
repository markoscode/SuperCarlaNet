# Setup and Run Guide

## Installation

### Docker (Recommended)
```bash
docker pull erdosproject/pylot
nvidia-docker run -itd --name pylot erdosproject/pylot

# Copy SCN files into container
docker cp pylot/utils/scn_timing.py pylot:/home/erdos/workspace/pylot/pylot/utils/
docker cp pylot/utils/scn_timing_config.py pylot:/home/erdos/workspace/pylot/pylot/utils/
docker cp scripts/scn_*.py pylot:/home/erdos/workspace/pylot/scripts/
docker cp scripts/scn_*.sh pylot:/home/erdos/workspace/pylot/scripts/
# ... copy all 13 modified operators
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

### Basic Run
```bash
# Terminal 1: Start CARLA
./scripts/run_simulator.sh

# Terminal 2: Run Pylot with timing
python3 pylot.py \
    --flagfile=configs/detection.conf \
    --v=1 \
    --log_file_name=pylot_timing.log
```

### Verify Timing
```bash
grep "TIMING" pylot_timing.log | head -5
# Should see: TIMING tier=2 stage=detection ts=...
```

## Analyzing Data

### One Command
```bash
./scripts/scn_quick_timing_analysis.sh pylot_timing.log
cat timing_results/tier2_statistics.txt
```

### Manual
```bash
python3 scripts/scn_analyze_timing.py pylot_timing.log --output timing_results/
python3 scripts/scn_plot_cumulative_cdf.py pylot_timing.log --output timing_results/
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
