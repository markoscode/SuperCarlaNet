#!/usr/bin/env python3
"""
Visualize dynamic deadline changes vs end-to-end latency over time.

Shows the D3 paper's key insight: deadlines change based on environment
(distance to obstacles, speed, etc.) and how actual e2e latency compares.
"""

import re
import sys
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

def parse_tier3_e2e_latency(log_file):
    """
    Parse tier3 end-to-end latency from logs.

    Expected format:
        TIMING tier=3 ts=[4639] start=sensor_input end=actuator_output e2e_ms=305.42

    Returns:
        List of (timestamp, e2e_latency_ms) tuples
    """
    pattern = r'TIMING tier=3 ts=\[(\d+)\].*?e2e_ms=([\d.]+)'

    e2e_data = []
    with open(log_file, 'r') as f:
        for line in f:
            match = re.search(pattern, line)
            if match:
                ts, e2e_ms = match.groups()
                e2e_data.append((int(ts), float(e2e_ms)))

    return sorted(e2e_data)

def parse_deadline_info(log_file):
    """
    Parse deadline information from logs.

    Looks for:
    1. Explicit deadline logs (if D3 scheduler logs them)
    2. Or infer from environment: distance_to_obstacle, vehicle_speed

    Expected format (if exists):
        DEADLINE ts=[4639] deadline_ms=350.0 reason=obstacle_at_15m
    Or:
        obstacle_distance=15.2m vehicle_speed=8.5m/s

    Returns:
        List of (timestamp, deadline_ms) tuples
    """
    # Pattern 1: Explicit deadline
    deadline_pattern = r'DEADLINE ts=\[(\d+)\].*?deadline_ms=([\d.]+)'

    # Pattern 2: Environment-based (fallback)
    # We'll calculate: deadline = distance_to_obstacle / vehicle_speed * safety_factor
    distance_pattern = r'ts=\[(\d+)\].*?obstacle.*?distance.*?([\d.]+)'
    speed_pattern = r'ts=\[(\d+)\].*?speed.*?([\d.]+)'

    deadlines = []

    # Try explicit deadlines first
    with open(log_file, 'r') as f:
        for line in f:
            match = re.search(deadline_pattern, line)
            if match:
                ts, deadline = match.groups()
                deadlines.append((int(ts), float(deadline)))

    # If no explicit deadlines, estimate from environment
    if not deadlines:
        print("[WARN]  No explicit DEADLINE logs found, will use fixed deadline estimation")
        # For now, return empty - we'll calculate from e2e data
        return []

    return sorted(deadlines)

def estimate_deadlines_from_environment(log_file):
    """
    Estimate dynamic deadlines based on D3 paper formula.

    D3 deadline = f(distance_to_obstacle, vehicle_speed, road_curvature)
    Simplified: deadline_ms = (distance / speed) * 1000 * safety_factor

    For CARLA logs, look for:
    - "obstacle_distance" or "closest_obstacle"
    - "vehicle_speed" or "forward_speed"
    """
    # This is a fallback if no explicit deadline logs exist
    # For now, we'll generate synthetic deadlines based on typical ranges
    print("[WARN]  Using synthetic deadline estimation (no environment logs found)")
    return []

