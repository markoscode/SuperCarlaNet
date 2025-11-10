# Timing Instrumentation Coverage Report

## Complete AV Pipeline Coverage

All critical operators in the Pylot autonomous vehicle pipeline are now instrumented with Tier 2 timing tracking. Coverage is **100%** across all pipeline stages.

## Instrumented Modules by Pipeline Stage

### 1. Perception - Detection (4 operators)
| Operator | Stage Name | File | Callback |
|----------|-----------|------|----------|
| Object Detection | `detection` | `detection_operator.py:77` | `on_msg_camera_stream` |
| Lane Detection | `lane_detection` | `lanenet_detection_operator.py:86` | `on_camera_frame` |
| Traffic Light Detection | `traffic_light_detection` | `traffic_light_det_operator.py:95` | `on_frame` |
| EfficientDet Detection | `efficient_detection` | `efficientdet_operator.py:169` | `on_watermark` |

### 2. Perception - Segmentation (1 operator)
| Operator | Stage Name | File | Callback |
|----------|-----------|------|----------|
| Semantic Segmentation | `segmentation` | `segmentation_drn_operator.py:67` | `on_msg_camera_stream` |

### 3. Perception - Tracking (1 operator)
| Operator | Stage Name | File | Callback |
|----------|-----------|------|----------|
| Object Tracking | `tracking` | `object_tracker_operator.py:105` | `on_watermark` |

### 4. Localization (1 operator)
| Operator | Stage Name | File | Callback |
|----------|-----------|------|----------|
| EKF Localization | `localization` | `localization_operator.py:164` | `on_watermark` |

### 5. Prediction (2 operators)
| Operator | Stage Name | File | Callback |
|----------|-----------|------|----------|
| Linear Prediction | `prediction` | `linear_predictor_operator.py:63` | `generate_predicted_trajectories` |
| R2P2 Prediction | `r2p2_prediction` | `r2p2_predictor_operator.py:77` | `on_watermark` |

### 6. Planning (2 operators)
| Operator | Stage Name | File | Callback |
|----------|-----------|------|----------|
| Trajectory Planning | `planning` | `planning_operator.py:200` | `on_watermark` |
| Behavior Planning | `behavior_planning` | `behavior_planning_operator.py:110` | `on_watermark` |

### 7. Control (2 operators)
| Operator | Stage Name | File | Callback |
|----------|-----------|------|----------|
| PID Control | `control` | `pid_control_operator.py:72` | `on_watermark` |
| MPC Control | `mpc_control` | `mpc/mpc_operator.py:61` | `on_watermark` |

## Pipeline Boundaries (Tier 3)

| Stage | Location | Purpose |
|-------|----------|---------|
| `sensor_input` | `carla_camera_driver_operator.py:82` | Entry point when sensor data enters pipeline |
| `actuator_output` | `pid_control_operator.py:94` | Exit point when control commands are sent |

## Configuration Management

All instrumented operators are centrally configured in:
- **Configuration File**: `pylot/utils/timing_config.py`
- **Total Operators**: 13 operators across 7 pipeline stages
- **Consistency**: All operators in `OPERATOR_TIMING_CONFIG` have been instrumented

## Coverage Verification

✅ **Object Detection**: Covered (2 implementations: detection, efficientdet)
✅ **Lane Detection**: Covered (lanenet)
✅ **Traffic Light Detection**: Covered
✅ **Segmentation**: Covered
✅ **Object Tracking**: Covered
✅ **Localization**: Covered
✅ **Prediction**: Covered (2 implementations: linear, r2p2)
✅ **Planning**: Covered (2 implementations: trajectory, behavior)
✅ **Control**: Covered (2 implementations: PID, MPC)

## Usage

All timing data is logged in the following format:

**Tier 2 - Operator Response Time:**
```
TIMING tier=2 stage=detection ts=Timestamp(...) response_ms=45.23
```

**Tier 3 - End-to-End Latency:**
```
TIMING tier=3 ts=Timestamp(...) start=sensor_input end=actuator_output e2e_ms=250.45
```

## Implementation Notes

1. **Minimal Changes**: Each operator requires only 2 lines of modification (import + decorator)
2. **Thread-Safe**: All timing operations use locks for concurrent access
3. **Memory-Efficient**: Automatic cleanup of old timing markers (keeps last 1000)
4. **Zero Overhead When Disabled**: Decorators add negligible overhead (~microseconds)
5. **Configuration-Driven**: Adding new operators only requires updating `timing_config.py`
