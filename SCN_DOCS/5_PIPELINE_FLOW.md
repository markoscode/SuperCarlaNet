# Pylot Pipeline Flow - Complete Reference

**File References**: All operator files, inputs/outputs, and dataflow

## Pipeline Overview

**Entry Point**: `pylot.py:23-233` - `driver()` function constructs entire dataflow
**DOT Graph**: `pylot.py:221` - `erdos.run_async('pylot.dot')` generates visualization
**Architecture**: `pylot/operator_creator.py` + `pylot/component_creator.py` - operator factories

---

## Complete Pipeline (Sensor → Actuator)

### ⓪ SIMULATOR BRIDGE
**File**: `pylot/simulation/carla_operator.py` - `CarlaOperator`
**Creator**: `pylot/operator_creator.py:13-24` - `add_simulator_bridge()`
**Purpose**: Connects Pylot to CARLA simulator
**Inputs**: `control_stream`, `sensor_ready_stream`, `pipeline_finish_notify_stream`
**Outputs**:
- `pose_stream` - Vehicle position/orientation
- `ground_traffic_lights_stream` - Ground truth traffic lights
- `ground_obstacles_stream` - Ground truth obstacles
- `vehicle_id_stream` - Simulator vehicle ID
- `open_drive_stream` - HD map data

---

### ① SENSOR LAYER

#### Camera Driver
**File**: `pylot/drivers/carla_camera_driver_operator.py` - `CarlaCameraDriverOperator`
**Creator**: `pylot/operator_creator.py:415-443` - `add_camera_driver()`
**Main Entry**: `pylot.py:55-61` - RGB center camera setup
**Inputs**: `vehicle_id_stream`, `release_sensor_stream`
**Outputs**: `center_camera_stream` - RGB frames (FrameMessage)
**Frequency**: 30 Hz default
**Instrumentation**: `carla_camera_driver_operator.py:82` - marks `sensor_input` (Tier 3 entry)

#### LiDAR Driver
**File**: `pylot/drivers/lidar_driver_operator.py` - `LidarDriverOperator`
**Creator**: `pylot/operator_creator.py:445-474` - `add_lidar()`
**Main Entry**: `pylot.py:84-91`
**Inputs**: `vehicle_id_stream`, `release_sensor_stream`
**Outputs**: `point_cloud_stream` - 3D point clouds (PointCloudMessage)
**Frequency**: 10-20 Hz default

#### IMU Sensor
**File**: `pylot/drivers/imu_driver_operator.py` - `IMUDriverOperator`
**Creator**: `pylot/operator_creator.py:524-545` - `add_imu()`
**Main Entry**: `pylot.py:112-117`
**Outputs**: `imu_stream` - IMUMessage (acceleration, gyroscope)

#### GNSS/GPS Sensor
**File**: `pylot/drivers/gnss_driver_operator.py` - `GNSSDriverOperator`
**Creator**: `pylot/operator_creator.py:548-569` - `add_gnss()`
**Main Entry**: `pylot.py:119-124`
**Outputs**: `gnss_stream` - GNSSMessage (latitude, longitude, altitude)

---

### ② PERCEPTION LAYER

#### 2a. Object Detection
**File**: `pylot/perception/detection/detection_operator.py:19-150` - `DetectionOperator`
**Creator**: `pylot/operator_creator.py:48-66` - `add_obstacle_detection()`
**Component**: `pylot/component_creator.py:14-126` - `add_obstacle_detection()`
**Main Entry**: `pylot.py:130-135`
**Callback**: `detection_operator.py:93-150` - `on_msg_camera_stream()` + `@track_operator_time('detection')`
**Inputs**:
- `center_camera_stream` - RGB frames
- `time_to_decision_stream` - Dynamic deadline hints
**Outputs**: `obstacles_stream_wo_depth` - ObstaclesMessage (2D bounding boxes)
**Models**: Faster-RCNN, SSD, EfficientDet (configurable via flags)
**Config**: `--obstacle_detection_model_paths`, `--obstacle_detection_model_names`
**Detects**: Cars, pedestrians, cyclists (COCO dataset classes)
**Output Format**: `[BoundingBox2D(x_min, y_min, x_max, y_max), confidence, label, id]`

**Alternative - EfficientDet**:
**File**: `pylot/perception/detection/efficientdet_operator.py:16-157` - `EfficientDetOperator`
**Creator**: `pylot/operator_creator.py:27-45` - `add_efficientdet_obstacle_detection()`
**Callback**: `efficientdet_operator.py:81-157` - `on_watermark()` + `@track_operator_time('efficient_detection')`

