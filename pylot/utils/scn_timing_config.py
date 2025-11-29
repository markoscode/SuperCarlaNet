"""
Central configuration for Pylot pipeline timing instrumentation.

This module defines which operators should be instrumented with Tier 2
(operator response time) timing tracking. Each entry maps an operator
to its timing stage name.

To instrument a new operator:
1. Add entry to OPERATOR_TIMING_CONFIG mapping file path to stage name
2. Import and apply @track_operator_time(stage) decorator to callback
3. Stage name should be lowercase, descriptive (e.g., 'detection', 'tracking')
"""

# Tier 2: Operator response time tracking
# Format: 'relative/path/to/operator.py': 'stage_name'
OPERATOR_TIMING_CONFIG = {
    # Perception - Detection
    'pylot/perception/detection/detection_operator.py': 'detection',
    'pylot/perception/detection/ws_maskformer_operator.py': 'detection',
    'pylot/perception/detection/ws_maskformer_grpc_operator.py': 'detection_grpc',
    'pylot/perception/detection/lanenet_detection_operator.py': 'lane_detection',
    'pylot/perception/detection/traffic_light_det_operator.py': 'traffic_light_detection',
    'pylot/perception/detection/efficientdet_operator.py': 'efficient_detection',

    # Perception - Segmentation
    'pylot/perception/segmentation/segmentation_drn_operator.py': 'segmentation',

    # Perception - Tracking
    'pylot/perception/tracking/object_tracker_operator.py': 'tracking',

    # Localization
    'pylot/localization/localization_operator.py': 'localization',

    # Prediction
    'pylot/prediction/linear_predictor_operator.py': 'prediction',
    'pylot/prediction/r2p2_predictor_operator.py': 'r2p2_prediction',

    # Planning
    'pylot/planning/planning_operator.py': 'planning',
    'pylot/planning/behavior_planning_operator.py': 'behavior_planning',

    # Control
    'pylot/control/pid_control_operator.py': 'control',
    'pylot/control/mpc/mpc_operator.py': 'mpc_control',
}

# Tier 3: Pipeline boundary stages for end-to-end latency
PIPELINE_STAGES = {
    'sensor_input': 'Entry point when sensor data enters pipeline',
    'actuator_output': 'Exit point when control commands are sent to actuators',
}


def get_stage_for_operator(operator_file_path: str) -> str:
    """
    Get the timing stage name for a given operator file path.

    Args:
        operator_file_path: Relative path to operator file

    Returns:
        Stage name string, or None if operator not configured for timing
    """
    return OPERATOR_TIMING_CONFIG.get(operator_file_path)


def get_all_instrumented_operators():
    """
    Get list of all operators configured for timing instrumentation.

    Returns:
        List of (file_path, stage_name) tuples
    """
    return list(OPERATOR_TIMING_CONFIG.items())
