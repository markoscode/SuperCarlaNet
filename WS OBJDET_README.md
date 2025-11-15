# WSObjDet Integration Guide

## Overview

This document describes the integration of the weakly-supervised object detection (wsobjdet) model trained with Mask2Former into the SuperCarlaNet/Pylot pipeline.

## Model Information

- **Model Path**: `/home/dsanyal7/wsobjdet/sem_ade_output_2/model_0004999.pth`
- **Model Type**: Mask2Former-based semantic segmentation
- **Training Dataset**: ADE20K (150 semantic classes)
- **Backbone**: ResNet-50
- **Training Method**: Weakly-supervised learning

## Files Modified/Created

### New Files

1. **`pylot/perception/detection/wsobjdet_operator.py`**
   - Main operator that loads the wsobjdet model
   - Converts semantic segmentation masks to object detections
   - Uses connected components analysis to extract bounding boxes

2. **`configs/wsobjdet.conf`**
   - Configuration file for running Pylot with wsobjdet
   - Sets all necessary flags and parameters

3. **`WSOBJDET_README.md`** (this file)
   - Documentation for the integration

### Modified Files

1. **`pylot/perception/flags.py`**
   - Added wsobjdet configuration flags:
     - `--wsobjdet_model_path`: Path to model checkpoint
     - `--wsobjdet_path`: Path to wsobjdet repository
     - `--wsobjdet_gpu_index`: GPU index for inference
     - `--wsobjdet_min_score_threshold`: Confidence threshold
     - `--wsobjdet_min_area`: Minimum detection area in pixels

2. **`pylot/operator_creator.py`**
   - Added `add_wsobjdet_obstacle_detection()` function
   - Creates and connects WSObjDetOperator to the pipeline

3. **`pylot/component_creator.py`**
   - Added wsobjdet detection path
   - Checks for 'wsobjdet' in model names to use WSObjDetOperator

## How It Works

### Detection Pipeline

1. **Input**: RGB camera frames from CARLA simulator
2. **Semantic Segmentation**: Mask2Former model predicts per-pixel class labels
3. **Post-Processing**:
   - Extract regions for relevant object classes (car, person, bicycle, etc.)
   - Use connected components analysis to find individual instances
   - Generate bounding boxes for each connected component
   - Filter by minimum area and confidence threshold
4. **Output**: ObstaclesMessage with detected objects

### Class Mapping

The operator maps ADE20K semantic classes to detection labels:

| ADE20K Class ID | Class Name | Detection Label |
|----------------|------------|-----------------|
| 21 | car | car |
| 84 | person | person |
| 104 | bicycle | bicycle |
| 126 | motorcycle | motorcycle |
| 81 | bus | bus |
| 83 | truck | truck |

**Note**: You may need to adjust these mappings based on the actual ADE20K class indices used in your model.

## Usage

### Option 1: Use the wsobjdet configuration file

```bash
python3 pylot.py --flagfile=configs/wsobjdet.conf
```

### Option 2: Add wsobjdet flags to existing config

Add these lines to your configuration file:

```
--obstacle_detection_model_names=wsobjdet
--wsobjdet_model_path=/home/dsanyal7/wsobjdet/sem_ade_output_2/model_0004999.pth
--wsobjdet_path=/home/dsanyal7/wsobjdet
--wsobjdet_gpu_index=0
--wsobjdet_min_score_threshold=0.5
--wsobjdet_min_area=100
```

### Option 3: Command-line flags

```bash
python3 pylot.py \
    --obstacle_detection \
    --obstacle_detection_model_names=wsobjdet \
    --wsobjdet_model_path=/home/dsanyal7/wsobjdet/sem_ade_output_2/model_0004999.pth \
    --wsobjdet_path=/home/dsanyal7/wsobjdet \
    --wsobjdet_gpu_index=0
```

## Configuration Parameters

### Required Parameters

- **`--wsobjdet_model_path`**: Path to the `.pth` checkpoint file
  - Default: `/home/dsanyal7/wsobjdet/sem_ade_output_2/model_0004999.pth`

- **`--wsobjdet_path`**: Path to wsobjdet repository (for imports)
  - Default: `/home/dsanyal7/wsobjdet`

### Optional Parameters

- **`--wsobjdet_gpu_index`**: GPU device index (default: 0)
- **`--wsobjdet_min_score_threshold`**: Minimum confidence score (default: 0.5)
- **`--wsobjdet_min_area`**: Minimum detection area in pixels (default: 100)

## Dependencies

The wsobjdet operator requires the following additional dependencies:

- Detectron2
- Mask2Former (from wsobjdet repository)
- PyTorch
- OpenCV (cv2)

These should already be installed if you successfully trained the wsobjdet model.

## Performance Considerations

### Advantages
- Trained with weak supervision (less annotation required)
- Uses semantic segmentation which can handle overlapping objects
- Can potentially generalize better to unseen scenarios

### Trade-offs
- Semantic segmentation is computationally more expensive than direct object detection
- Connected components analysis adds post-processing overhead
- May have different accuracy characteristics compared to fully-supervised detectors

### Optimization Tips

1. **Reduce image resolution**: Semantic segmentation models can run at lower resolutions
   ```
   --camera_image_width=640
   --camera_image_height=480
   ```

2. **Increase minimum area threshold**: Filter out small detections to reduce false positives
   ```
   --wsobjdet_min_area=200
   ```

3. **Adjust confidence threshold**: Balance precision vs recall
   ```
   --wsobjdet_min_score_threshold=0.6
   ```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'mask2former'`

**Solution**: Ensure wsobjdet path is correctly set:
```bash
--wsobjdet_path=/home/dsanyal7/wsobjdet
```

### Model Loading Errors

**Problem**: `FileNotFoundError: config.yaml not found`

**Solution**: The operator looks for `config.yaml` in the same directory as the model checkpoint. Ensure both files exist in `/home/dsanyal7/wsobjdet/sem_ade_output_2/`.

### GPU Memory Issues

**Problem**: CUDA out of memory

**Solution**:
1. Use a different GPU: `--wsobjdet_gpu_index=1`
2. Reduce image size (see Performance Considerations)
3. Disable other GPU-intensive operators

### No Detections

**Problem**: Operator runs but doesn't detect any objects

**Solution**:
1. Check class mapping in `wsobjdet_operator.py` matches your ADE20K model
2. Lower confidence threshold: `--wsobjdet_min_score_threshold=0.3`
3. Lower minimum area: `--wsobjdet_min_area=50`
4. Visualize output: `--visualize_detected_obstacles`

## Validation

To verify the integration is working:

1. **Check logs**: Look for "wsobjdet model loaded successfully" message
   ```bash
   grep "wsobjdet" pylot_wsobjdet.log
   ```

2. **Enable visualization**: Add to config:
   ```
   --visualize_rgb_camera
   --visualize_detected_obstacles
   ```

3. **Check timing logs**: Verify detections are being generated
   ```bash
   grep "detection runtime" pylot_wsobjdet.log
   ```

## Future Improvements

1. **Instance Segmentation**: Use instance masks directly instead of connected components
2. **Occlusion Handling**: Leverage depth information for better occlusion reasoning
3. **Temporal Consistency**: Add tracking to smooth detections over time
4. **Class-specific Thresholds**: Different confidence thresholds for different object classes
5. **Multi-scale Inference**: Run detection at multiple scales for better small object detection

## Contact

For issues specific to the wsobjdet model, refer to the original wsobjdet repository.
For integration issues with Pylot, check the SuperCarlaNet documentation.