#### 2b. Lane Detection
**File**: `pylot/perception/detection/lanenet_detection_operator.py:20-157` - `LaneNetDetectionOperator`
**Creator**: `pylot/operator_creator.py:261-289` - `add_lane_detection()`
**Component**: `pylot/component_creator.py:359-383` - `add_lane_detection()`
**Main Entry**: `pylot.py:144-148`
**Callback**: `lanenet_detection_operator.py:60-157` - `on_camera_frame()` + `@track_operator_time('lane_detection')`
**Inputs**: `center_camera_stream`, `pose_stream`, `open_drive_stream`
**Outputs**: `lane_detection_stream` - LaneDetectionMessage (lane polynomials/waypoints)
**Config**: `--lane_detection`
**Purpose**: Detect drivable lanes, road boundaries
**Output Format**: Lane centerline + left/right boundaries as polynomial curves

#### 2c. Traffic Light Detection
**File**: `pylot/perception/detection/traffic_light_det_operator.py:15-147` - `TrafficLightDetOperator`
**Creator**: `pylot/operator_creator.py:291-325` - `add_traffic_light_detector()`
**Component**: `pylot/component_creator.py:129-216` - `add_traffic_light_detection()`
**Main Entry**: `pylot.py:138-142`
**Callback**: `traffic_light_det_operator.py:68-147` - `on_frame()` + `@track_operator_time('traffic_light_detection')`
**Inputs**:
- `tl_camera_stream` - Narrow FOV camera (45° vs 90°)
- `time_to_decision_stream`
**Outputs**: `traffic_lights_stream_wo_depth` - ObstaclesMessage (traffic lights)
**Config**: `--traffic_light_detection`
**Why Separate Camera**: Higher resolution for distant/small traffic lights
**Output Format**: `[BoundingBox2D, confidence, state (Red/Yellow/Green)]`

#### 2d. Obstacle Location Finder
**File**: `pylot/perception/detection/obstacle_location_finder_operator.py:15-184` - `ObstacleLocationFinderOperator`
**Creator**: `pylot/operator_creator.py:69-101` - `add_obstacle_location_finder()`
**Called By**: `component_creator.py:86-89` (detection), `component_creator.py:180-183` (traffic lights)
**Callback**: `obstacle_location_finder_operator.py:66-184` - `on_watermark()`
**Inputs**:
- `obstacles_stream_wo_depth` - 2D bounding boxes
- `depth_stream` - LiDAR point cloud or depth camera
- `pose_stream` - Vehicle pose
- `camera_setup` - Camera intrinsics
**Outputs**: `obstacles_stream` - ObstaclesMessage (with 3D world coordinates)
**Purpose**: Convert 2D image boxes → 3D world locations
**Process**:
1. Project 2D box into 3D frustum using camera intrinsics
2. Find LiDAR points inside frustum
3. Cluster points to find object centroid
4. Transform to world coordinates using vehicle pose
**Output Format**: `[Location(x_world, y_world, z_world), velocity, label]`

#### 2e. Segmentation
**File**: `pylot/perception/segmentation/segmentation_drn_operator.py:22-144` - `SegmentationDRNOperator`
**Creator**: `pylot/operator_creator.py:327-353` - `add_segmentation()`
**Component**: `pylot/component_creator.py:385-413` - `add_segmentation()`
**Main Entry**: `pylot.py:155-156`
**Callback**: `segmentation_drn_operator.py:71-144` - `on_msg_camera_stream()` + `@track_operator_time('segmentation')`
**Inputs**: `center_camera_stream`
**Outputs**: `segmented_stream` - SegmentedFrameMessage (per-pixel labels)
**Config**: `--segmentation`, `--perfect_segmentation`
**Model**: DRN (Dilated Residual Networks)
**Purpose**: Pixel-level classification (road, sidewalk, vehicle, pedestrian, etc.)
**Output Format**: `[H x W] array with class labels per pixel`

---

### ③ TRACKING LAYER

**File**: `pylot/perception/tracking/object_tracker_operator.py:22-270` - `ObjectTrackerOperator`
**Creator**: `pylot/operator_creator.py:176-218` - `add_obstacle_tracking()`
**Component**: `pylot/component_creator.py:415-474` - `add_obstacle_tracking()`
**Main Entry**: `pylot.py:150-153`
**Callback**: `object_tracker_operator.py:94-270` - `on_watermark()` + `@track_operator_time('tracking')`
**Inputs**:
- `camera_stream` - RGB frames
- `obstacles_stream` - Detected obstacles with 3D locations
- `depth_stream` - LiDAR/depth data
- `pose_stream` - Vehicle pose
- `ground_obstacles_stream` - Ground truth (for evaluation)
**Outputs**: `obstacles_tracking_stream` - ObstacleTrajectoriesMessage
**Algorithms**: SORT, DeepSORT, DaSiamRPN (configurable)
**Config**: `--tracking_num_steps=10` (history length)
**Purpose**:
- Assign persistent IDs to obstacles across frames
- Track motion history (past 10 frames default)
- Filter false positives
- Enable trajectory prediction
**Output Format**: `[ObstacleTrajectory(id, past_locations, velocities)]`

