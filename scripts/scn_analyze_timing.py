#!/usr/bin/env python3
"""
Timing Analysis Script for Pylot Pipeline with Two-Tier System

Parses and analyzes timing logs from Pylot's two-tier timing instrumentation:
- Tier 2: Per-operator response times
- Tier 3: End-to-end pipeline latency

Generates:
1. CDF plots for each stage
2. Statistics (mean, median, p95, p99)
3. Time breakdown pie/bar charts
4. E2E latency analysis
5. System overhead analysis (Tier 3 - sum of Tier 2)

Usage:
    python3 scripts/analyze_timing.py pylot.log --output timing_results/
    python3 scripts/analyze_timing.py pylot.log --output timing_results/ --skip-warmup 5
"""

import argparse
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server environments
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path


def parse_timing_logs(log_file):
    """Parse TIMING logs from pylot log file.

    Returns:
        dict: {
            'tier2': {stage_name: [list of timing values in ms]},
            'tier3': {(start_stage, end_stage): [list of e2e times in ms]},
            'timestamps': {stage_name: [list of timestamp strings]}
        }
    """
    # Tier 2: TIMING tier=2 stage=detection ts=Timestamp(...) response_ms=45.23
    tier2_pattern = re.compile(
        r'TIMING tier=2 stage=(\w+) ts=(\S+) response_ms=([\d.]+)'
    )

    # Tier 3: TIMING tier=3 ts=Timestamp(...) start=sensor_input end=actuator_output e2e_ms=250.45
    tier3_pattern = re.compile(
        r'TIMING tier=3 ts=(\S+) start=(\w+) end=(\w+) e2e_ms=([\d.]+)'
    )

    tier2_timings = defaultdict(list)
    tier3_timings = defaultdict(list)
    timestamps = defaultdict(list)

    with open(log_file, 'r') as f:
        for line in f:
            # Parse Tier 2
            match = tier2_pattern.search(line)
            if match:
                stage = match.group(1)
                timestamp = match.group(2)
                response_ms = float(match.group(3))
                tier2_timings[stage].append(response_ms)
                timestamps[stage].append(timestamp)
                continue

            # Parse Tier 3
            match = tier3_pattern.search(line)
            if match:
                timestamp = match.group(1)
                start_stage = match.group(2)
                end_stage = match.group(3)
                e2e_ms = float(match.group(4))
                tier3_timings[(start_stage, end_stage)].append(e2e_ms)

    return {
        'tier2': dict(tier2_timings),
        'tier3': dict(tier3_timings),
        'timestamps': dict(timestamps)
    }


def compute_statistics(values):
    """Compute timing statistics."""
    values = np.array(values)
    return {
        'count': len(values),
        'mean': np.mean(values),
        'median': np.median(values),
        'std': np.std(values),
        'min': np.min(values),
        'max': np.max(values),
        'p50': np.percentile(values, 50),
        'p95': np.percentile(values, 95),
        'p99': np.percentile(values, 99),
    }


