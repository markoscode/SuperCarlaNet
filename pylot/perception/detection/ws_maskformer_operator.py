import os
import sys
import time
from typing import Dict

import erdos

from pylot.perception.detection.obstacle import Obstacle
from pylot.perception.detection.utils import BoundingBox2D, OBSTACLE_LABELS
from pylot.perception.messages import ObstaclesMessage
from pylot.utils.scn_timing import track_operator_time


def _maybe_extend_path(path: str):
    if path and os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


class MissingDependencyError(RuntimeError):
    pass


class WSMaskFormerDetectionOperator(erdos.Operator):
    """Runs a Mask2Former weight-sharing model as a detection operator."""

    _ADE_TO_PYLOT = {
        'person, individual, someone, somebody, mortal, soul': 'person',
        'car, auto, automobile, machine, motorcar': 'car',
        'bus, autobus, coach, charabanc, double-decker, jitney, motorbus, motorcoach, omnibus, passenger vehicle': 'bus',
        'truck, motortruck': 'truck',
        'minibike, motorbike': 'motorcycle',
        'bicycle, bike, wheel, cycle': 'bicycle',
    }

    _MODEL_NETWORK_CONFIGS: Dict[str, Dict[str, list]] = {
        "min": {
            "backbone": [0, 0, 0, 0],
            "pixel_decoder": [0],
            "predictor": [0]
        },
        "min_backbone": {
            "backbone": [0, 0, 0, 0]
        },
        "middle": {
            "backbone": [1, 1, 1, 1],
            "pixel_decoder": [1],
            "predictor": [1]
        },
        "middle_backbone_min_transformer_decoder": {
            "backbone": [1, 1, 1, 1],
            "pixel_decoder": [2],
            "predictor": [0]
        },
        "middle_backbone": {
            "backbone": [1, 1, 1, 1]
        },
        "min_pixel_decoder": {
            "pixel_decoder": [0],
        },
        "min_transformer_decoder": {
            "predictor": [0],
        },
        "max": {}
    }

    def __init__(self, camera_stream: erdos.ReadStream,
                 time_to_decision_stream: erdos.ReadStream,
                 obstacles_stream: erdos.WriteStream, flags):
        camera_stream.add_callback(self.on_msg_camera_stream,
                                   [obstacles_stream])
        time_to_decision_stream.add_callback(self.on_time_to_decision_update)
        self._flags = flags
        self._logger = erdos.utils.setup_logging(self.config.name,
                                                 self.config.log_file_name)
        self._obstacles_stream = obstacles_stream
        self._unique_id = 0
        self._last_ttd = 0.0
        self._min_mask_area = self._flags.ws_maskformer_min_mask_area

        self._predictor = None
        self._class_name_to_label = {}
        self._class_index_to_pylot: Dict[int, str] = {}

        self._load_predictor()

    @staticmethod
    def connect(camera_stream: erdos.ReadStream,
                time_to_decision_stream: erdos.ReadStream):
        obstacles_stream = erdos.WriteStream()
        return [obstacles_stream]

    def destroy(self):
        self._logger.warn('destroying {}'.format(self.config.name))
        self._obstacles_stream.send(
            erdos.WatermarkMessage(erdos.Timestamp(is_top=True)))

    def _load_predictor(self):
        ws_root = os.path.abspath(self._flags.ws_maskformer_repo_root)
        _maybe_extend_path(ws_root)
        _maybe_extend_path(os.path.join(ws_root, 'mask2former'))
        try:
            from detectron2.config import get_cfg
            from detectron2.data import MetadataCatalog
            from detectron2.structures import BitMasks
            from mask2former import add_maskformer2_config
            from mask2former.engine.defaults import DefaultPredictor
        except ImportError as err:
            raise MissingDependencyError(
                'Detectron2 / Mask2Former not available: {}'.format(err))

        if not self._flags.ws_maskformer_config_path or \
                not self._flags.ws_maskformer_weights_path:
            raise ValueError('Must set ws_maskformer_config_path and '
                             'ws_maskformer_weights_path')

        cfg = get_cfg()
        add_maskformer2_config(cfg)
        cfg.merge_from_file(self._flags.ws_maskformer_config_path)
        cfg.MODEL.WEIGHTS = self._flags.ws_maskformer_weights_path
        cfg.MODEL.MASK_FORMER.TEST.INSTANCE_ON = True
        cfg.MODEL.MASK_FORMER.TEST.SEMANTIC_ON = False
        cfg.MODEL.MASK_FORMER.TEST.PANOPTIC_ON = False
        if self._flags.obstacle_detection_gpu_index is not None:
            cfg.MODEL.DEVICE = f'cuda:{self._flags.obstacle_detection_gpu_index}'
        self._predictor = DefaultPredictor(cfg)
        self._metadata = None
        if len(cfg.DATASETS.TRAIN):
            self._metadata = MetadataCatalog.get(cfg.DATASETS.TRAIN[0])
        elif len(cfg.DATASETS.TEST):
            self._metadata = MetadataCatalog.get(cfg.DATASETS.TEST[0])

        # Build label map from metadata names to Pylot's labels.
        if self._metadata and hasattr(self._metadata, 'stuff_classes'):
            for idx, name in enumerate(self._metadata.stuff_classes):
                normalized = name.strip().lower()
                if normalized in self._normalize_label_map().keys():
                    pylot_label = self._normalize_label_map()[normalized]
                    self._class_index_to_pylot[idx] = pylot_label

        # Default to specific strings if metadata lookup failed.
        if not self._class_index_to_pylot and self._metadata:
            for idx, name in enumerate(getattr(self._metadata, 'thing_classes', [])):
                normalized = name.strip().lower()
                if normalized in self._normalize_label_map():
                    self._class_index_to_pylot[idx] = self._normalize_label_map()[normalized]

        model = self._predictor.model
        subnet_name = self._flags.ws_maskformer_subnet
        subnet_cfg = self._MODEL_NETWORK_CONFIGS.get(subnet_name, {})
        if hasattr(model, 'set_max_net'):
            model.set_max_net()
            if subnet_cfg:
                self._logger.info('Activating ws subnet: {}'.format(subnet_name))
                if 'backbone' in subnet_cfg and hasattr(
                        model.backbone, 'set_active_subnet'):
                    model.backbone.set_active_subnet(
                        depth_list=subnet_cfg['backbone'])
                if 'predictor' in subnet_cfg and hasattr(
                        model.sem_seg_head.predictor, 'set_active_subnet'):
                    model.sem_seg_head.predictor.set_active_subnet(
                        subnet_cfg['predictor'])
                if 'pixel_decoder' in subnet_cfg and hasattr(
                        model.sem_seg_head.pixel_decoder, 'transformer'):
                    model.sem_seg_head.pixel_decoder.transformer\
                        .set_active_subnet(subnet_cfg['pixel_decoder'])
        else:
            if subnet_name != 'max':
                self._logger.warn(
                    'Model does not expose weight-sharing hooks; running max net')

        self._BitMasks = BitMasks

        if not self._class_index_to_pylot:
            # Hard-coded ADE20K fallbacks.
            self._class_index_to_pylot = {
                11: 'person',
                14: 'car',
                80: 'bus',
                93: 'truck',
                103: 'motorcycle',
                108: 'bicycle',
            }
            self._logger.warn(
                'Metadata mapping unavailable, using ADE20K class index defaults')

    def _normalize_label_map(self):
        if not self._class_name_to_label:
            for ade_name, pylot_name in self._ADE_TO_PYLOT.items():
                self._class_name_to_label[ade_name.strip().lower()] = pylot_name
        return self._class_name_to_label

    def _map_class(self, class_index: int, default_name: str = ''):
        if class_index in self._class_index_to_pylot:
            return self._class_index_to_pylot[class_index]
        normalized = default_name.strip().lower()
        return self._normalize_label_map().get(normalized, None)

    def on_time_to_decision_update(self, msg: erdos.Message):
        self._logger.debug('@{}: {} received ttd update {}'.format(
            msg.timestamp, self.config.name, msg))
        if isinstance(msg.data, (int, float)):
            self._last_ttd = float(msg.data)

    @erdos.profile_method()
    @track_operator_time('detection')
    def on_msg_camera_stream(self, msg: erdos.Message,
                             obstacles_stream: erdos.WriteStream):
        start_time = time.time()
        obstacles = []
        if self._predictor is None:
            self._logger.error('Predictor not initialized; dropping frame')
        else:
            detections = self._predictor(msg.frame.frame)
            instances = detections.get('instances', None)
            if instances is not None:
                instances = instances.to('cpu')
                if (not hasattr(instances, 'pred_boxes') or
                        instances.pred_boxes is None or
                        len(instances.pred_boxes.tensor) == 0):
                    if hasattr(instances, 'pred_masks') and len(instances) > 0:
                        bitmasks = self._BitMasks(
                            (instances.pred_masks > 0).numpy())
                        boxes = bitmasks.get_bounding_boxes()
                        instances.pred_boxes = boxes
                num_instances = len(instances)
                for idx in range(num_instances):
                    score = float(instances.scores[idx])
                    if score < self._flags.obstacle_detection_min_score_threshold:
                        continue
                    box_tensor = instances.pred_boxes.tensor[idx].cpu().numpy()
                    x_min, y_min, x_max, y_max = box_tensor.tolist()
                    width = x_max - x_min
                    height = y_max - y_min
                    if width <= 0 or height <= 0:
                        continue
                    if width * height < self._min_mask_area:
                        continue
                    class_idx = int(instances.pred_classes[idx])
                    label_name = None
                    if self._metadata and hasattr(self._metadata, 'stuff_classes') \
                            and class_idx < len(self._metadata.stuff_classes):
                        label_name = self._metadata.stuff_classes[class_idx]
                    pylot_label = self._map_class(class_idx,
                                                  label_name or '')
                    if pylot_label is None or pylot_label not in OBSTACLE_LABELS:
                        continue
                    bbox2d = BoundingBox2D(int(x_min), int(x_max), int(y_min),
                                           int(y_max))
                    obstacles.append(
                        Obstacle(bbox2d,
                                 score,
                                 pylot_label,
                                 id=self._unique_id))
                    self._unique_id += 1

        runtime = (time.time() - start_time) * 1000
        obstacles_stream.send(
            ObstaclesMessage(msg.timestamp, obstacles, runtime))
        obstacles_stream.send(erdos.WatermarkMessage(msg.timestamp))