---

### ④ LOCALIZATION LAYER

**File**: `pylot/localization/localization_operator.py:14-287` - `LocalizationOperator`
**Creator**: `pylot/operator_creator.py:571-594` - `add_localization()`
**Main Entry**: `pylot.py:126-128`
**Callback**: `localization_operator.py:79-287` - `on_watermark()` + `@track_operator_time('localization')`
**Inputs**:
- `imu_stream` - IMU measurements
- `gnss_stream` - GPS coordinates
- `pose_stream` - Simulator pose (for initialization)
**Outputs**: `localized_pose_stream` - Refined pose
**Algorithm**: Extended Kalman Filter (EKF)
**Config**: `--localization`
**Purpose**: Fuse noisy IMU + GPS to get accurate vehicle position
**Process**:
1. Prediction step: Use IMU to predict position change
2. Update step: Correct prediction with GPS measurement
3. Output smoothed, accurate pose
**Output Format**: `Transform(Location(x, y, z), Rotation(pitch, yaw, roll)), velocity`

---

### ⑤ PREDICTION LAYER

#### Linear Predictor
**File**: `pylot/prediction/linear_predictor_operator.py:14-173` - `LinearPredictorOperator`
**Creator**: `pylot/operator_creator.py:680-707` - `add_linear_prediction()`
**Callback**: `linear_predictor_operator.py:53-173` - `generate_predicted_trajectories()` + `@track_operator_time('prediction')`
**Inputs**:
- `tracking_stream` - Obstacle trajectories with history
- `pose_stream` - Vehicle pose (for relative coordinates)
**Outputs**: `prediction_stream` - PredictionMessage
**Algorithm**: Constant velocity model (linear extrapolation)
**Config**: `--prediction_type=linear`, `--prediction_num_future_steps=10` (5s horizon @ 0.5s steps)
**Output Format**: `[ObstaclePrediction(id, probability, future_trajectory_waypoints)]`

#### R2P2 Predictor
**File**: `pylot/prediction/r2p2_predictor_operator.py:21-191` - `R2P2PredictorOperator`
**Creator**: `pylot/operator_creator.py:709-749` - `add_r2p2_prediction()`
**Callback**: `r2p2_predictor_operator.py:99-191` - `on_watermark()` + `@track_operator_time('r2p2_prediction')`
**Inputs**:
- `obstacles_tracking_stream`
- `camera_stream` - For scene context
- `lidar_stream` - For 3D scene understanding
**Outputs**: `prediction_stream` - PredictionMessage
**Algorithm**: R2P2 neural network (scene-aware predictions)
**Config**: `--prediction_type=r2p2`
**Purpose**: Multi-modal predictions considering scene context (intersections, lanes)

**Component Entry**: `pylot/component_creator.py:476-535` - `add_prediction()`
**Main Entry**: `pylot.py:163-171`

---

### ⑥ PLANNING LAYER

#### Behavior Planning
**File**: `pylot/planning/behavior_planning_operator.py:17-279` - `BehaviorPlanningOperator`
**Callback**: `behavior_planning_operator.py:69-279` - `on_watermark()` + `@track_operator_time('behavior_planning')`
**Inputs**:
- `pose_stream`
- `open_drive_stream` - HD map
- `route_stream` - High-level route
**Outputs**: `behavior_stream` - High-level decisions
**Algorithm**: Finite State Machine (FSM)
**States**: `FOLLOW_LANE`, `STOP`, `OVERTAKE`, `CHANGE_LANE`, `INTERSECTION_PASS`
**Purpose**: Make tactical driving decisions based on traffic rules
**Output**: Behavior enum + recommended speed

