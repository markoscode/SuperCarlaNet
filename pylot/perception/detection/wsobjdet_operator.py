"""Weakly-Supervised Object Detection Operator using Mask2Former model."""

import erdos
import numpy as np
import torch
import cv2
import time

from pylot.perception.detection.utils import BoundingBox2D
from pylot.perception.detection.obstacle import Obstacle
from pylot.perception.messages import ObstaclesMessage
from pylot.utils.scn_timing import track_operator_time


class WSObjDetOperator(erdos.Operator):
    """Operator for weakly-supervised object detection using trained wsobjdet model.

    This operator loads a Mask2Former-based semantic segmentation model trained
    with weak supervision and converts semantic masks to object detections.

    Args:
        camera_stream: Stream of camera frames
        obstacles_stream: Output stream for detected obstacles
        flags: Configuration flags
        name: Operator name
    """

    def __init__(self, camera_stream, time_to_decision_stream, obstacles_stream, model_path, flags):
        camera_stream.add_callback(self.on_msg_camera_stream, [obstacles_stream])
        time_to_decision_stream.add_callback(self.on_time_to_decision_update)
        self._flags = flags
        self._logger = erdos.utils.setup_logging(self.config.name, self.config.log_file_name)
        self._obstacles_stream = obstacles_stream
        self._unique_id = 0

        # Import detectron2 and mask2former components
        try:
            from detectron2.config import get_cfg
            from detectron2.projects.deeplab import add_deeplab_config
            from detectron2.checkpoint import DetectionCheckpointer
            from detectron2.data import MetadataCatalog
            import sys
            import os

            # Add wsobjdet to path
            wsobjdet_path = flags.wsobjdet_path
            if wsobjdet_path not in sys.path:
                sys.path.insert(0, wsobjdet_path)

            from mask2former import add_maskformer2_config

            self._logger.info("Loading wsobjdet model from {}".format(model_path))

            # Setup configuration
            cfg = get_cfg()
            add_deeplab_config(cfg)
            add_maskformer2_config(cfg)

            # Load config from trained model directory
            config_file = os.path.join(os.path.dirname(model_path), 'config.yaml')
            cfg.merge_from_file(config_file)
            cfg.MODEL.WEIGHTS = model_path
            cfg.MODEL.DEVICE = 'cuda:{}'.format(flags.wsobjdet_gpu_index)

            # Build model
            from mask2former import MaskFormer
            self.model = MaskFormer(cfg)
            self.model.eval()

            # Load weights
            checkpointer = DetectionCheckpointer(self.model)
            checkpointer.load(cfg.MODEL.WEIGHTS)

            # Move to GPU
            self.model = self.model.to(cfg.MODEL.DEVICE)
            self.device = cfg.MODEL.DEVICE

            # Get metadata for ADE20K classes
            self.metadata = MetadataCatalog.get(cfg.DATASETS.TEST[0] if len(cfg.DATASETS.TEST) > 0 else "ade20k_sem_seg_val")
            self.num_classes = cfg.MODEL.SEM_SEG_HEAD.NUM_CLASSES

            # Mapping from ADE20K semantic classes to COCO-like object classes
            # We'll focus on vehicle-related and person classes
            self.class_mapping = self._create_class_mapping()

            self._logger.info("wsobjdet model loaded successfully with {} classes".format(self.num_classes))

        except Exception as e:
            self._logger.error("Failed to load wsobjdet model: {}".format(e))
            raise

    @staticmethod
    def connect(camera_stream: erdos.ReadStream,
                time_to_decision_stream: erdos.ReadStream):
        """Connects the operator to other streams.

        Args:
            camera_stream: The stream on which camera frames are received.
            time_to_decision_stream: Stream on which time to decision updates are received.

        Returns:
            List containing obstacles_stream
        """
        obstacles_stream = erdos.WriteStream()
        return [obstacles_stream]

    def destroy(self):
        self._logger.warn('destroying {}'.format(self.config.name))
        self._obstacles_stream.send(
            erdos.WatermarkMessage(erdos.Timestamp(is_top=True)))

    def on_time_to_decision_update(self, msg: erdos.Message):
        self._logger.debug('@{}: {} received ttd update {}'.format(
            msg.timestamp, self.config.name, msg))

    def _create_class_mapping(self):
        """Create mapping from ADE20K classes to detection labels."""
        # ADE20K index to detection label mapping
        # Based on common ADE20K classes (you may need to adjust these)
        mapping = {
            21: 'car',           # car
            84: 'person',        # person
            104: 'bicycle',      # bicycle
            126: 'motorcycle',   # motorcycle/motorbike
            81: 'bus',           # bus
            83: 'truck',         # truck
        }
        return mapping

    @erdos.profile_method()
    @track_operator_time('detection')
    def on_msg_camera_stream(self, msg, obstacles_stream):
        """Callback for camera frames."""
        self._logger.debug("@{}: received frame".format(msg.timestamp))

        start_time = time.time()

        # Convert frame to RGB (model expects RGB)
        image = msg.frame.as_rgb_numpy_array()

        # Run inference
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
            else:
                self._logger.warning("No semantic segmentation in predictions")
                sem_seg = np.zeros((height, width), dtype=np.int32)

        # Convert semantic masks to bounding boxes
        obstacles = self._masks_to_obstacles(sem_seg, msg.timestamp)

        # Log timing
        runtime = (time.time() - start_time) * 1000
        self._logger.debug("@{}: detection runtime: {:.2f}ms, {} obstacles".format(msg.timestamp, runtime, len(obstacles)))

        # Send obstacles
        obstacles_stream.send(ObstaclesMessage(msg.timestamp, obstacles, runtime))
        obstacles_stream.send(erdos.WatermarkMessage(msg.timestamp))

    def _masks_to_obstacles(self, sem_seg, timestamp):
        """Convert semantic segmentation masks to obstacle bounding boxes.

        Args:
            sem_seg: Semantic segmentation mask (H x W)
            timestamp: Message timestamp

        Returns:
            List of DetectedObstacle objects
        """
        obstacles = []

        # Get unique class IDs in the segmentation
        unique_classes = np.unique(sem_seg)

        for class_id in unique_classes:
            if class_id == 0 or class_id >= self.num_classes:
                continue  # Skip background and invalid classes

            # Check if this class maps to a detection label
            if class_id not in self.class_mapping:
                continue

            label = self.class_mapping[class_id]

            # Create binary mask for this class
            mask = (sem_seg == class_id).astype(np.uint8)

            # Find connected components
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

            # Process each connected component
            for i in range(1, num_labels):  # Skip background (0)
                x, y, w, h, area = stats[i]

                # Filter small regions
                if area < self._flags.wsobjdet_min_area:
                    continue

                # Create bounding box
                bbox = BoundingBox2D(x, x + w, y, y + h)

                # Estimate confidence based on mask area and density
                component_mask = (labels == i).astype(np.uint8)
                density = area / (w * h) if (w * h) > 0 else 0
                confidence = min(0.5 + density * 0.5, 1.0)  # Base confidence 0.5-1.0

                if confidence < self._flags.wsobjdet_min_score_threshold:
                    continue

                # Create obstacle
                obstacle = Obstacle(bbox, confidence, label, id=self._unique_id)
                obstacles.append(obstacle)
                self._unique_id += 1

        return obstacles