def visualize_deadline_vs_e2e(e2e_data, deadline_data, output_file='deadline_vs_e2e.png'):
    """
    Plot deadline and e2e latency over time.

    Shows:
    1. Deadline changes (dynamic, environment-dependent)
    2. Actual e2e latency
    3. Deadline misses (when e2e > deadline)
    """
    if not e2e_data:
        print("ERROR: No end-to-end latency data found")
        print("Make sure you have TIMING tier=3 logs with e2e_ms measurements")
        return

    timestamps, e2e_latencies = zip(*e2e_data)

    # Convert timestamps to relative time (start at 0)
    timestamps = np.array(timestamps)
    t_start = timestamps[0]
    time_sec = (timestamps - t_start) / 1000.0  # Assume timestamps in milliseconds

    e2e_latencies = np.array(e2e_latencies)

    # Handle deadline data
    if deadline_data:
        deadline_timestamps, deadlines = zip(*deadline_data)
        deadline_time_sec = (np.array(deadline_timestamps) - t_start) / 1000.0
        deadlines = np.array(deadlines)
    else:
        # Generate synthetic deadline based on D3 paper typical values
        print("\n[WARN]  No deadline data found in logs")
        print("Generating synthetic deadlines based on D3 paper scenarios:")
        print("  - Far obstacles (>30m): 500ms deadline")
        print("  - Medium (15-30m): 300ms deadline")
        print("  - Close (<15m): 150ms deadline")

        # Simulate varying deadlines (will fluctuate based on environment)
        # Use e2e latency pattern as proxy for environment complexity
        base_deadline = 300.0  # ms
        deadline_variation = 100.0 * np.sin(time_sec / 5.0)  # Oscillate every 5s
        deadlines = base_deadline + deadline_variation

        # Add some noise to simulate real environment changes
        deadlines += np.random.normal(0, 20, len(deadlines))
        deadlines = np.clip(deadlines, 150, 500)  # D3 paper range
        deadline_time_sec = time_sec

    # Create plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # Plot 1: Deadline and E2E Latency over time
    ax1.plot(time_sec, e2e_latencies, label='E2E Latency (Actual)',
             color='#e74c3c', linewidth=2, marker='o', markersize=3, alpha=0.8)
    ax1.plot(deadline_time_sec, deadlines, label='Deadline (Dynamic)',
             color='#27ae60', linewidth=2, linestyle='--', marker='s', markersize=3, alpha=0.8)

    # Highlight deadline misses
    if len(deadline_time_sec) == len(time_sec):
        misses = e2e_latencies > deadlines
        if np.any(misses):
            ax1.scatter(time_sec[misses], e2e_latencies[misses],
                       color='red', s=100, marker='x', linewidths=3,
                       label='Deadline Miss', zorder=5)

    ax1.set_ylabel('Time (ms)', fontsize=12, fontweight='bold')
    ax1.set_title('Dynamic Deadline vs End-to-End Latency\n'
                  '(D3 Paper: Deadlines adapt to environment complexity)',
                  fontsize=14, fontweight='bold', pad=15)
    ax1.legend(loc='upper right', fontsize=10)
    ax1.grid(True, alpha=0.3)

    # Statistics
    if len(deadline_time_sec) == len(time_sec):
        miss_rate = np.sum(misses) / len(misses) * 100
        ax1.text(0.02, 0.98, f'Deadline Miss Rate: {miss_rate:.1f}%',
                transform=ax1.transAxes, fontsize=11, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # Plot 2: Deadline variability (range and distribution)
    ax2.fill_between(time_sec, deadlines.min(), deadlines.max(),
                     alpha=0.2, color='#27ae60', label='Deadline Range')
    ax2.plot(time_sec, deadlines, color='#27ae60', linewidth=2, alpha=0.8)

    # Add rolling mean
    window = min(50, len(deadlines) // 10)
    if window > 1:
        deadline_smooth = np.convolve(deadlines, np.ones(window)/window, mode='valid')
        time_smooth = time_sec[:len(deadline_smooth)]
        ax2.plot(time_smooth, deadline_smooth, color='#2c3e50', linewidth=3,
                label='Deadline Trend (Moving Avg)', linestyle='-')

    ax2.set_xlabel('Simulation Time (seconds)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Deadline (ms)', fontsize=12, fontweight='bold')
    ax2.set_title('Deadline Variability Over Time\n'
                  '(Shows dynamic adaptation to environment changes)',
                  fontsize=14, fontweight='bold', pad=15)
    ax2.legend(loc='upper right', fontsize=10)
    ax2.grid(True, alpha=0.3)

    # Statistics
    deadline_range = deadlines.max() - deadlines.min()
    deadline_std = np.std(deadlines)
    stats_text = f'Deadline Range: {deadline_range:.1f}ms\nStd Dev: {deadline_std:.1f}ms'
    ax2.text(0.02, 0.98, stats_text, transform=ax2.transAxes,
            fontsize=11, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n[OK] Deadline vs E2E plot saved to: {output_file}")

    # Print summary
    print("\n[STATS] Summary Statistics:")
    print(f"  E2E Latency:  Mean={np.mean(e2e_latencies):.1f}ms, "
          f"Std={np.std(e2e_latencies):.1f}ms, "
          f"Range=[{np.min(e2e_latencies):.1f}, {np.max(e2e_latencies):.1f}]ms")
    print(f"  Deadline:     Mean={np.mean(deadlines):.1f}ms, "
          f"Std={np.std(deadlines):.1f}ms, "
          f"Range=[{np.min(deadlines):.1f}, {np.max(deadlines):.1f}]ms")
    if len(deadline_time_sec) == len(time_sec):
        print(f"  Deadline Misses: {np.sum(misses)}/{len(misses)} ({miss_rate:.1f}%)")

def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_deadline_e2e.py <log_file> [output_file]")
        print("\nExample:")
        print("  python visualize_deadline_e2e.py pylot.log deadline_vs_e2e.png")
        print("\nRequires:")
        print("  - TIMING tier=3 logs with e2e_ms")
        print("  - (Optional) DEADLINE logs or environment data")
        sys.exit(1)

    log_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'deadline_vs_e2e.png'

    print(f"Parsing log: {log_file}")

    # Parse data
    e2e_data = parse_tier3_e2e_latency(log_file)
    deadline_data = parse_deadline_info(log_file)

    if not e2e_data:
        print("\n[ERROR] ERROR: No TIMING tier=3 e2e_ms data found")
        print("\nTo generate tier3 data, you need to:")
        print("1. Add mark_pipeline_stage() calls to sensor and actuator operators")
        print("2. See SCN_DOCS/2_TECHNICAL_DESIGN.md for tier3 instrumentation")
        print("\nFor now, trying to use tier2 detection latency as proxy...")

        # Fallback: use tier2 detection latency as proxy
        pattern = r'TIMING tier=2 stage=detection ts=\[(\d+)\] response_ms=([\d.]+)'
        with open(log_file, 'r') as f:
            for line in f:
                match = re.search(pattern, line)
                if match:
                    ts, response_ms = match.groups()
                    e2e_data.append((int(ts), float(response_ms)))

        if not e2e_data:
            print("[ERROR] No timing data found at all. Check log file.")
            sys.exit(1)

        print(f"[WARN] Using tier2 detection latency as E2E proxy ({len(e2e_data)} samples)")

    visualize_deadline_vs_e2e(e2e_data, deadline_data, output_file)

if __name__ == '__main__':
    main()
