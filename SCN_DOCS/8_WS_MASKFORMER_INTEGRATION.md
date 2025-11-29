# WS-Mask2Former Integration via gRPC

**Status**: Implemented
**Last Updated**: 2024-11-29
**Replaces**: 8_WS_MASKFORMER_TESTING.md (deprecated virtualenv approach)

---

## Summary

This document describes the integration of the weight-sharing Mask2Former detection model into the SuperCarlaNet/Pylot AV pipeline using a **two-container gRPC architecture**.

### Key Design Decision

**Previous approach (abandoned)**: Run PyTorch/Detectron2 in a virtualenv inside the Pylot container.
- Failed due to NumPy version conflict (TF needs <1.20, PyTorch needs ≥1.21)
- Complex, fragile, hard to maintain

**Current approach (implemented)**: Run detection model in separate container, communicate via gRPC.
- Complete dependency isolation
- Clean IPC boundary
- Easier debugging and independent scaling

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              Docker Network (scn-network)                  │
│                                                                            │
│  ┌─────────────────────────────┐         ┌─────────────────────────────┐  │
│  │    wsobjdet Container       │  gRPC   │     Pylot Container         │  │
│  │                             │◄───────►│                             │  │
│  │  PyTorch 1.10 + CUDA 11.3   │ :50051  │  TensorFlow 2.5.1           │  │
│  │  Detectron2 v0.6            │         │  ERDOS + Pylot              │  │
│  │  Mask2Former model          │         │  CARLA client               │  │
│  │                             │         │                             │  │
│  │  grpc_server.py             │         │  ws_maskformer_grpc_operator│  │
│  └─────────────────────────────┘         └─────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### wsobjdet Container (Server)

| Component | File | Purpose |
|-----------|------|---------|
| gRPC Server | `grpc_server.py` | Handles Detect/SetSubnet/GetStatus RPCs |
| Inference Engine | `inference_server.py` | Model loading, inference, label mapping |
| Protobuf Schema | `detection_service/detection.proto` | API contract |
| Dockerfile | `Dockerfile` | PyTorch 1.10 + detectron2 v0.6 environment |

### SuperCarlaNet/Pylot (Client)

| Component | File | Purpose |
|-----------|------|---------|
| ERDOS Operator | `pylot/perception/detection/ws_maskformer_grpc_operator.py` | gRPC client, frame handling |
| gRPC Stubs | `pylot/perception/detection/wsobjdet_grpc/` | Generated protobuf classes |
| Flags | `pylot/perception/flags.py` | `ws_maskformer_grpc_address` flag |
| Operator Creator | `pylot/operator_creator.py` | `add_ws_maskformer_grpc_detection()` |
| Component Creator | `pylot/component_creator.py` | Routes `ws_maskformer_grpc` model |
| Config | `configs/ws_detection_grpc.conf` | Flagfile for gRPC detector |

---

## Data Flow

```
1. CameraStream (BGR numpy array)
         │
         ▼
2. WSMaskFormerGRPCOperator.on_msg_camera_stream()
         │
         ├── Serialize frame to bytes: frame.tobytes()
         │
         ├── Build DetectRequest protobuf
         │
         ▼
3. gRPC stub.Detect(request) ──────────────────────► wsobjdet container
         │                                                    │
         │                                                    ▼
         │                                           4. DetectionServicer.Detect()
         │                                                    │
         │                                                    ├── Deserialize image
         │                                                    │
         │                                                    ├── run_inference()
         │                                                    │
         │                                                    ├── Build DetectResponse
         │                                                    │
         ◄────────────────────────────────────────────────────┘
         │
         ▼
5. Parse response.detections into Obstacle objects
         │
         ├── BoundingBox2D(x_min, x_max, y_min, y_max)
         │
         ├── Obstacle(bbox, score, label, id)
         │
         ▼
6. ObstaclesMessage sent to downstream operators
```

---

## Usage

### 1. Start Detection Server

```bash
# From marko root directory
./launch_grpc_detection.sh start

# Or manually
docker run --gpus all --network scn-network --name wsobjdet-grpc \
    -p 50051:50051 ws-mask2former:latest
```

### 2. Verify Server

```bash
./launch_grpc_detection.sh test
# Expected: GetStatus returns ready=True, active_subnet=max
```

### 3. Run Pylot with gRPC Detector

```bash
# Open Pylot container on same network
./launch_grpc_detection.sh pylot

# Inside container
python pylot.py --flagfile=configs/ws_detection_grpc.conf
```

### 4. Or with Docker Compose

```bash
docker compose up -d wsobjdet
docker compose run pylot bash
# Inside: python pylot.py --flagfile=configs/ws_detection_grpc.conf
```

---

