#!/usr/bin/env python3
"""
Standalone sanity-check script for the ws Mask2Former detector.

Loads the Mask2Former config/weights, runs inference on a provided image,
prints the detections, and optionally saves an annotated visualization.
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

from pylot.perception.detection.utils import BoundingBox2D, OBSTACLE_LABELS, \
    PYLOT_BBOX_COLOR_MAP


def _maybe_extend_path(path: str):
    if path and os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


ADE_TO_PYLOT = {
    'person, individual, someone, somebody, mortal, soul': 'person',
    'car, auto, automobile, machine, motorcar': 'car',
    'bus, autobus, coach, charabanc, double-decker, jitney, motorbus, motorcoach, omnibus, passenger vehicle': 'bus',
    'truck, motortruck': 'truck',
    'minibike, motorbike': 'motorcycle',
    'bicycle, bike, wheel, cycle': 'bicycle',
}

MODEL_NETWORK_CONFIGS = {
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


def load_predictor(args):
    ws_root = os.path.abspath(args.ws_repo_root)
    _maybe_extend_path(ws_root)
    _maybe_extend_path(os.path.join(ws_root, 'mask2former'))

    from detectron2.config import get_cfg
    from detectron2.data import MetadataCatalog
    from detectron2.structures import BitMasks
    from mask2former import add_maskformer2_config
    from mask2former.engine.defaults import DefaultPredictor

    cfg = get_cfg()
    add_maskformer2_config(cfg)
    cfg.merge_from_file(args.config)
    cfg.MODEL.WEIGHTS = args.weights
    cfg.MODEL.MASK_FORMER.TEST.INSTANCE_ON = True
    cfg.MODEL.MASK_FORMER.TEST.SEMANTIC_ON = False
    cfg.MODEL.MASK_FORMER.TEST.PANOPTIC_ON = False

    if args.gpu_index is not None:
        cfg.MODEL.DEVICE = f'cuda:{args.gpu_index}'
    predictor = DefaultPredictor(cfg)

    model = predictor.model
    subnet_cfg = MODEL_NETWORK_CONFIGS.get(args.subnet, {})
    if hasattr(model, 'set_max_net'):
        model.set_max_net()
        if subnet_cfg:
            if 'backbone' in subnet_cfg:
                model.backbone.set_active_subnet(depth_list=subnet_cfg['backbone'])
            if 'predictor' in subnet_cfg:
                model.sem_seg_head.predictor.set_active_subnet(subnet_cfg['predictor'])
            if 'pixel_decoder' in subnet_cfg:
                model.sem_seg_head.pixel_decoder.transformer\
                    .set_active_subnet(subnet_cfg['pixel_decoder'])

    metadata = None
    if len(cfg.DATASETS.TRAIN):
        metadata = MetadataCatalog.get(cfg.DATASETS.TRAIN[0])
    elif len(cfg.DATASETS.TEST):
        metadata = MetadataCatalog.get(cfg.DATASETS.TEST[0])

    return predictor, metadata, BitMasks


def build_label_map(metadata):
    mapping = {}
    if metadata and hasattr(metadata, 'stuff_classes'):
        for idx, name in enumerate(metadata.stuff_classes):
            normalized = name.strip().lower()
            pylot_label = ADE_TO_PYLOT.get(normalized, None)
            if pylot_label:
                mapping[idx] = pylot_label
    if not mapping and metadata and hasattr(metadata, 'thing_classes'):
        for idx, name in enumerate(metadata.thing_classes):
            normalized = name.strip().lower()
            pylot_label = ADE_TO_PYLOT.get(normalized, None)
            if pylot_label:
                mapping[idx] = pylot_label
    if not mapping:
        mapping = {
            11: 'person',
            14: 'car',
            80: 'bus',
            93: 'truck',
            103: 'motorcycle',
            108: 'bicycle',
        }
    return mapping


def convert_instances(instances, metadata, bitmask_cls,
                      min_area, min_score):
    results = []
    label_map = build_label_map(metadata)
    if instances is None:
        return results
    instances = instances.to('cpu')
    if (not hasattr(instances, 'pred_boxes') or
            instances.pred_boxes is None or
            len(instances.pred_boxes.tensor) == 0):
        if hasattr(instances, 'pred_masks') and len(instances) > 0:
            bitmasks = bitmask_cls((instances.pred_masks > 0).numpy())
            instances.pred_boxes = bitmasks.get_bounding_boxes()
    num_instances = len(instances)
    for idx in range(num_instances):
        score = float(instances.scores[idx])
        if score < min_score:
            continue
        bbox = instances.pred_boxes.tensor[idx].cpu().numpy().tolist()
        x_min, y_min, x_max, y_max = bbox
        width = x_max - x_min
        height = y_max - y_min
        if width <= 0 or height <= 0:
            continue
        if width * height < min_area:
            continue
        class_idx = int(instances.pred_classes[idx])
        label_name = label_map.get(class_idx)
        if label_name is None or label_name not in OBSTACLE_LABELS:
            continue
        bbox2d = BoundingBox2D(int(x_min), int(x_max),
                               int(y_min), int(y_max))
        results.append({
            'label': label_name,
            'score': score,
            'bbox': bbox2d
        })
    return results


def annotate(image, obstacles):
    annotated = image.copy()
    for obstacle in obstacles:
        bbox = obstacle['bbox']
        label = obstacle['label']
        score = obstacle['score']
        if label in PYLOT_BBOX_COLOR_MAP:
            color = PYLOT_BBOX_COLOR_MAP[label]
        else:
            color = [0, 255, 0]
        cv2.rectangle(annotated, (bbox.x_min, bbox.y_min),
                      (bbox.x_max, bbox.y_max), color, 2)
        cv2.putText(annotated,
                    f'{label}:{score:.2f}',
                    (bbox.x_min, max(0, bbox.y_min - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                    cv2.LINE_AA)
    return annotated


def main():
    parser = argparse.ArgumentParser(
        description='Run Mask2Former WS detector on a single image.')
    parser.add_argument('--config', required=True,
                        help='Path to Mask2Former YAML config.')
    parser.add_argument('--weights', required=True,
                        help='Path to Mask2Former checkpoint.')
    parser.add_argument('--image', required=True,
                        help='Path to BGR image to test.')
    parser.add_argument('--ws_repo_root', default='../wsobjdet',
                        help='Root directory for wsobjdet repo.')
    parser.add_argument('--gpu_index', type=int, default=0,
                        help='GPU index (set to -1 for CPU).')
    parser.add_argument('--subnet', default='max',
                        choices=list(MODEL_NETWORK_CONFIGS.keys()),
                        help='Which subnet to activate.')
    parser.add_argument('--min_score', type=float, default=0.3,
                        help='Minimum confidence.')
    parser.add_argument('--min_area', type=float, default=200,
                        help='Min pixel area for detections.')
    parser.add_argument('--output', default=None,
                        help='Optional path to save annotated image.')

    args = parser.parse_args()
    if args.gpu_index < 0:
        args.gpu_index = None

    predictor, metadata, bitmask_cls = load_predictor(args)

    image = cv2.imread(args.image)
    if image is None:
        raise RuntimeError('Failed to read image {}'.format(args.image))

    start = time.time()
    outputs = predictor(image)
    runtime = (time.time() - start) * 1000

    instances = outputs.get('instances', None)
    obstacles = convert_instances(instances, metadata,
                                  bitmask_cls, args.min_area,
                                  args.min_score)

    print('Inference time: {:.2f} ms'.format(runtime))
    print('Detections:')
    for idx, obstacle in enumerate(obstacles):
        bbox = obstacle['bbox']
        print('[{}] {:<10s} score={:.2f} bbox=({}, {}, {}, {})'.format(
            idx, obstacle['label'], obstacle['score'],
            bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max))

    if args.output:
        annotated = annotate(image, obstacles)
        cv2.imwrite(args.output, annotated)
        print('Annotated image saved to {}'.format(args.output))


if __name__ == '__main__':
    main()