def plot_cdf(values, title, output_file):
    """Generate CDF plot for timing values."""
    values_sorted = np.sort(values)
    cdf = np.arange(1, len(values_sorted) + 1) / len(values_sorted)

    plt.figure(figsize=(10, 6))
    plt.plot(values_sorted, cdf, linewidth=2)
    plt.xlabel('Runtime (ms)', fontsize=12)
    plt.ylabel('CDF', fontsize=12)
    plt.title(title, fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    plt.close()
    print(f"  Saved CDF: {output_file}")


def generate_breakdown_plot(stage_means, output_file):
    """Generate pie chart and bar chart showing time breakdown across stages."""
    stages = list(stage_means.keys())
    times = list(stage_means.values())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Pie chart
    colors = plt.cm.Set3(range(len(stages)))
    ax1.pie(times, labels=stages, autopct='%1.1f%%', colors=colors, startangle=90)
    ax1.set_title('Time Breakdown by Pipeline Stage (Tier 2)',
                  fontsize=14, fontweight='bold')

    # Bar chart
    y_pos = np.arange(len(stages))
    ax2.barh(y_pos, times, color=colors)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(stages)
    ax2.set_xlabel('Mean Runtime (ms)', fontsize=12)
    ax2.set_title('Mean Runtime by Stage', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    plt.close()
    print(f"  Saved breakdown: {output_file}")


def analyze_system_overhead(tier2_timings, tier3_timings, output_dir):
    """Analyze system overhead (Tier 3 - sum of Tier 2)."""
    print("\n" + "="*80)
    print("SYSTEM OVERHEAD ANALYSIS (Tier 3 - Tier 2)")
    print("="*80)

    # Calculate mean Tier 2 times
    tier2_sum = sum(np.mean(values) for values in tier2_timings.values())

    # Get Tier 3 E2E times (assume single entry: sensor_input -> actuator_output)
    if not tier3_timings:
        print("  No Tier 3 (E2E) data found. Skipping overhead analysis.")
        return

    # Get the first (and likely only) E2E measurement
    e2e_key = list(tier3_timings.keys())[0]
    e2e_times = tier3_timings[e2e_key]
    e2e_mean = np.mean(e2e_times)

    overhead = e2e_mean - tier2_sum
    overhead_pct = (overhead / e2e_mean) * 100 if e2e_mean > 0 else 0

    output = f"""
System Overhead Breakdown:
  Tier 2 (Sum of operator times):  {tier2_sum:.2f} ms
  Tier 3 (End-to-end latency):     {e2e_mean:.2f} ms
  System Overhead:                 {overhead:.2f} ms ({overhead_pct:.1f}%)

Overhead includes:
  - Message passing between operators
  - Queue wait times
  - ERDOS scheduling latency
  - Watermark propagation delays
"""

    print(output)

    # Save to file
    overhead_file = output_dir / 'system_overhead.txt'
    with open(overhead_file, 'w') as f:
        f.write(output)
    print(f"Overhead analysis saved to: {overhead_file}")


def main():
    parser = argparse.ArgumentParser(description='Analyze Pylot two-tier timing logs')
    parser.add_argument('log_file', help='Path to pylot log file')
    parser.add_argument('--output', default='timing_results',
                        help='Output directory for results')
    parser.add_argument('--skip-warmup', type=int, default=1,
                        help='Skip first N samples per stage to exclude warmup/initialization (default: 1)')
    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Parsing timing logs from: {args.log_file}")
    data = parse_timing_logs(args.log_file)
    tier2_timings = data['tier2']
    tier3_timings = data['tier3']

    if not tier2_timings and not tier3_timings:
        print("ERROR: No timing data found in log file!")
        print("Make sure you ran Pylot with timing instrumentation enabled.")
        return

    # Tier 2 Analysis
    if tier2_timings:
        print(f"\nFound {len(tier2_timings)} pipeline stages (Tier 2):")
        for stage in sorted(tier2_timings.keys()):
            print(f"  - {stage}: {len(tier2_timings[stage])} measurements")

        # Skip warmup samples
        if args.skip_warmup > 0:
            print(f"\nSkipping first {args.skip_warmup} sample(s) per stage to exclude warmup overhead")
            for stage in tier2_timings:
                original_count = len(tier2_timings[stage])
                tier2_timings[stage] = tier2_timings[stage][args.skip_warmup:]
                skipped = original_count - len(tier2_timings[stage])
                if skipped > 0:
                    print(f"  - {stage}: skipped {skipped}, using {len(tier2_timings[stage])} samples")

        # Compute statistics for each stage
        print("\n" + "="*80)
        print("TIER 2: OPERATOR RESPONSE TIME STATISTICS")
        print("="*80)

        stats_file = output_dir / 'tier2_statistics.txt'
        stage_means = {}

        with open(stats_file, 'w') as f:
            for stage in sorted(tier2_timings.keys()):
                values = tier2_timings[stage]
                stats = compute_statistics(values)
                stage_means[stage] = stats['mean']

                output = f"\n{stage.upper()}:\n"
                output += f"  Samples:    {stats['count']}\n"
                output += f"  Mean:       {stats['mean']:.2f} ms\n"
                output += f"  Median:     {stats['median']:.2f} ms\n"
                output += f"  Std Dev:    {stats['std']:.2f} ms\n"
                output += f"  Min:        {stats['min']:.2f} ms\n"
                output += f"  Max:        {stats['max']:.2f} ms\n"
                output += f"  P95:        {stats['p95']:.2f} ms\n"
                output += f"  P99:        {stats['p99']:.2f} ms\n"

                print(output)
                f.write(output)

                # Generate CDF plot
                plot_cdf(values, f'{stage.upper()} Stage Runtime Distribution (Tier 2)',
                        output_dir / f'tier2_cdf_{stage}.png')

        print(f"\nTier 2 statistics saved to: {stats_file}")

        # Calculate time breakdown
        total_time = sum(stage_means.values())
        print("\n" + "="*80)
        print("TIME BREAKDOWN (% of total Tier 2 operator time)")
        print("="*80)

        breakdown_file = output_dir / 'tier2_breakdown.txt'
        with open(breakdown_file, 'w') as f:
            f.write("Tier 2 Stage Breakdown:\n")
            f.write("="*60 + "\n")
            for stage in sorted(stage_means.keys(), key=lambda x: stage_means[x], reverse=True):
                percentage = (stage_means[stage] / total_time) * 100
                line = f"{stage:25s}: {stage_means[stage]:8.2f} ms ({percentage:5.1f}%)\n"
                print(f"  {line.strip()}")
                f.write(line)
            f.write(f"\n{'TOTAL':25s}: {total_time:8.2f} ms (100.0%)\n")

        print(f"\nBreakdown saved to: {breakdown_file}")

        # Generate breakdown visualization
        generate_breakdown_plot(stage_means, output_dir / 'tier2_breakdown.png')

    # Tier 3 Analysis
    if tier3_timings:
        print("\n" + "="*80)
        print("TIER 3: END-TO-END PIPELINE LATENCY")
        print("="*80)

        stats_file = output_dir / 'tier3_statistics.txt'
        with open(stats_file, 'w') as f:
            for (start_stage, end_stage), values in tier3_timings.items():
                # Skip warmup
                if args.skip_warmup > 0:
                    values = values[args.skip_warmup:]

                stats = compute_statistics(values)

                output = f"\nE2E: {start_stage} → {end_stage}\n"
                output += f"  Samples:    {stats['count']}\n"
                output += f"  Mean:       {stats['mean']:.2f} ms\n"
                output += f"  Median:     {stats['median']:.2f} ms\n"
                output += f"  Std Dev:    {stats['std']:.2f} ms\n"
                output += f"  Min:        {stats['min']:.2f} ms\n"
                output += f"  Max:        {stats['max']:.2f} ms\n"
                output += f"  P95:        {stats['p95']:.2f} ms\n"
                output += f"  P99:        {stats['p99']:.2f} ms\n"

                print(output)
                f.write(output)

                # Generate CDF plot
                plot_cdf(values, f'E2E Latency: {start_stage} → {end_stage}',
                        output_dir / f'tier3_cdf_e2e.png')

        print(f"\nTier 3 statistics saved to: {stats_file}")

    # System overhead analysis
    if tier2_timings and tier3_timings:
        analyze_system_overhead(tier2_timings, tier3_timings, output_dir)

    print(f"\n{'='*80}")
    print(f"Analysis complete! Results saved to: {output_dir}/")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
