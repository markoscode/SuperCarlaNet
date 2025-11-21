# Model Interface Guide for SuperCarlaNet

## Overview

This document describes how models (particularly object detection models) are loaded and interfaced with in the SuperCarlaNet repository. This guide enables developers to design drop-in replacement systems or integrate new models.

## Architecture Pattern

SuperCarlaNet uses an **operator-based architecture** built on the ERDOS streaming framework. Each model is wrapped in an operator class that:
- Manages model loading and GPU configuration
- Processes incoming data streams (camera frames, time-to-decision updates)
- Performs inference
- Post-processes outputs into standardized message types
- Publishes results to output streams

**Key principle**: There is no abstract model interface. Instead, standardization occurs at the **operator level** through ERDOS streams and message types.

---

## 1. Operator Interface Contract

### Required Structure

All detection operators must inherit from `erdos.Operator` and implement:

#### 1.1 Constructor
```python
def __init__(self,
             camera_stream: erdos.ReadStream,
             time_to_decision_stream: erdos.ReadStream,
             obstacles_stream: erdos.WriteStream,
             model_path: str,
             flags):
    """
    Args:
        camera_stream: Input stream of camera frames
        time_to_decision_stream: Stream providing time-to-decision updates
        obstacles_stream: Output stream for detected obstacles
        model_path: Path to model checkpoint/weights
        flags: Global FLAGS object with configuration
    """
```

**Responsibilities**:
- Load model from `model_path`
- Configure GPU (device selection, memory allocation)
- Initialize internal state (object IDs, label mappings, etc.)
- Register stream callbacks

#### 1.2 Static Connection Method
```python
@staticmethod
def connect(camera_stream: erdos.ReadStream,
            time_to_decision_stream: erdos.ReadStream):
    """Define stream connections.

    Returns:
        List[erdos.WriteStream]: Output streams created by this operator
    """
    obstacles_stream = erdos.WriteStream()
    return [obstacles_stream]
```

#### 1.3 Callback Methods
```python
@erdos.profile_method()
def on_msg_camera_stream(self, msg: erdos.Message, obstacles_stream: erdos.WriteStream):
    """Process incoming camera frames.

    Args:
        msg: Message containing camera frame and timestamp
        obstacles_stream: Output stream to publish results
    """

def on_time_to_decision_update(self, msg: erdos.Message):
    """Handle time-to-decision updates (optional)."""

def destroy(self):
    """Cleanup resources on shutdown."""
```

---

## 2. Model Loading Patterns

### 2.1 TensorFlow 2.x SavedModel (Recommended for TF models)

