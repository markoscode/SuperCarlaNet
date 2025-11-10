"""
Two-Tier Timing Infrastructure for Pylot AV Pipeline

Tier 2: Operator Response Time - Input received → Output sent (per-operator)
Tier 3: End-to-End Latency - Sensor capture → Actuator command (safety-critical)

Configuration-driven approach: All instrumented operators are defined in
timing_config.py. See OPERATOR_TIMING_CONFIG for complete list.

Usage:
    # Tier 2: Wrap operator callbacks
    from pylot.utils.scn_timing import track_operator_time

    @track_operator_time('detection')
    def on_msg_camera_stream(self, msg, output_stream):
        ...

    # Tier 3: Mark pipeline entry/exit
    from pylot.utils.scn_timing import mark_pipeline_stage, compute_e2e_latency

    mark_pipeline_stage('sensor_input', timestamp)
    mark_pipeline_stage('actuator_output', timestamp)
    compute_e2e_latency('sensor_input', 'actuator_output', timestamp, logger)
"""

import time
import threading
from typing import Optional
import erdos


class TimingTracker:
    """Thread-safe timing tracker for operator and pipeline metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._operator_start_times = {}  # (stage, timestamp) -> start_time
        self._pipeline_markers = {}      # timestamp -> {stage: wall_time}

    def start_operator(self, stage: str, timestamp: erdos.Timestamp):
        """Mark operator callback start."""
        key = (stage, str(timestamp))
        with self._lock:
            self._operator_start_times[key] = time.time()

    def end_operator(self, stage: str, timestamp: erdos.Timestamp, logger) -> float:
        """Mark operator callback end and return duration."""
        key = (stage, str(timestamp))
        with self._lock:
            start = self._operator_start_times.pop(key, None)
            if start is None:
                return 0.0
            duration_ms = (time.time() - start) * 1000
            logger.info(f'TIMING tier=2 stage={stage} ts={timestamp} response_ms={duration_ms:.2f}')
            return duration_ms

    def mark_pipeline(self, stage: str, timestamp: erdos.Timestamp):
        """Mark timestamp reaching a pipeline stage."""
        with self._lock:
            ts_key = str(timestamp)
            if ts_key not in self._pipeline_markers:
                self._pipeline_markers[ts_key] = {}
            self._pipeline_markers[ts_key][stage] = time.time()

    def compute_e2e(self, start_stage: str, end_stage: str,
                    timestamp: erdos.Timestamp, logger) -> Optional[float]:
        """Compute end-to-end time between pipeline stages."""
        with self._lock:
            ts_key = str(timestamp)
            markers = self._pipeline_markers.get(ts_key, {})

            if start_stage in markers and end_stage in markers:
                e2e_ms = (markers[end_stage] - markers[start_stage]) * 1000
                logger.info(
                    f'TIMING tier=3 ts={timestamp} '
                    f'start={start_stage} end={end_stage} e2e_ms={e2e_ms:.2f}'
                )
                # Cleanup old markers to prevent memory leak
                if len(self._pipeline_markers) > 1000:
                    oldest_keys = sorted(self._pipeline_markers.keys())[:100]
                    for key in oldest_keys:
                        del self._pipeline_markers[key]
                return e2e_ms
        return None


_global_tracker = TimingTracker()


def get_tracker() -> TimingTracker:
    """Get global timing tracker instance."""
    return _global_tracker


def track_operator_time(stage: str):
    """Decorator to track Tier 2 operator response time."""
    def decorator(func):
        def wrapper(self, msg, *args, **kwargs):
            tracker = get_tracker()
            tracker.start_operator(stage, msg.timestamp)
            try:
                result = func(self, msg, *args, **kwargs)
                return result
            finally:
                tracker.end_operator(stage, msg.timestamp, self._logger)
        return wrapper
    return decorator


def mark_pipeline_stage(stage: str, timestamp: erdos.Timestamp):
    """Mark Tier 3 pipeline stage for end-to-end tracking."""
    get_tracker().mark_pipeline(stage, timestamp)


def compute_e2e_latency(start_stage: str, end_stage: str,
                        timestamp: erdos.Timestamp, logger) -> Optional[float]:
    """Compute and log Tier 3 end-to-end latency."""
    return get_tracker().compute_e2e(start_stage, end_stage, timestamp, logger)
