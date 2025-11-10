# Technical Design

## Two-Tier Timing System

### Why Two Tiers?

**Tier 1 (Algorithm-only)** - Excluded
- Redundant for deadline enforcement
- Well-documented in model specs
- Doesn't include operator overhead

**Tier 2 (Operator Response)** - Implemented ✅
- Complete callback execution time
- Input message → Output message
- Includes algorithm + message passing
- **D3-compliant**

**Tier 3 (End-to-End)** - Implemented ✅
- Sensor capture → Actuator command
- Includes all operators + system overhead
- Safety-critical metric

### System Overhead

```
Tier 3 (E2E) = Tier 2 (sum of operators) + System Overhead

Overhead = message passing + queuing + scheduling + watermark propagation
Typical: 20-30% of E2E time
```

## Implementation

### Core Components

**scn_timing.py** (120 lines)
```python
class TimingTracker:
    _operator_start_times = {}  # (stage, ts) -> time
    _pipeline_markers = {}      # ts -> {stage: time}

    def start_operator(stage, ts)
    def end_operator(stage, ts, logger) -> duration_ms
    def mark_pipeline(stage, ts)
    def compute_e2e(start, end, ts, logger) -> e2e_ms

@track_operator_time(stage)  # Decorator for Tier 2 (handles both msg & watermark callbacks)
def on_msg_callback(self, msg, stream):
    # Entire callback is timed
    # Decorator automatically detects: msg.timestamp (messages) or msg (watermarks)
```

**scn_timing_config.py** (80 lines)
- Central registry of 13 operators
- Maps file paths to stage names
- Configuration-driven approach

### Operator Instrumentation

**Pattern:**
```python
from pylot.utils.scn_timing import track_operator_time

@erdos.profile_method()
@track_operator_time('detection')
def on_msg_camera_stream(self, msg, output_stream):
    # Algorithm execution
    output_stream.send(result)
```

### Pipeline Boundaries

**Entry (carla_camera_driver_operator.py):**
```python
from pylot.utils.scn_timing import mark_pipeline_stage
mark_pipeline_stage('sensor_input', timestamp)
```

**Exit (pid_control_operator.py):**
```python
from pylot.utils.scn_timing import mark_pipeline_stage, compute_e2e_latency
mark_pipeline_stage('actuator_output', timestamp)
compute_e2e_latency('sensor_input', 'actuator_output', timestamp, logger)
```

## Performance

### Overhead Breakdown
```
Decorator call:         ~5μs
Time measurement (2x):  ~2μs
Dict operations:        ~3μs
Logger call:           ~15μs
String formatting:      ~5μs
---------------------------------
Total:                 ~30μs per operator
```

**For 45ms detection: 0.03ms / 45ms = 0.067% overhead**

### Thread Safety
- All operations use `threading.Lock()`
- Safe for concurrent operator execution

### Memory Management
- Auto-cleanup: keeps last 1000 timestamps
- ~100KB max memory usage
- Bounded and predictable

## Log Format

### Tier 2
```
TIMING tier=2 stage=detection ts=Timestamp(100) response_ms=45.23
```

### Tier 3
```
TIMING tier=3 ts=Timestamp(100) start=sensor_input end=actuator_output e2e_ms=115.67
```

**Structured for easy parsing with regex**

## D3 Alignment

✅ Operator response time (not algorithm time)
✅ Timestamp-based tracking (watermark-driven)
✅ Thread-safe for concurrent execution
✅ Minimal overhead (<0.1%)
