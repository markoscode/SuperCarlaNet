"""
gRPC-based WS-Mask2Former detection operator.

This operator calls out to an external gRPC service running the Mask2Former model,
avoiding dependency conflicts between PyTorch/Detectron2 and TensorFlow.

The operator has the same ERDOS interface as WSMaskFormerDetectionOperator but
uses IPC instead of in-process inference.
"""

import time
from typing import Optional

import erdos
import grpc
import numpy as np

from pylot.perception.detection.obstacle import Obstacle
from pylot.perception.detection.utils import BoundingBox2D, OBSTACLE_LABELS
from pylot.perception.messages import ObstaclesMessage
from pylot.utils.scn_timing import track_operator_time

# Import generated gRPC stubs
from pylot.perception.detection.wsobjdet_grpc import (
    detection_pb2,
    detection_pb2_grpc,
)


class WSMaskFormerGRPCOperator(erdos.Operator):
    """
    Runs object detection via gRPC call to external WS-Mask2Former service.

    This avoids the NumPy version conflict between TensorFlow (needs <1.20)
    and PyTorch/Detectron2 (needs >=1.21) by running the model in a separate
    container accessible via gRPC.
    """

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

        # gRPC connection
        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[detection_pb2_grpc.DetectionServiceStub] = None
        self._connected = False

        # Timing stats
        self._total_rpc_calls = 0
        self._total_rpc_time_ms = 0.0
        self._total_inference_time_ms = 0.0

        self._connect_to_server()

    @staticmethod
    def connect(camera_stream: erdos.ReadStream,
                time_to_decision_stream: erdos.ReadStream):
        obstacles_stream = erdos.WriteStream()
        return [obstacles_stream]

    def destroy(self):
        self._logger.warn('destroying {}'.format(self.config.name))

        # Log timing stats
        if self._total_rpc_calls > 0:
            avg_rpc = self._total_rpc_time_ms / self._total_rpc_calls
            avg_inference = self._total_inference_time_ms / self._total_rpc_calls
            avg_overhead = avg_rpc - avg_inference
            self._logger.info(
                f'gRPC stats: {self._total_rpc_calls} calls, '
                f'avg RPC={avg_rpc:.1f}ms, avg inference={avg_inference:.1f}ms, '
                f'avg overhead={avg_overhead:.1f}ms')

        # Close gRPC channel
        if self._channel is not None:
            self._channel.close()
            self._logger.info('Closed gRPC channel')

        self._obstacles_stream.send(
            erdos.WatermarkMessage(erdos.Timestamp(is_top=True)))

    def _connect_to_server(self):
        """Establish gRPC connection to the detection server."""
        server_address = self._flags.ws_maskformer_grpc_address
        self._logger.info(f'Connecting to gRPC server at {server_address}')

        try:
            # Create channel with reasonable defaults
            options = [
                ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),  # 50MB
            ]
            self._channel = grpc.insecure_channel(server_address, options=options)
            self._stub = detection_pb2_grpc.DetectionServiceStub(self._channel)

            # Test connection with GetStatus
            status = self._stub.GetStatus(
                detection_pb2.StatusRequest(),
                timeout=10.0
            )

            if status.ready:
                self._connected = True
                self._logger.info(
                    f'Connected to detection server: '
                    f'subnet={status.active_subnet}, device={status.device}')

                # Set subnet if specified
                subnet = self._flags.ws_maskformer_subnet
                if subnet and subnet != status.active_subnet:
                    self._set_subnet(subnet)
            else:
                self._logger.error('Detection server not ready')

        except grpc.RpcError as e:
            self._logger.error(f'Failed to connect to gRPC server: {e}')
            self._connected = False

    def _set_subnet(self, subnet: str):
        """Switch the active subnet on the server."""
        try:
            response = self._stub.SetSubnet(
                detection_pb2.SetSubnetRequest(subnet=subnet),
                timeout=5.0
            )
            if response.success:
                self._logger.info(f'Switched to subnet: {response.active_subnet}')
            else:
                self._logger.error(f'Failed to switch subnet: {response.error}')
        except grpc.RpcError as e:
            self._logger.error(f'gRPC error switching subnet: {e}')

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

        if not self._connected or self._stub is None:
            self._logger.error('Not connected to detection server; dropping frame')
        else:
            try:
                obstacles = self._run_detection(msg.frame.frame)
            except grpc.RpcError as e:
                self._logger.error(f'gRPC detection failed: {e}')
            except Exception as e:
                self._logger.error(f'Detection error: {e}')

        runtime = (time.time() - start_time) * 1000
        obstacles_stream.send(
            ObstaclesMessage(msg.timestamp, obstacles, runtime))
        obstacles_stream.send(erdos.WatermarkMessage(msg.timestamp))

    def _run_detection(self, frame: np.ndarray) -> list:
        """
        Send frame to gRPC server and parse response into Obstacle objects.

        Args:
            frame: BGR image as numpy array (H, W, 3)

        Returns:
            List of Obstacle objects
        """
        height, width, channels = frame.shape

        # Serialize image to bytes
        image_bytes = frame.tobytes()

        # Build request
        request = detection_pb2.DetectRequest(
            image_data=image_bytes,
            width=width,
            height=height,
            channels=channels,
            subnet="",  # Use server's current subnet
            min_score=self._flags.obstacle_detection_min_score_threshold,
            min_area=self._flags.ws_maskformer_min_mask_area,
            all_labels=False,  # Only Pylot-relevant labels
        )

        # Time the RPC call
        rpc_start = time.perf_counter()
        response = self._stub.Detect(request, timeout=5.0)
        rpc_time_ms = (time.perf_counter() - rpc_start) * 1000

        # Update stats
        self._total_rpc_calls += 1
        self._total_rpc_time_ms += rpc_time_ms
        self._total_inference_time_ms += response.inference_time_ms

        if not response.success:
            self._logger.error(f'Detection failed: {response.error}')
            return []

        # Log timing periodically
        if self._total_rpc_calls % 100 == 0:
            overhead = rpc_time_ms - response.inference_time_ms
            self._logger.debug(
                f'Detection: inference={response.inference_time_ms:.1f}ms, '
                f'RPC={rpc_time_ms:.1f}ms, overhead={overhead:.1f}ms, '
                f'detections={len(response.detections)}')

        # Convert gRPC detections to Obstacle objects
        obstacles = []
        for det in response.detections:
            # Validate label
            if det.label not in OBSTACLE_LABELS:
                continue

            # Create bounding box
            # Note: BoundingBox2D expects (x_min, x_max, y_min, y_max)
            bbox2d = BoundingBox2D(
                det.x_min, det.x_max,
                det.y_min, det.y_max
            )

            obstacles.append(
                Obstacle(
                    bbox2d,
                    det.score,
                    det.label,
                    id=self._unique_id
                )
            )
            self._unique_id += 1

        return obstacles
