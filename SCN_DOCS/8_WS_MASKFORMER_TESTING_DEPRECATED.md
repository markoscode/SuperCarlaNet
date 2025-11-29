# WS Mask2Former Detector - Integration & Testing Guide

This document covers the integration of a weight-sharing Mask2Former model (trained on ADE20K) into the SuperCarlaNet/Pylot autonomous vehicle pipeline as an alternative object detector.

---

## Background & Context

### What This Integration Does

The `wsobjdet` repository contains a **Mask2Former** model with **weight-sharing subnets** - the core innovation being dynamic model scaling. At runtime, you can select between `min`, `middle`, and `max` subnet configurations to trade off latency vs accuracy, which is valuable for deadline-aware AV pipelines.

The model was trained on **ADE20K** (150 indoor+outdoor classes) rather than COCO (80 classes). This means we need label mapping to extract only AV-relevant classes: `person`, `car`, `bus`, `truck`, `motorcycle`, `bicycle`.

### Key Technical Decisions Made

1. **Instance Mode, Not Semantic**: Mask2Former supports both semantic and instance segmentation. We enable `MODEL.MASK_FORMER.TEST.INSTANCE_ON = True` to get per-object masks with native bounding boxes - no need for connected components heuristics.

2. **DefaultPredictor Handles Preprocessing**: Detectron2's `DefaultPredictor` automatically handles BGR→RGB conversion, resizing, and normalization. The operator passes frames directly without manual preprocessing.

3. **Subnet Control API**: Must call module-specific methods, not a single `set_active_subnet()`:
   ```python
   model.backbone.set_active_subnet(depth_list=[...])
   model.sem_seg_head.predictor.set_active_subnet([...])
   model.sem_seg_head.pixel_decoder.transformer.set_active_subnet([...])
   ```

4. **Label Mapping Strategy**: Dual approach - metadata lookup from Detectron2's catalog with hardcoded ADE20K trainId fallback:
   ```python
   {11: 'person', 14: 'car', 80: 'bus', 93: 'truck', 103: 'motorcycle', 108: 'bicycle'}
   ```

---

## Critical Bugs Found & Fixed

During code audit, three critical issues were identified and fixed:

| Issue | Original Code | Fix Applied |
|-------|---------------|-------------|
| Subnet API | Called non-existent `model.set_active_subnet(**kwargs)` | Call module-specific methods on backbone, predictor, pixel_decoder |
| BBox Tensor | `instances.pred_boxes[idx].tensor` returns wrong shape | Use `instances.pred_boxes.tensor[idx]` |
| Class Mapping | No fallback if metadata lookup fails | Added hardcoded ADE20K trainId→label dict |

Additionally, optimized to only compute boxes from masks when `pred_boxes` is missing (some Mask2Former outputs already include boxes).

---

## Dependency Hell: What We Learned

### The Core Conflict

The Pylot base image uses **TensorFlow 2.5.1** for existing detection operators (Faster-RCNN, EfficientDet). Mask2Former requires **Detectron2** which needs **PyTorch**.

The "invisible wall" is actually **NumPy version incompatibility**:

| Requirement | NumPy Version |
|-------------|---------------|
| TensorFlow 2.5.1 | `numpy>=1.14.5,<1.20` |
| PyTorch 1.13+ | `numpy>=1.21` |

These ranges are **mutually exclusive** - you cannot satisfy both in the same Python environment.

### Approaches Considered

#### ❌ Approach 1: Direct PyTorch 1.13+ Upgrade
- **Problem**: NumPy conflict crashes TensorFlow operators
- **Status**: Won't work without breaking existing pipeline

#### ⚠️ Approach 2: "Goldilocks" PyTorch 1.10.1
- **Theory**: PyTorch 1.10.1 works with numpy 1.19.5, which TF 2.5.1 also accepts
- **Risk**: Detectron2 0.6 compatibility uncertain; ~60% success probability
- **Dockerfile pins**: `torch==1.10.1+cu111`, `numpy==1.19.5`, `protobuf==3.19.6`

