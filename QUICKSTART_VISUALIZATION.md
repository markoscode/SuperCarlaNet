# Pylot Visualization Quick Start

**4-step process to see your AV drive in real-time:**

## Prerequisites

- **Mac:** Install XQuartz, restart: `brew install --cask xquartz`
- **Linux:** X11 already installed

## Workflow

```bash
# 1. Mac/Linux → GPU server (with X11):
ssh -Y -C dsanyal7@sysml-01.cc.gatech.edu

# 2. Create container:
cd /home/dsanyal7/marko/SuperCarlaNet && bash reset_container.sh

# 3. SSH into container:
ssh -Y -p 20025 erdos@localhost  # Password: erdos

# 4. Run visualization:
cd /home/erdos/workspace/pylot
bash start_carla.sh && sleep 30
source scripts/set_pythonpath.sh
python3 pylot.py --flagfile=configs/detection.conf \
  --visualize_rgb_camera --visualize_detected_obstacles \
  --simulator_fps=10 --v=1

# When done (Ctrl+C then):
bash stop_pylot.sh
```

## Controls

- **'n' key**: Cycle visualization modes
- **Ctrl+C**: Stop Pylot
- **ALWAYS run `bash stop_pylot.sh` after Ctrl+C** (prevents crashes)

## If Something Breaks

**D-state hang detected:**
```bash
exit  # Leave container
cd /home/dsanyal7/marko/SuperCarlaNet && bash reset_container.sh
```

**Docker completely broken:** Contact sysadmin, show them [ROOT_CAUSE_ANALYSIS.md](ROOT_CAUSE_ANALYSIS.md)

## Full Documentation

- [7_VISUALIZATION_GUIDE.md](SCN_DOCS/7_VISUALIZATION_GUIDE.md) - Complete setup guide
- [ROOT_CAUSE_ANALYSIS.md](ROOT_CAUSE_ANALYSIS.md) - D-state technical details
- [SCN_DOCS/](SCN_DOCS/) - Full timing system documentation