#### Trajectory Planning
**File**: `pylot/planning/planning_operator.py:20-396` - `PlanningOperator`
**Creator**: `pylot/operator_creator.py:596-651` - `add_planning()`
**Component**: `pylot/component_creator.py:537-596` - `add_planning()`
**Main Entry**: `pylot.py:176-179`
**Callback**: `planning_operator.py:123-396` - `on_watermark()` + `@track_operator_time('planning')`
**Inputs**:
- `pose_stream` - Current position
- `prediction_stream` - Predicted obstacle trajectories
- `static_obstacles_stream` - Traffic lights
- `lanes_stream` - Lane boundaries
- `route_stream` - Global route waypoints
- `open_drive_stream` - HD map
- `time_to_decision_stream` - Dynamic deadline
**Outputs**: `waypoints_stream` - WaypointsMessage
**Algorithms** (selectable via `--planning_type`):
- `waypoint` - Simple waypoint follower (default)
- `frenet_optimal_trajectory` - Frenet frame trajectory optimization
- `rrt_star` - RRT* sampling-based planner
- `hybrid_astar` - Hybrid A* planner
**Purpose**: Generate collision-free, comfortable trajectory
**Optimization Criteria**:
- Safety: Avoid predicted collision paths
- Comfort: Minimize jerk (3rd derivative of position)
- Legality: Stay in lanes, respect traffic lights
- Efficiency: Reach goal quickly
**Output Format**: `Waypoints[Location(x, y), target_speed] (every 0.5m along path)`

**Planner Implementations**:
- Frenet: `pylot/planning/frenet_optimal_trajectory/fot_planner.py:27-411`
- RRT*: `pylot/planning/rrt_star/rrt_star_planner.py:17-281`
- Hybrid A*: `pylot/planning/hybrid_astar/hybrid_astar_planner.py:25-388`

---

### ⑦ CONTROL LAYER

#### PID Control
**File**: `pylot/control/pid_control_operator.py:13-137` - `PIDControlOperator`
**Creator**: `pylot/operator_creator.py:653-678` - `add_pid_control()`
**Component**: `pylot/component_creator.py:598-650` - `add_control()`
**Main Entry**: `pylot.py:197-200`
**Callback**: `pid_control_operator.py:64-137` - `on_watermark()` + `@track_operator_time('control')`
**Inputs**:
- `pose_stream` - Current vehicle state
- `waypoints_stream` - Target waypoints from planner
**Outputs**: `control_stream` - ControlMessage
**Algorithm**: PID (Proportional-Integral-Derivative) controller
**Config**: `--control=pid`, `--pid_p`, `--pid_i`, `--pid_d` (tuning parameters)
**Control Law**:
```
throttle/brake = K_p * speed_error + K_i * ∫speed_error + K_d * d(speed_error)/dt
steer = K_steer * angle_to_next_waypoint
```
**Purpose**: Convert waypoints → low-level actuator commands
**Output Format**: `ControlMessage(throttle, brake, steer)` - values in [0, 1] or [-1, 1]
**Frequency**: 100 Hz default
**Instrumentation**: `pid_control_operator.py:94` - marks `actuator_output` (Tier 3 exit)

#### MPC Control
**File**: `pylot/control/mpc/mpc_operator.py:15-184` - `MPCControlOperator`
**Creator**: `pylot/operator_creator.py:653-678` (same as PID)
**Callback**: `mpc_operator.py:65-184` - `on_watermark()` + `@track_operator_time('mpc_control')`
**Algorithm**: Model Predictive Control (optimization-based)
**Config**: `--control=mpc`
**Advantage**: Better for sharp turns, considers future trajectory
**Process**:
1. Predict vehicle motion over horizon (1-2 seconds)
2. Optimize control sequence to minimize deviation from waypoints
3. Execute first control in sequence
4. Repeat at next timestep

---

## Synchronization via Watermarks

**Key Concept**: Operators with multiple inputs use **watermarks** for synchronization

**Example - Planning Operator** (`planning_operator.py:58-61`):
```python
erdos.add_watermark_callback([
    pose_stream, prediction_stream, static_obstacles_stream,
    lanes_stream, time_to_decision_stream, route_stream
], [waypoints_stream], self.on_watermark)
```

**Behavior**: `on_watermark()` only fires when **all 6 input streams** have received watermark for same timestamp
**Purpose**: Ensures synchronized, consistent world state for planning decision

---

## Parallel vs Sequential Execution

### Parallel (same timestamp, concurrent execution):
- **Detection**: `DetectionOperator` (object) | `LaneNetDetectionOperator` (lanes) | `TrafficLightDetector` (TL)
- **All receive**: `center_camera_stream` with same `timestamp=T`
- **All execute**: Simultaneously on separate threads/GPUs
- **All output**: Independent streams, no dependencies

### Sequential (watermark-driven pipeline):
```
Camera(T) → Detection(T) → LocationFinder(T) → Tracking(T) →
Prediction(T) → Planning(T) → Control(T)
```
Each waits for watermark from previous stage

---

## Config File Control