#### ✅ Approach 3: Virtualenv Isolation (Current Plan)
- Create a **separate virtualenv inside the container** for PyTorch/Detectron2
- Base Pylot env keeps TF 2.5.1 + numpy 1.19.5
- WS Mask2Former runs in the venv with PyTorch 2.3.0 + modern numpy
- **Trade-off**: Only ws_maskformer can run at a time (can't mix TF and PyTorch operators in same process)

---

## What We Tried

### Docker Build (In Progress)

Created `Dockerfile.wsdet` at repo root:

```dockerfile
FROM erdosproject/pylot:latest

# Install build tools
RUN apt-get update && apt-get install -y \
      git build-essential cmake ninja-build libgl1 libglib2.0-0

# Create isolated virtualenv for PyTorch stack
RUN python3 -m venv /home/erdos/wsdet
ENV VIRTUAL_ENV=/home/erdos/wsdet
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install PyTorch 2.3.0 + CUDA 12.1
RUN pip install torch==2.3.0+cu121 torchvision==0.18.0+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Install Detectron2 + Mask2Former
RUN pip install 'git+https://github.com/facebookresearch/detectron2.git@main'
COPY wsobjdet /home/erdos/workspace/wsobjdet
RUN pip install -e /home/erdos/workspace/wsobjdet/mask2former
```

Build command:
```bash
cd /home/saketh/marko
docker build -t pylot-wsdet -f Dockerfile.wsdet .
```

**Status**: Build initiated, downloading ~8GB base image + PyTorch wheels. Takes 15-30 minutes.

---

## Validation Steps

These steps validate the ADE20K Mask2Former weights outside the ERDOS pipeline before hooking them into a full run.

## 1. Sanity-check the raw model (Requirement A)

```bash
cd SuperCarlaNet
python3 scripts/ws_maskformer_sanity_check.py \
  --config ../wsobjdet/sem_ade_output_2/config.yaml \
  --weights ../wsobjdet/sem_ade_output_2/model_final.pth \
  --image ../wsobjdet/input.jpg \
  --ws_repo_root ../wsobjdet \
  --gpu_index 0 \
  --subnet max \
  --output /tmp/ws_maskformer_preview.jpg
```

**What to look for**
- CLI prints inference time plus the list of detections (label, score, bbox).
- `/tmp/ws_maskformer_preview.jpg` shows the annotated boxes. This confirms Detectron2/Mask2Former dependencies are installed and the checkpoint loads correctly.

## 2. Validate obstacle conversion (Requirement B)

The same script applies the exact score/area filters and ADE→Pylot label mapping used inside `WSMaskFormerDetectionOperator`. If the console output looks reasonable (only `OBSTACLE_LABELS`, bounding boxes have positive width/height), the operator will emit identical `ObstaclesMessage` contents once wired to ERDOS.

For deeper inspection, rerun with stricter thresholds:

```bash
python3 scripts/ws_maskformer_sanity_check.py \
  --config ../wsobjdet/sem_ade_output_2/config.yaml \
  --weights ../wsobjdet/sem_ade_output_2/model_final.pth \
  --image ../wsobjdet/input.jpg \
  --min_score 0.5 \
  --min_area 500
```

This mimics tuning `--obstacle_detection_min_score_threshold` and `--ws_maskformer_min_mask_area` before touching the full pipeline.

## Notes
- These commands require Detectron2 + Mask2Former + PyTorch ≥1.10 available in the environment.
- `--ws_repo_root` defaults to `../wsobjdet`; adjust if the weights/config live elsewhere.
- Keep subnet selection (`--subnet`) aligned with the pipeline flag `--ws_maskformer_subnet` to reproduce the same backbone depth.

---

## Files Changed Summary

| File | Change |
|------|--------|
| `pylot/perception/detection/ws_maskformer_operator.py` | **New** - Main ERDOS operator (237 lines) |
| `pylot/perception/flags.py` | Added flags for config/weights/subnet/min-area |
| `pylot/operator_creator.py` | Added `add_ws_maskformer_detection()` factory |
| `pylot/component_creator.py` | Added routing branch for `ws_maskformer` model selection |
| `pylot/utils/scn_timing_config.py` | Registered operator for SCN timing |
| `configs/ws_detection.conf` | **New** - Flagfile for ws_maskformer runs |
| `scripts/ws_maskformer_sanity_check.py` | **New** - Standalone validation script |
| `Dockerfile.wsdet` | **New** - Docker image with PyTorch/Detectron2 |

---

## What's Incomplete

### Blocking Issues
- [ ] **Docker image not built** - Build was initiated but not completed
- [ ] **Sanity check not run** - Scripts exist but weren't executed due to missing dependencies
- [ ] **Pipeline run untested** - Only operator wiring is in place, not validated end-to-end

### Known Unknowns
- [ ] **Subnet control may silently fail** - If wsobjdet model doesn't have `set_active_subnet` methods, it falls back to max net with a warning (not an error)
- [ ] **ADE20K class coverage** - Model may detect objects but fail to map them (e.g., `van` → no Pylot equivalent)
- [ ] **Threshold tuning** - Default `min_score=0.3`, `min_area=200` are guesses; need real-world calibration

### Out of Scope
- No CI/CD integration
- No benchmark comparison vs baseline Faster-RCNN
- No deadline-driven subnet switching (only static selection)

---

## Next Steps (Detailed)

### Step 1: Complete Docker Build
```bash
cd /home/saketh/marko
docker build -t pylot-wsdet -f Dockerfile.wsdet .
```
Expected: ~15-30 min for first build (downloads ~10GB of layers + wheels)

### Step 2: Launch Container
```bash
docker run --gpus all --shm-size=16g -it \
  -v /home/saketh/marko:/home/erdos/workspace \
  -w /home/erdos/workspace/SuperCarlaNet \
  --name scn_wsdet pylot-wsdet /bin/bash
```

### Step 3: Activate Venv & Run Sanity Check
```bash
source /home/erdos/wsdet/bin/activate

python3 scripts/ws_maskformer_sanity_check.py \
  --config ../wsobjdet/sem_ade_output_2/config.yaml \
  --weights ../wsobjdet/sem_ade_output_2/model_final.pth \
  --image ../wsobjdet/input.jpg \
  --ws_repo_root ../wsobjdet \
  --gpu_index 0 \
  --subnet max \
  --output /tmp/ws_maskformer_preview.jpg
```

**Expected output**:
```
Loading model from ../wsobjdet/sem_ade_output_2/model_final.pth...
Enabling INSTANCE_ON mode...
Setting subnet to: max
Inference time: 0.XXXs
Detections:
  - car (0.92) [x1, y1, x2, y2]
  - person (0.87) [x1, y1, x2, y2]
  ...
Saved annotated image to /tmp/ws_maskformer_preview.jpg
```

### Step 4: Test Different Subnets
```bash
# Test min subnet (fastest, least accurate)
python3 scripts/ws_maskformer_sanity_check.py \
  --config ../wsobjdet/sem_ade_output_2/config.yaml \
  --weights ../wsobjdet/sem_ade_output_2/model_final.pth \
  --image ../wsobjdet/input.jpg \
  --subnet min \
  --output /tmp/ws_min.jpg

# Compare inference times across subnets
```

### Step 5: Full Pipeline Test (Requires CARLA)
```bash
# Still inside container with venv activated
python3 pylot.py --flagfile=configs/ws_detection.conf

# In another terminal, start CARLA simulator
# Check logs for:
#   - "WSMaskFormerDetectionOperator: Loaded model"
#   - TIMING entries for 'detection' operator
#   - No import errors or crashes
```

### Step 6: Tune Thresholds
Adjust in `configs/ws_detection.conf`:
```
--obstacle_detection_min_score_threshold=0.5  # Higher = fewer false positives
--ws_maskformer_min_mask_area=500             # Higher = ignore small objects
--ws_maskformer_subnet=middle                  # Balance speed/accuracy
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'detectron2'"
- Ensure virtualenv is activated: `source /home/erdos/wsdet/bin/activate`

### "CUDA out of memory"
- Reduce `--shm-size` or use `--subnet min` for smaller model

### "No detections produced"
- Check if input image has ADE20K-relevant objects
- Lower `--min_score` threshold
- Verify INSTANCE_ON is True in model config

### "Subnet control warning: model doesn't have set_active_subnet"
- Model falls back to max net - this is expected for some checkpoints
- Only affects dynamic scaling, not basic functionality

---

## Architecture Notes

### Why Virtualenv Inside Container?

ERDOS operators run **in-process** - they share the Python interpreter. If we installed PyTorch system-wide, TensorFlow operators would crash on `import numpy` due to version mismatch.

The virtualenv approach means:
1. Base container has TensorFlow + numpy 1.19.5
2. Venv has PyTorch 2.3.0 + numpy 2.x
3. When running ws_maskformer, activate venv first
4. Cannot run TF-based and PyTorch-based operators simultaneously

For true multi-framework support, would need:
- Out-of-process IPC (gRPC/ZMQ) for each framework
- Separate Python processes per operator type
- Significant architectural changes

### Operator Data Flow

```
CameraStream (BGR, 1920x1080)
    │
    ▼
WSMaskFormerDetectionOperator
    │
    ├── DefaultPredictor(frame) → BGR→RGB, resize, normalize
    │
    ├── Model inference → pred_masks, pred_classes, pred_scores, [pred_boxes]
    │
    ├── If no pred_boxes: BitMasks → get_bounding_boxes()
    │
    ├── Filter by score threshold + min area
    │
    ├── Map ADE20K class → Pylot label (or skip if unmapped)
    │
    └── Emit ObstaclesMessage([Obstacle, Obstacle, ...])
            │
            ▼
        Downstream operators (tracking, prediction, planning)
```