**Example**: [detection_operator.py:55-56](pylot/perception/detection/detection_operator.py#L55-L56)

```python
import tensorflow as tf

# Load SavedModel
self._model = tf.saved_model.load(model_path)

# Configure GPU
physical_devices = tf.config.experimental.list_physical_devices('GPU')
tf.config.experimental.set_visible_devices(
    [physical_devices[flags.obstacle_detection_gpu_index]], 'GPU')
tf.config.experimental.set_memory_growth(
    physical_devices[flags.obstacle_detection_gpu_index], True)
```

**Model API Requirements**:
- Must be exported as TensorFlow SavedModel format
- Must have a signature named `'serving_default'`
- Expected signature:
  ```python
  infer = model.signatures['serving_default']
  result = infer(tf.convert_to_tensor(value=image_np_expanded))
  # image_np_expanded shape: [1, H, W, 3] (batch, height, width, channels)
  ```

**Expected Outputs**:
```python
result = {
    'boxes': tf.Tensor,      # Shape: [1, num_detections, 4] (ymin, xmin, ymax, xmax) normalized
    'scores': tf.Tensor,     # Shape: [1, num_detections]
    'classes': tf.Tensor,    # Shape: [1, num_detections] (integer class IDs)
    'detections': tf.Tensor  # Shape: [1] (number of valid detections)
}
```

### 2.2 TensorFlow 1.x Frozen Graph

**Example**: [efficientdet_operator.py:79-93](pylot/perception/detection/efficientdet_operator.py#L79-L93)

```python
import tensorflow.compat.v1 as tf

def load_serving_model(model_path, gpu_index, gpu_memory_fraction):
    detection_graph = tf.Graph()
    with detection_graph.as_default():
        graph_def = tf.GraphDef()
        with tf.io.gfile.GFile(model_path, 'rb') as f:
            graph_def.ParseFromString(f.read())
            tf.import_graph_def(graph_def, name='')

    gpu_options = tf.GPUOptions(
        allow_growth=True,
        visible_device_list=str(gpu_index),
        per_process_gpu_memory_fraction=gpu_memory_fraction)

    session = tf.Session(
        graph=detection_graph,
        config=tf.ConfigProto(gpu_options=gpu_options))

    return session
```

**Model API Requirements**:
- Model exported as `.pb` frozen graph
- Input tensor name accessible via graph
- Output tensors accessible via graph

### 2.3 PyTorch with Detectron2 (Mask2Former/DETR-style)

**Example**: [wsobjdet_operator.py:36-76](pylot/perception/detection/wsobjdet_operator.py#L36-L76)

```python
import torch
from detectron2.config import get_cfg
from detectron2.checkpoint import DetectionCheckpointer
from mask2former import add_maskformer2_config, MaskFormer

# Load configuration
cfg = get_cfg()
add_maskformer2_config(cfg)  # Register custom config groups

# Merge from saved config
config_file = os.path.join(os.path.dirname(model_path), 'config.yaml')
cfg.merge_from_file(config_file)
cfg.MODEL.WEIGHTS = model_path
cfg.MODEL.DEVICE = f'cuda:{gpu_index}'

# Build and load model
model = MaskFormer(cfg)
model.eval()

checkpointer = DetectionCheckpointer(model)
checkpointer.load(cfg.MODEL.WEIGHTS)
model = model.to(cfg.MODEL.DEVICE)
```

**Model API Requirements**:
- Must be a Detectron2-compatible model class
- Checkpoint file (`.pth`) with state dict
- Accompanying `config.yaml` with model architecture settings
- Expected input format:
  ```python
  inputs = [{"image": torch.Tensor,  # Shape: [3, H, W]
             "height": int,
             "width": int}]
  ```
- Expected output:
  ```python
  predictions = model(inputs)[0]  # Returns list of dicts
  {
      "sem_seg": torch.Tensor,  # Shape: [num_classes, H, W]
      # ... other task-specific outputs
  }
  ```

### 2.4 PyTorch Standard (State Dict)

**Example**: [segmentation_drn_operator.py:38-48](pylot/perception/segmentation/segmentation_drn_operator.py#L38-L48)

```python
import torch

# Define model architecture
model = DRNSeg(arch="drn_d_22", classes=19, pretrained=False)

# Load weights
model.load_state_dict(torch.load(model_path))

# Multi-GPU setup
if torch.cuda.is_available():
    model = torch.nn.DataParallel(model).cuda()

model.eval()
```

**Model API Requirements**:
- Model class definition must be importable
- Checkpoint is a state dict (`.pth` file)
- Model accepts tensors via `__call__` or `forward()`

---

## 3. Inference API Requirements

### 3.1 Input Format

Models receive inputs as **numpy arrays** (from camera frames):

```python
# Typical preprocessing
image_np = msg.frame.frame  # Shape: [H, W, 3], dtype: uint8, range: [0, 255]

# Framework-specific conversions:

# TensorFlow
image_np_expanded = np.expand_dims(image_np, axis=0)  # [1, H, W, 3]
infer = model.signatures['serving_default']
result = infer(tf.convert_to_tensor(value=image_np_expanded))

# PyTorch
image_tensor = torch.as_tensor(image_np.astype("float32").transpose(2, 0, 1))
image_tensor = image_tensor.to(device)  # [3, H, W]
```

**Standard input shape**: `[H, W, 3]` (height, width, channels in RGB order)

### 3.2 Output Format

Models must output information sufficient to construct `Obstacle` objects:

#### Required Fields:
```python
class Obstacle:
    bbox: BoundingBox2D  # (x_min, x_max, y_min, y_max) in pixel coordinates
    confidence: float     # Detection confidence [0.0, 1.0]
    label: str           # Class label ('car', 'person', 'bicycle', etc.)
    id: int              # Unique identifier
```

#### Detection Model Outputs (Bounding Box):
```python
# TensorFlow SavedModel format
{
    'boxes': [[ymin, xmin, ymax, xmax], ...],  # Normalized [0, 1]
    'scores': [score1, score2, ...],
    'classes': [class_id1, class_id2, ...],
    'detections': num_valid_detections
}
```

#### Segmentation Model Outputs (Semantic Masks):
```python
# PyTorch Detectron2 format
{
    'sem_seg': torch.Tensor  # Shape: [num_classes, H, W]
}

# Post-processing converts masks to bounding boxes via connected components
```

### 3.3 Inference Pattern Example

**TensorFlow 2.x SavedModel** - [detection_operator.py:158-175](pylot/perception/detection/detection_operator.py#L158-L175):
```python
def __run_model(self, image_np):
    # Prepare input
    image_np_expanded = np.expand_dims(image_np, axis=0)

    # Run inference
    infer = self._model.signatures['serving_default']
    result = infer(tf.convert_to_tensor(value=image_np_expanded))

    # Extract outputs
    boxes = result['boxes'].numpy()[0]
    scores = result['scores'].numpy()[0]
    classes = result['classes'].numpy()[0]
    num_detections = int(result['detections'].numpy()[0])

    return num_detections, boxes, scores, classes
```

**PyTorch Detectron2** - [wsobjdet_operator.py:142-158](pylot/perception/detection/wsobjdet_operator.py#L142-L158):
```python
with torch.no_grad():
    # Prepare input
    height, width = image.shape[:2]
    image_tensor = torch.as_tensor(image.astype("float32").transpose(2, 0, 1))
    image_tensor = image_tensor.to(self.device)

    inputs = [{"image": image_tensor, "height": height, "width": width}]

    # Get predictions
    predictions = self.model(inputs)[0]

    # Extract semantic segmentation
    if "sem_seg" in predictions:
        sem_seg = predictions["sem_seg"].argmax(dim=0).cpu().numpy()
```

---

## 4. Post-Processing Requirements

### 4.1 Convert Model Outputs to Obstacles

**Bounding Box Detections** - [detection_operator.py:120-141](pylot/perception/detection/detection_operator.py#L120-L141):
```python
from pylot.perception.detection.obstacle import Obstacle
from pylot.perception.detection.utils import BoundingBox2D

obstacles = []
for i in range(num_detections):
    if scores[i] >= min_score_threshold:
        # Convert normalized coordinates to pixel coordinates
        bbox = BoundingBox2D(
            int(boxes[i][1] * image_width),   # x_min
            int(boxes[i][3] * image_width),   # x_max
            int(boxes[i][0] * image_height),  # y_min
            int(boxes[i][2] * image_height)   # y_max
        )

        obstacle = Obstacle(
            bbox=bbox,
            confidence=scores[i],
            label=labels[int(classes[i])],
            id=self._unique_id
        )
        self._unique_id += 1
        obstacles.append(obstacle)
```

**Semantic Segmentation to Bounding Boxes** - [wsobjdet_operator.py:171-226](pylot/perception/detection/wsobjdet_operator.py#L171-L226):
```python
def _masks_to_obstacles(self, sem_seg, timestamp):
    """Convert semantic segmentation masks to obstacle bounding boxes."""
    obstacles = []

    for class_id, label_name in self.class_mapping.items():
        # Extract binary mask for this class
        mask = (sem_seg == class_id).astype(np.uint8)

        # Find connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=8)

        # Convert each component to bounding box
        for i in range(1, num_labels):  # Skip background (0)
            x, y, w, h, area = stats[i]

            # Filter small components
            if area < min_area_threshold:
                continue

            bbox = BoundingBox2D(x, x + w, y, y + h)
            obstacle = Obstacle(
                bbox=bbox,
                confidence=0.9,  # High confidence for segmentation
                label=label_name,
                id=self._unique_id
            )
            self._unique_id += 1
            obstacles.append(obstacle)

    return obstacles
```

### 4.2 Publish Results

```python
from pylot.perception.messages import ObstaclesMessage

# Create message
obstacles_msg = ObstaclesMessage(
    timestamp=msg.timestamp,
    obstacles=obstacles,
    runtime=inference_time_ms
)

# Send to output stream
obstacles_stream.send(obstacles_msg)
```

---

## 5. Configuration via Flags

### 5.1 Define Model-Specific Flags

**File**: [pylot/perception/flags.py](pylot/perception/flags.py)

```python
import absl

flags = absl.flags.FLAGS

# Basic detection flags
flags.DEFINE_string('obstacle_detection_model_path',
                    'dependencies/models/obstacle_detection/faster-rcnn/',
                    'Path to detection model')
flags.DEFINE_integer('obstacle_detection_gpu_index', 0,
                     'GPU device index')
flags.DEFINE_float('obstacle_detection_gpu_memory_fraction', 0.3,
                   'GPU memory fraction allocated')
flags.DEFINE_float('obstacle_detection_min_score_threshold', 0.5,
                   'Minimum confidence threshold')

# Custom model flags (example: WSObjDet)
flags.DEFINE_string('wsobjdet_model_path',
                    '/path/to/model.pth',
                    'Path to WSObjDet checkpoint')
flags.DEFINE_string('wsobjdet_config_path',
                    '/path/to/config.yaml',
                    'Path to model config')
flags.DEFINE_integer('wsobjdet_gpu_index', 0,
                     'GPU device index')
flags.DEFINE_float('wsobjdet_min_score_threshold', 0.5,
                   'Minimum confidence threshold')
```

### 5.2 Register Operator in Factory

**File**: [pylot/operator_creator.py](pylot/operator_creator.py)

```python
def add_my_custom_detection(camera_stream, time_to_decision_stream, csv_file_name=None):
    """Adds custom detection operator.

    Args:
        camera_stream: Input camera stream
        time_to_decision_stream: TTD stream
        csv_file_name: Optional CSV log file

    Returns:
        List[erdos.ReadStream]: Output obstacle streams
    """
    from pylot.perception.detection.my_custom_operator import MyCustomDetectionOperator

    op_config = erdos.OperatorConfig(
        name='my_custom_detection',
        flow_watermarks=False,
        log_file_name=FLAGS.log_file_name,
        csv_log_file_name=csv_file_name,
        profile_file_name=FLAGS.profile_file_name)

    [obstacles_stream] = erdos.connect(
        MyCustomDetectionOperator,
        op_config,
        [camera_stream, time_to_decision_stream],
        FLAGS.my_custom_model_path,
        FLAGS)

    return [obstacles_stream]
```

### 5.3 Add Component Creator Entry

**File**: [pylot/component_creator.py](pylot/component_creator.py)

```python
def add_obstacle_detection(center_camera_stream, ...):
    """High-level component for obstacle detection."""

    if FLAGS.obstacle_detection:
        if 'my_custom' in FLAGS.obstacle_detection_model_names:
            logger.debug('Using custom obstacle detector...')
            obstacles_streams = pylot.operator_creator.add_my_custom_detection(
                center_camera_stream, time_to_decision_stream, csv_file_name)
        # ... other model checks

    return obstacles_streams
```

---

## 6. Label Mapping

Models must use **COCO labels** or provide custom label mappings:

### 6.1 COCO Labels (Standard)

**File**: [pylot/perception/detection/utils.py](pylot/perception/detection/utils.py#L1-L30)

```python
COCO_LABELS = {
    1: 'person', 2: 'bicycle', 3: 'car', 4: 'motorcycle',
    5: 'airplane', 6: 'bus', 7: 'train', 8: 'truck',
    # ... (90 total categories)
}
```

### 6.2 Custom Labels

**Example**: WSObjDet - [wsobjdet_operator.py:78-87](pylot/perception/detection/wsobjdet_operator.py#L78-L87)

```python
self.class_mapping = {
    24: 'person',
    26: 'bicycle',
    20: 'car',
    # ... custom mapping
}
```

**Important**: Ensure label names match those expected by downstream operators (e.g., planning, tracking).

---

## 7. GPU Configuration Best Practices

### 7.1 TensorFlow GPU Setup

```python
import tensorflow as tf

physical_devices = tf.config.experimental.list_physical_devices('GPU')

# Set visible GPU
tf.config.experimental.set_visible_devices(
    [physical_devices[FLAGS.gpu_index]], 'GPU')

# Enable memory growth (recommended)
tf.config.experimental.set_memory_growth(
    physical_devices[FLAGS.gpu_index], True)

# OR set memory fraction
tf.config.experimental.set_virtual_device_configuration(
    physical_devices[FLAGS.gpu_index],
    [tf.config.experimental.VirtualDeviceConfiguration(
        memory_limit=FLAGS.gpu_memory_fraction * 1024)])  # MB
```

### 7.2 PyTorch GPU Setup

```python
import torch

device = f'cuda:{FLAGS.gpu_index}' if torch.cuda.is_available() else 'cpu'
model = model.to(device)
```

---

## 8. Drop-In Model Replacement Checklist

To create a drop-in replacement model:

- [ ] **Create operator class** inheriting from `erdos.Operator`
- [ ] **Implement required methods**:
  - [ ] `__init__(camera_stream, time_to_decision_stream, obstacles_stream, model_path, flags)`
  - [ ] `connect(camera_stream, time_to_decision_stream)` (static method)
  - [ ] `on_msg_camera_stream(msg, obstacles_stream)`
  - [ ] `destroy()`
- [ ] **Load model** in constructor using appropriate framework pattern
- [ ] **Configure GPU** using flags
- [ ] **Implement inference** that accepts `[H, W, 3]` numpy arrays
- [ ] **Post-process outputs** to `Obstacle` objects with:
  - [ ] `BoundingBox2D` in pixel coordinates
  - [ ] `confidence` score
  - [ ] `label` (COCO-compatible or custom)
  - [ ] `id` (unique per detection)
- [ ] **Send ObstaclesMessage** to output stream
- [ ] **Define flags** in [pylot/perception/flags.py](pylot/perception/flags.py)
- [ ] **Register in operator_creator.py** factory function
- [ ] **Add to component_creator.py** conditional logic
- [ ] **Test** with example scenarios

---

## 9. Example: Minimal Detection Operator Template

```python
import erdos
import numpy as np
import tensorflow as tf  # or torch

from pylot.perception.detection.obstacle import Obstacle
from pylot.perception.detection.utils import BoundingBox2D
from pylot.perception.messages import ObstaclesMessage


class MyDetectionOperator(erdos.Operator):
    """Custom detection operator template."""

    def __init__(self, camera_stream, time_to_decision_stream,
                 obstacles_stream, model_path, flags):
        """Initialize model and GPU configuration."""
        camera_stream.add_callback(self.on_msg_camera_stream,
                                   [obstacles_stream])
        erdos.add_watermark_callback([camera_stream],
                                     [obstacles_stream],
                                     self.on_watermark)

        self._flags = flags
        self._logger = erdos.utils.setup_logging(self.config.name,
                                                  self.config.log_file_name)
        self._unique_id = 0

        # Load model
        self._model = self._load_model(model_path)

        # Configure GPU
        self._configure_gpu()

    def _load_model(self, model_path):
        """Load model from checkpoint."""
        # TensorFlow example
        model = tf.saved_model.load(model_path)
        return model

    def _configure_gpu(self):
        """Configure GPU device and memory."""
        physical_devices = tf.config.experimental.list_physical_devices('GPU')
        tf.config.experimental.set_visible_devices(
            [physical_devices[self._flags.my_model_gpu_index]], 'GPU')
        tf.config.experimental.set_memory_growth(
            physical_devices[self._flags.my_model_gpu_index], True)

    @staticmethod
    def connect(camera_stream, time_to_decision_stream):
        """Define stream connections."""
        obstacles_stream = erdos.WriteStream()
        return [obstacles_stream]

    @erdos.profile_method()
    def on_msg_camera_stream(self, msg, obstacles_stream):
        """Process camera frame."""
        self._logger.debug(f'@{msg.timestamp}: received frame')

        # Run inference
        image_np = msg.frame.frame  # [H, W, 3]
        obstacles = self._run_inference(image_np, msg.timestamp)

        # Send results
        obstacles_msg = ObstaclesMessage(msg.timestamp, obstacles)
        obstacles_stream.send(obstacles_msg)

    def _run_inference(self, image_np, timestamp):
        """Run model inference and post-process."""
        # Inference
        infer = self._model.signatures['serving_default']
        image_expanded = np.expand_dims(image_np, axis=0)
        result = infer(tf.convert_to_tensor(value=image_expanded))

        # Post-process
        boxes = result['boxes'].numpy()[0]
        scores = result['scores'].numpy()[0]
        classes = result['classes'].numpy()[0]
        num_detections = int(result['detections'].numpy()[0])

        # Convert to obstacles
        obstacles = []
        height, width = image_np.shape[:2]

        for i in range(num_detections):
            if scores[i] >= self._flags.my_model_min_score_threshold:
                bbox = BoundingBox2D(
                    int(boxes[i][1] * width),   # x_min
                    int(boxes[i][3] * width),   # x_max
                    int(boxes[i][0] * height),  # y_min
                    int(boxes[i][2] * height)   # y_max
                )

                obstacle = Obstacle(
                    bbox=bbox,
                    confidence=scores[i],
                    label=self._get_label(int(classes[i])),
                    id=self._unique_id
                )
                self._unique_id += 1
                obstacles.append(obstacle)

        return obstacles

    def _get_label(self, class_id):
        """Map class ID to label string."""
        from pylot.perception.detection.utils import COCO_LABELS
        return COCO_LABELS.get(class_id, 'unknown')

    def on_watermark(self, timestamp, obstacles_stream):
        """Handle watermark."""
        obstacles_stream.send(erdos.WatermarkMessage(timestamp))

    def destroy(self):
        """Cleanup resources."""
        self._logger.info('Destroying operator')
```

---

## 10. Reference Files

### Core Implementation Files
- Detection operator: [pylot/perception/detection/detection_operator.py](pylot/perception/detection/detection_operator.py)
- WSObjDet operator: [pylot/perception/detection/wsobjdet_operator.py](pylot/perception/detection/wsobjdet_operator.py)
- EfficientDet operator: [pylot/perception/detection/efficientdet_operator.py](pylot/perception/detection/efficientdet_operator.py)
- Traffic light detection: [pylot/perception/detection/traffic_light_det_operator.py](pylot/perception/detection/traffic_light_det_operator.py)

### Configuration Files
- Flags definition: [pylot/perception/flags.py](pylot/perception/flags.py)
- Operator factory: [pylot/operator_creator.py](pylot/operator_creator.py)
- Component factory: [pylot/component_creator.py](pylot/component_creator.py)

### Data Types
- Obstacle class: [pylot/perception/detection/obstacle.py](pylot/perception/detection/obstacle.py)
- Messages: [pylot/perception/messages.py](pylot/perception/messages.py)
- Utils: [pylot/perception/detection/utils.py](pylot/perception/detection/utils.py)

---

## 11. Common Patterns Summary

| Pattern | Framework | Loading | Inference | Example |
|---------|-----------|---------|-----------|---------|
| SavedModel | TensorFlow 2.x | `tf.saved_model.load()` | `model.signatures['serving_default'](tensor)` | [detection_operator.py](pylot/perception/detection/detection_operator.py) |
| Frozen Graph | TensorFlow 1.x | `tf.Session()` with graph | `session.run(outputs, feed_dict)` | [efficientdet_operator.py](pylot/perception/detection/efficientdet_operator.py) |
| Detectron2 | PyTorch | `DetectionCheckpointer.load()` | `model([{image, height, width}])` | [wsobjdet_operator.py](pylot/perception/detection/wsobjdet_operator.py) |
| State Dict | PyTorch | `model.load_state_dict(torch.load())` | `model(tensor)` | [segmentation_drn_operator.py](pylot/perception/segmentation/segmentation_drn_operator.py) |

---

## Questions?

For issues or questions about integrating new models, refer to:
- ERDOS documentation: https://github.com/erdos-project/erdos
- SuperCarlaNet repository: https://github.com/your-repo/SuperCarlaNet
- Existing operator implementations in [pylot/perception/](pylot/perception/)