**Detection Only** (`configs/detection.conf`):
```
--obstacle_detection
--obstacle_detection_model_paths=dependencies/models/obstacle_detection/faster-rcnn/
--control=simulator_auto_pilot
```

**Full E2E Pipeline** (`configs/e2e.conf`):
```
--obstacle_detection          # Enable detection
--traffic_light_detection     # Enable TL detection
--lane_detection              # Enable lane detection
--prediction                  # Enable prediction
--planning_type=waypoint      # Choose planner
--control=pid                 # Choose controller
```

**Perfect Modes** (use ground truth, skip ML models):
```
--perfect_obstacle_detection  # Skip detection, use simulator truth
--perfect_segmentation        # Skip segmentation model
--perfect_obstacle_tracking   # Skip tracker
```

---

## Timing Instrumentation Locations

**Tier 2 (Operator Response Time)** - All decorated with `@track_operator_time(stage)`:
1. `detection_operator.py:94` - detection
2. `lanenet_detection_operator.py:60` - lane_detection
3. `traffic_light_det_operator.py:68` - traffic_light_detection
4. `efficientdet_operator.py:81` - efficient_detection
5. `segmentation_drn_operator.py:71` - segmentation
6. `object_tracker_operator.py:94` - tracking
7. `localization_operator.py:79` - localization
8. `linear_predictor_operator.py:53` - prediction
9. `r2p2_predictor_operator.py:99` - r2p2_prediction
10. `planning_operator.py:123` - planning
11. `behavior_planning_operator.py:69` - behavior_planning
12. `pid_control_operator.py:65` - control
13. `mpc_operator.py:65` - mpc_control

**Tier 3 (End-to-End Latency)**:
- **Entry**: `carla_camera_driver_operator.py:82` - `mark_pipeline_stage('sensor_input', timestamp)`
- **Exit**: `pid_control_operator.py:94` - `mark_pipeline_stage('actuator_output', timestamp)` + `compute_e2e_latency()`

---

## Message Types

**FrameMessage**: `pylot/perception/messages.py` - RGB/depth camera frames
**ObstaclesMessage**: `pylot/perception/messages.py` - Detected obstacles (2D or 3D)
**ObstacleTrajectoriesMessage**: `pylot/perception/messages.py` - Tracked trajectories
**PredictionMessage**: `pylot/prediction/messages.py` - Predicted future paths
**WaypointsMessage**: `pylot/planning/messages.py` - Planned trajectory
**ControlMessage**: `pylot/control/messages.py` - Actuator commands
**PointCloudMessage**: `pylot/perception/messages.py` - LiDAR point cloud

---

## Key Files Summary

| Layer | File | Operator | Stage Name |
|-------|------|----------|------------|
| **Sensor** | `drivers/carla_camera_driver_operator.py` | CarlaCameraDriverOperator | - |
| **Sensor** | `drivers/lidar_driver_operator.py` | LidarDriverOperator | - |
| **Detection** | `perception/detection/detection_operator.py` | DetectionOperator | detection |
| **Detection** | `perception/detection/lanenet_detection_operator.py` | LaneNetDetectionOperator | lane_detection |
| **Detection** | `perception/detection/traffic_light_det_operator.py` | TrafficLightDetOperator | traffic_light_detection |
| **Detection** | `perception/detection/efficientdet_operator.py` | EfficientDetOperator | efficient_detection |
| **Location** | `perception/detection/obstacle_location_finder_operator.py` | ObstacleLocationFinderOperator | - |
| **Segmentation** | `perception/segmentation/segmentation_drn_operator.py` | SegmentationDRNOperator | segmentation |
| **Tracking** | `perception/tracking/object_tracker_operator.py` | ObjectTrackerOperator | tracking |
| **Localization** | `localization/localization_operator.py` | LocalizationOperator | localization |
| **Prediction** | `prediction/linear_predictor_operator.py` | LinearPredictorOperator | prediction |
| **Prediction** | `prediction/r2p2_predictor_operator.py` | R2P2PredictorOperator | r2p2_prediction |
| **Planning** | `planning/behavior_planning_operator.py` | BehaviorPlanningOperator | behavior_planning |
| **Planning** | `planning/planning_operator.py` | PlanningOperator | planning |
| **Control** | `control/pid_control_operator.py` | PIDControlOperator | control |
| **Control** | `control/mpc/mpc_operator.py` | MPCControlOperator | mpc_control |

**Factory Files**:
- `pylot.py` - Main driver, constructs entire pipeline
- `operator_creator.py` - Low-level operator factories
- `component_creator.py` - High-level component builders

---

**Version**: 1.0
**Date**: 2025-11-10
