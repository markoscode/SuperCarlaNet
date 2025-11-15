#!/usr/bin/env python3
"""
Timeline visualization showing parallel operators and synchronization.

Shows operators executing in parallel (detection, lane, traffic light) and
synchronization points where downstream operators wait for all inputs.
"""

import re
import sys
from collections import defaultdict
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
import numpy as np

# Color scheme for different pipeline stages
STAGE_COLORS = {
    'detection': '#e74c3c',           # Red - bottleneck
    'lane_detection': '#3498db',       # Blue
    'traffic_light_detection': '#f39c12',  # Orange
    'segmentation': '#9b59b6',        # Purple
    'tracking': '#1abc9c',             # Turquoise
    'localization': '#95a5a6',         # Gray
    'prediction': '#e67e22',           # Dark orange
    'planning': '#27ae60',             # Green
    'behavior_planning': '#2ecc71',    # Light green
    'control': '#34495e',              # Dark blue-gray
    'mpc_control': '#7f8c8d',          # Medium gray
}

def parse_timing_log(log_file):
    """
    Parse tier2 timing logs and extract operator execution windows.

    Returns:
        List of (timestamp, stage, start_time, duration_ms) tuples
    """
    # Regex: TIMING tier=2 stage=detection ts=[4639] response_ms=253.38
    pattern = r'(\d{4}-\d{2}-\d{2},\d{2}:\d{2}:\d{2}\.\d{3}).*?TIMING tier=2 stage=(\w+) ts=\[(\d+)\] response_ms=([\d.]+)'

    events = []
    with open(log_file, 'r') as f:
        for line in f:
            match = re.search(pattern, line)
            if match:
                log_time_str, stage, ts, response_ms = match.groups()
                # Parse log time (when operator FINISHED)
                log_time = datetime.strptime(log_time_str, '%Y-%m-%d,%H:%M:%S.%f')
                log_time_sec = log_time.timestamp()

                # Calculate start time (finish - duration)
                duration_sec = float(response_ms) / 1000.0
                start_time = log_time_sec - duration_sec

                events.append((int(ts), stage, start_time, duration_sec))

    return sorted(events, key=lambda x: (x[0], x[2]))  # Sort by timestamp, then start_time

def visualize_timeline(events, output_file='timeline.png', time_window=5.0):
    """
    Create Gantt-like timeline showing operator execution with global time axis.

    Args:
        events: List of (timestamp, stage, start_time, duration_sec)
        time_window: How many seconds of execution to show (default: 5s)
    """
    if not events:
        print("ERROR: No timing events found in log")
        return

    # Find unique stages and timestamps in the data
    stages_in_data = sorted(set(e[1] for e in events))
    timestamps = sorted(set(e[0] for e in events))

    print(f"Found {len(events)} timing events")
    print(f"Stages: {stages_in_data}")
    print(f"Timestamp range: {timestamps[0]} - {timestamps[-1]}")

    # Normalize time to start at 0
    min_time = min(e[2] for e in events)
    events_normalized = [(ts, stage, start - min_time, dur) for ts, stage, start, dur in events]

    # Filter to time window
    events_windowed = [(ts, stage, start, dur) for ts, stage, start, dur in events_normalized
                       if start < time_window]

    if not events_windowed:
        print(f"WARNING: No events in first {time_window}s, showing all data")
        events_windowed = events_normalized[:100]  # Show first 100 events
        time_window = max(e[2] + e[3] for e in events_windowed)

    print(f"Showing {len(events_windowed)} events in {time_window:.2f}s window")

    # Create figure
    fig, ax = plt.subplots(figsize=(16, len(stages_in_data) * 0.8 + 2))

    # Y-axis: one row per stage
    stage_to_row = {stage: i for i, stage in enumerate(stages_in_data)}

    # Plot each operator execution as a rectangle
    for ts, stage, start_time, duration in events_windowed:
        row = stage_to_row[stage]
        color = STAGE_COLORS.get(stage, '#95a5a6')

        # Draw rectangle: (x, y, width, height)
        rect = Rectangle((start_time, row - 0.4), duration, 0.8,
                         facecolor=color, edgecolor='black', linewidth=0.5,
                         alpha=0.8)
        ax.add_patch(rect)

    # Formatting
    ax.set_xlim(0, time_window)
    ax.set_ylim(-0.5, len(stages_in_data) - 0.5)
    ax.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Pipeline Stage', fontsize=12, fontweight='bold')
    ax.set_yticks(range(len(stages_in_data)))
    ax.set_yticklabels(stages_in_data)

    # Grid
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

    # Title
    ax.set_title(f'Operator Timeline - First {time_window:.1f}s of Execution\n'
                 f'(Parallel execution shown as overlapping bars)',
                 fontsize=14, fontweight='bold', pad=20)

    # Legend
    legend_patches = [mpatches.Patch(color=STAGE_COLORS.get(stage, '#95a5a6'),
                                     label=stage.replace('_', ' ').title())
                     for stage in stages_in_data]
    ax.legend(handles=legend_patches, loc='upper right', fontsize=9)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n[OK] Timeline saved to: {output_file}")

    # Print statistics about parallelism
    print("\n[STATS] Parallelism Analysis:")
    for ts in timestamps[:10]:  # First 10 timestamps
        ts_events = [(stage, start, dur) for t, stage, start, dur in events_normalized if t == ts]
        if len(ts_events) > 1:
            # Find overlaps
            ts_events_sorted = sorted(ts_events, key=lambda x: x[1])
            print(f"  Timestamp {ts}:")
            for stage, start, dur in ts_events_sorted:
                print(f"    {stage:25s} [{start:.3f}s - {start+dur:.3f}s] ({dur*1000:.1f}ms)")

def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_timeline.py <log_file> [output_file] [time_window_sec]")
        print("\nExample:")
        print("  python visualize_timeline.py pylot.log timeline.png 5.0")
        sys.exit(1)

    log_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'timeline.png'
    time_window = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    print(f"Parsing log: {log_file}")
    events = parse_timing_log(log_file)

    if not events:
        print("ERROR: No TIMING tier=2 entries found in log")
        print("\nExpected format:")
        print("  TIMING tier=2 stage=detection ts=[4639] response_ms=253.38")
        sys.exit(1)

    visualize_timeline(events, output_file, time_window)

if __name__ == '__main__':
    main()
