#!/usr/bin/env python3
"""
Generate cumulative CDF plot showing all Tier 2 pipeline stages on one graph.

Usage:
    python3 scripts/plot_cumulative_cdf.py pylot.log --output timing_results/
    python3 scripts/plot_cumulative_cdf.py pylot.log --output timing_results/ --skip-warmup 5
"""

import argparse
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path


def parse_timing_logs(log_file):
    """Parse Tier 2 TIMING logs from pylot log file.

    Returns:
        dict: {stage_name: [list of timing values in ms]}
    """
    # Tier 2: TIMING tier=2 stage=detection ts=Timestamp(...) response_ms=45.23
    tier2_pattern = re.compile(
        r'TIMING tier=2 stage=(\w+) ts=\S+ response_ms=([\d.]+)'
    )

    timings = defaultdict(list)

    with open(log_file, 'r') as f:
        for line in f:
            match = tier2_pattern.search(line)
            if match:
                stage = match.group(1)
                response_ms = float(match.group(2))
                timings[stage].append(response_ms)

    return dict(timings)


def plot_cumulative_cdf(timings, output_file, skip_warmup=1):
    """Generate cumulative CDF plot with all stages on one graph."""

    # Define colorblind-friendly colors for each stage type
    color_map = {
        # Detection stages
        'detection': '#1E88E5',              # Blue
        'efficient_detection': '#1565C0',    # Dark Blue
        'lane_detection': '#FFC107',         # Amber
        'traffic_light_detection': '#D81B60',  # Pink/Magenta

        # Perception stages
        'segmentation': '#FF6F00',           # Orange
        'tracking': '#43A047',               # Green

        # Localization
        'localization': '#7B1FA2',           # Purple

        # Prediction stages
        'prediction': '#E53935',             # Red
        'r2p2_prediction': '#C62828',        # Dark Red

        # Planning stages
        'planning': '#004D40',               # Dark Teal
        'behavior_planning': '#00695C',      # Teal

        # Control stages
        'control': '#6A1B9A',                # Purple
        'mpc_control': '#4A148C',            # Dark Purple
    }

    # Define prettier display names
    display_names = {
        'detection': 'Object Detection',
        'efficient_detection': 'Object Detection (EfficientDet)',
        'lane_detection': 'Lane Detection (LaneNet)',
        'traffic_light_detection': 'Traffic Light Detection',
        'segmentation': 'Semantic Segmentation',
        'tracking': 'Object Tracking',
        'localization': 'Localization (EKF)',
        'prediction': 'Trajectory Prediction (Linear)',
        'r2p2_prediction': 'Trajectory Prediction (R2P2)',
        'planning': 'Trajectory Planning',
        'behavior_planning': 'Behavior Planning',
        'control': 'Vehicle Control (PID)',
        'mpc_control': 'Vehicle Control (MPC)',
    }

    # Skip warmup samples
    if skip_warmup > 0:
        for stage in timings:
            timings[stage] = timings[stage][skip_warmup:]

    # Sort stages by mean runtime (descending) for legend ordering
    stage_means = {stage: np.mean(values) for stage, values in timings.items()}
    sorted_stages = sorted(stage_means.keys(), key=lambda x: stage_means[x], reverse=True)

    # Create figure
    plt.figure(figsize=(14, 8))

    # Plot CDF for each stage
    for stage in sorted_stages:
        values = np.array(timings[stage])
        values_sorted = np.sort(values)
        cdf = np.arange(1, len(values_sorted) + 1) / len(values_sorted)

        mean_val = stage_means[stage]
        label = f'{display_names.get(stage, stage)} ({mean_val:.1f} ms mean)'
        color = color_map.get(stage, '#000000')

        plt.plot(values_sorted, cdf, linewidth=2.5, label=label, color=color, alpha=0.85)

    # Formatting
    plt.xlabel('Runtime (ms)', fontsize=14, fontweight='bold')
    plt.ylabel('CDF', fontsize=14, fontweight='bold')
    plt.title('Cumulative Distribution of Tier 2 Operator Response Times',
              fontsize=16, fontweight='bold', pad=20)
    plt.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
    plt.legend(loc='lower right', fontsize=10, framealpha=0.95, ncol=2)

    # Set x-axis to log scale for better visibility
    plt.xscale('log')

    # Add horizontal grid lines at key percentiles
    plt.axhline(y=0.5, color='gray', linestyle=':', alpha=0.5, linewidth=1)
    plt.axhline(y=0.95, color='red', linestyle=':', alpha=0.7, linewidth=1.5)
    plt.axhline(y=0.99, color='darkred', linestyle=':', alpha=0.7, linewidth=1.5)

    # Add text labels for percentile lines
    ax = plt.gca()
    xlim = ax.get_xlim()
    ax.text(xlim[0] * 1.1, 0.5, 'P50', fontsize=9, color='gray', va='bottom')
    ax.text(xlim[0] * 1.1, 0.95, 'P95', fontsize=9, color='red', va='bottom')
    ax.text(xlim[0] * 1.1, 0.99, 'P99', fontsize=9, color='darkred', va='bottom')

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved cumulative CDF: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate cumulative CDF plot for all Tier 2 pipeline stages')
    parser.add_argument('log_file', help='Path to pylot log file')
    parser.add_argument('--output', default='timing_results',
                        help='Output directory for results')
    parser.add_argument('--skip-warmup', type=int, default=1,
                        help='Skip first N samples per stage to exclude warmup (default: 1)')
    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Parsing Tier 2 timing logs from: {args.log_file}")
    timings = parse_timing_logs(args.log_file)

    if not timings:
        print("ERROR: No Tier 2 timing data found in log file!")
        print("Make sure you ran Pylot with timing instrumentation enabled.")
        return

    print(f"\nFound {len(timings)} pipeline stages")
    if args.skip_warmup > 0:
        print(f"Skipping first {args.skip_warmup} sample(s) per stage\n")

    # Generate cumulative CDF plot
    output_file = output_dir / 'tier2_cdf_cumulative_all_stages.png'
    plot_cumulative_cdf(timings, output_file, skip_warmup=args.skip_warmup)

    print("\nDone!")


if __name__ == '__main__':
    main()