## Configuration

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--obstacle_detection_model_names` | - | Set to `ws_maskformer_grpc` |
| `--ws_maskformer_grpc_address` | `localhost:50051` | gRPC server address |
| `--ws_maskformer_subnet` | `max` | Subnet: min, middle, max |
| `--obstacle_detection_min_score_threshold` | `0.5` | Min detection confidence |
| `--ws_maskformer_min_mask_area` | `200` | Min bbox area in pixels |

### Config File (ws_detection_grpc.conf)

```conf
--obstacle_detection
--nosimulator_obstacle_detection
--obstacle_detection_model_names=ws_maskformer_grpc
--ws_maskformer_grpc_address=wsobjdet-grpc:50051
--ws_maskformer_subnet=max
--obstacle_detection_min_score_threshold=0.3
```

---

## Label Mapping

The model was trained on ADE20K (150 classes). Only these classes are mapped to Pylot labels:

| ADE20K Class | Pylot Label |
|--------------|-------------|
| person | person |
| car | car |
| bus | bus |
| truck | truck |
| minibike/motorbike | motorcycle |
| bicycle | bicycle |

All other ADE20K classes are filtered out. Use `--all_labels=True` in DetectRequest to bypass filtering (for debugging).

---

## Performance

### Latency (640x480 image, RTX-class GPU)

| Subnet | Inference | RPC Total | Network Overhead |
|--------|-----------|-----------|------------------|
| min | 85 ms | 125 ms | ~40 ms |
| middle | 90 ms | 128 ms | ~38 ms |
| max | 105 ms | 146 ms | ~41 ms |

### Throughput

At max subnet (~150ms per frame): **~6.7 FPS**

### Overhead Breakdown

| Component | Time |
|-----------|------|
| Image serialization | 0.5 ms |
| Network transfer (Docker bridge) | 2 ms |
| Protobuf parsing | 0.5 ms |
| Python GIL / thread scheduling | ~35 ms |
| **Total overhead** | ~40 ms |

---

## Timing Instrumentation

The operator is registered for SCN timing:

```python
# scn_timing_config.py
'pylot/perception/detection/ws_maskformer_grpc_operator.py': 'detection_grpc'
```

Logs include:
- Total operator time (frame-to-frame)
- gRPC round-trip time
- Model inference time (from response)
- Network overhead (RTT - inference)

---

## Error Handling

### Connection Failure

```python
# Operator logs error and drops frame
if not self._connected:
    self._logger.error('Not connected to detection server; dropping frame')
    return []
```

### Detection Failure

```python
if not response.success:
    self._logger.error(f'Detection failed: {response.error}')
    return []
```

### Reconnection

The operator attempts connection once at startup. If the server restarts, the operator must be restarted. (Future: add automatic reconnection.)

---

## Files Modified

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `ws_maskformer_grpc_operator.py` | 230 | ERDOS operator with gRPC client |
| `wsobjdet_grpc/__init__.py` | 25 | Package exports |
| `wsobjdet_grpc/detection_pb2.py` | 90 | Generated messages |
| `wsobjdet_grpc/detection_pb2_grpc.py` | 120 | Generated stubs |
| `configs/ws_detection_grpc.conf` | 20 | Flagfile |

### Modified Files

| File | Change |
|------|--------|
| `pylot/perception/flags.py` | Added `ws_maskformer_grpc_address` |
| `pylot/operator_creator.py` | Added `add_ws_maskformer_grpc_detection()` |
| `pylot/component_creator.py` | Route for `ws_maskformer_grpc` model |
| `pylot/utils/scn_timing_config.py` | Registered operator for timing |

---

## Comparison: In-Process vs gRPC

| Aspect | In-Process (ws_maskformer) | gRPC (ws_maskformer_grpc) |
|--------|---------------------------|---------------------------|
| Dependencies | Requires PyTorch in Pylot env | Only grpcio in Pylot env |
| Isolation | None (shared process) | Full (separate container) |
| Latency | ~100ms | ~140ms (+40ms overhead) |
| Debugging | Complex (mixed frameworks) | Simple (isolated logs) |
| Deployment | Single container | Two containers |
| NumPy conflict | Breaks TensorFlow ops | No conflict |

**Recommendation**: Use gRPC version for production. In-process version kept for reference but not functional with TensorFlow operators.

---

## Troubleshooting

### "Not connected to detection server"

```bash
# Check if server is running
docker ps | grep wsobjdet

# Check network
docker network inspect scn-network

# Ensure containers on same network
docker network connect scn-network wsobjdet-grpc
docker network connect scn-network scn-pylot
```

### "Connection refused"

```bash
# Verify server is listening
docker exec wsobjdet-grpc netstat -tlnp | grep 50051

# Check server logs
docker logs wsobjdet-grpc
```

### Zero detections

1. Lower score threshold: `--obstacle_detection_min_score_threshold=0.1`
2. Check image has AV-relevant objects (cars, people, etc.)
3. Verify model is in instance mode (should be default)

### High latency

1. Check GPU utilization: `nvidia-smi`
2. Use smaller subnet: `--ws_maskformer_subnet=min`
3. Verify no CPU fallback: server logs should show `cuda:0`

---

## Future Work

- [ ] Automatic reconnection on server restart
- [ ] Streaming RPC for continuous frame processing
- [ ] Dynamic subnet switching based on TTD (time-to-decision)
- [ ] Load balancing across multiple detection servers
- [ ] GPU memory pooling for multiple models

---

## Related Documents

- [WSOBJDET_INFERENCE_SERVER.md](WSOBJDET_INFERENCE_SERVER.md) - Standalone inference documentation
- [wsobjdet/docs/GRPC_SERVICE.md](../../wsobjdet/docs/GRPC_SERVICE.md) - gRPC server implementation details
- [ROOT_CAUSE_ANALYSIS.md](ROOT_CAUSE_ANALYSIS.md) - Docker/CARLA D-state issues
