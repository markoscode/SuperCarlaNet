# API and Coverage Reference

## Complete Operator Coverage (13)

### Detection (4 operators)
| Operator | File | Stage Name | Callback |
|----------|------|------------|----------|
| Object Detection | detection_operator.py | `detection` | on_msg_camera_stream |
| Lane Detection | lanenet_detection_operator.py | `lane_detection` | on_camera_frame |
| Traffic Lights | traffic_light_det_operator.py | `traffic_light_detection` | on_frame |
| EfficientDet | efficientdet_operator.py | `efficient_detection` | on_watermark |

### Segmentation (1 operator)
| Operator | File | Stage Name | Callback |
|----------|------|------------|----------|
| Semantic Seg | segmentation_drn_operator.py | `segmentation` | on_msg_camera_stream |

### Tracking (1 operator)
| Operator | File | Stage Name | Callback |
|----------|------|------------|----------|
| Object Tracker | object_tracker_operator.py | `tracking` | on_watermark |

### Localization (1 operator)
| Operator | File | Stage Name | Callback |
|----------|------|------------|----------|
| EKF Localization | localization_operator.py | `localization` | on_watermark |

### Prediction (2 operators)
| Operator | File | Stage Name | Callback |
|----------|------|------------|----------|
| Linear Predictor | linear_predictor_operator.py | `prediction` | generate_predicted_trajectories |
| R2P2 Predictor | r2p2_predictor_operator.py | `r2p2_prediction` | on_watermark |

### Planning (2 operators)
| Operator | File | Stage Name | Callback |
|----------|------|------------|----------|
| Trajectory Planning | planning_operator.py | `planning` | on_watermark |
| Behavior Planning | behavior_planning_operator.py | `behavior_planning` | on_watermark |

### Control (2 operators)
| Operator | File | Stage Name | Callback |
|----------|------|------------|----------|
| PID Control | pid_control_operator.py | `control` | on_watermark |
| MPC Control | mpc/mpc_operator.py | `mpc_control` | on_watermark |

## Tier 3 Pipeline Boundaries

| Stage | File | Location | Purpose |
|-------|------|----------|---------|
| `sensor_input` | carla_camera_driver_operator.py:82 | Camera frame sent | Entry point |
| `actuator_output` | pid_control_operator.py:94 | Control command sent | Exit point |

## API Reference

### scn_timing.py

```python
class TimingTracker:
    def start_operator(stage: str, timestamp: erdos.Timestamp)
    def end_operator(stage: str, timestamp: erdos.Timestamp, logger) -> float
    def mark_pipeline(stage: str, timestamp: erdos.Timestamp)
    def compute_e2e(start_stage: str, end_stage: str,
                    timestamp: erdos.Timestamp, logger) -> Optional[float]

# Decorator for Tier 2
@track_operator_time(stage: str)

# Functions for Tier 3
mark_pipeline_stage(stage: str, timestamp: erdos.Timestamp)
compute_e2e_latency(start_stage: str, end_stage: str,
                    timestamp: erdos.Timestamp, logger) -> Optional[float]
```

### scn_timing_config.py

```python
# Configuration
OPERATOR_TIMING_CONFIG = {
    'pylot/perception/detection/detection_operator.py': 'detection',
    # ... 12 more entries
}

# Utility functions
get_stage_for_operator(operator_file_path: str) -> str
get_all_instrumented_operators() -> List[Tuple[str, str]]
```

### scn_analyze_timing.py

```bash
python3 scn_analyze_timing.py <log_file> [--output DIR] [--skip-warmup N]
```

**Outputs:**
- tier2_statistics.txt
- tier2_breakdown.txt
- tier2_breakdown.png
- tier2_cdf_<stage>.png (per stage)
- tier3_statistics.txt
- tier3_cdf_e2e.png
- system_overhead.txt

### scn_plot_cumulative_cdf.py

```bash
python3 scn_plot_cumulative_cdf.py <log_file> [--output DIR] [--skip-warmup N]
```

**Output:**
- tier2_cdf_cumulative_all_stages.png

### scn_quick_timing_analysis.sh

```bash
./scn_quick_timing_analysis.sh <log_file> [output_dir] [skip_warmup]
```

**Runs both analysis scripts with defaults**

## Configuration

### Adding New Operators

**1. Add to scn_timing_config.py:**
```python
OPERATOR_TIMING_CONFIG = {
    'pylot/your/new_operator.py': 'your_stage_name',
}
```

**2. Instrument operator:**
```python
from pylot.utils.scn_timing import track_operator_time

@erdos.profile_method()
@track_operator_time('your_stage_name')
def on_watermark(self, timestamp, output_stream):
    # Your code
```

**3. Run and verify:**
```bash
grep "stage=your_stage_name" pylot.log
```

## Log Format Specification

### Tier 2 Format
```
TIMING tier=2 stage=<STAGE_NAME> ts=<TIMESTAMP> response_ms=<FLOAT>
```

**Example:**
```
TIMING tier=2 stage=detection ts=Timestamp(100) response_ms=45.23
```

**Regex:**
```python
r'TIMING tier=2 stage=(\w+) ts=(\S+) response_ms=([\d.]+)'
```

### Tier 3 Format
```
TIMING tier=3 ts=<TIMESTAMP> start=<START_STAGE> end=<END_STAGE> e2e_ms=<FLOAT>
```

**Example:**
```
TIMING tier=3 ts=Timestamp(100) start=sensor_input end=actuator_output e2e_ms=115.67
```

**Regex:**
```python
r'TIMING tier=3 ts=(\S+) start=(\w+) end=(\w+) e2e_ms=([\d.]+)'
```

## Statistics Computed

| Metric | Description | Use Case |
|--------|-------------|----------|
| Mean | Average time | General performance |
| Median | Middle value | Typical performance |
| Std Dev | Variation | Consistency |
| Min/Max | Range | Outliers |
| P50 | 50th percentile | Same as median |
| P95 | 95th percentile | Near-worst case |
| P99 | 99th percentile | Worst case planning |

## Visualization Types

| Plot | Shows | Purpose |
|------|-------|---------|
| CDF (per stage) | Distribution of single stage | Identify outliers |
| Cumulative CDF | All stages on one plot | Compare stages |
| Pie chart | Time breakdown % | Identify bottlenecks |
| Bar chart | Absolute time per stage | Compare magnitudes |

## Integration Points

**Pylot configs:** No changes needed - works with all existing configs

**ERDOS:** Integrates with existing ERDOS operator framework

**Logging:** Uses standard Python logging (no new dependencies)

**Analysis:** Uses numpy + matplotlib (standard data science stack)
