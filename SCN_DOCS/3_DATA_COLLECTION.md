# Data Collection and Analysis

## Workflow

```
Run Pylot → Logs to file → Analyze offline → Visualize → Iterate
```

## Collection

### Run with Timing
```bash
python3 pylot.py \
    --flagfile=configs/detection.conf \
    --v=1 \
    --log_file_name=pylot.log

# Run 500-1000 frames (~5 min) for statistical significance
# Ctrl+C to stop
```

### Verify Data
```bash
grep "TIMING" pylot.log | head -5
echo "Tier 2: $(grep 'tier=2' pylot.log | wc -l)"
echo "Tier 3: $(grep 'tier=3' pylot.log | wc -l)"
```

## Analysis

### One Command
```bash
./scripts/scn_quick_timing_analysis.sh pylot.log [output_dir] [skip_warmup]
```

**Generates:**
- tier2_statistics.txt - Per-stage stats (mean, P95, P99)
- tier2_breakdown.png - Pie + bar charts
- tier2_cdf_*.png - CDF per stage
- tier2_cdf_cumulative_all_stages.png - All on one plot
- tier3_statistics.txt - E2E latency stats
- tier3_cdf_e2e.png - E2E CDF
- system_overhead.txt - Overhead analysis

### Manual Analysis
```bash
# Comprehensive statistics
python3 scripts/scn_analyze_timing.py pylot.log \
    --output timing_results/ \
    --skip-warmup 5

# Cumulative CDF
python3 scripts/scn_plot_cumulative_cdf.py pylot.log \
    --output timing_results/ \
    --skip-warmup 5
```

### View Results
```bash
cat timing_results/tier2_statistics.txt
cat timing_results/system_overhead.txt
open timing_results/tier2_breakdown.png
```

## Output Examples

### Tier 2 Statistics
```
DETECTION:
  Mean:    45.23 ms
  Median:  43.12 ms
  P95:     58.12 ms
  P99:     72.45 ms

TRACKING:
  Mean:    12.34 ms
  ...
```

### Time Breakdown
```
detection:  45.23 ms (52%)
planning:   15.67 ms (18%)
tracking:   12.34 ms (14%)
prediction:  8.56 ms (10%)
control:     2.45 ms ( 3%)
--------------------------
TOTAL:      87.43 ms
```

### System Overhead
```
Tier 2 (operators):  87.43 ms
Tier 3 (E2E):       115.67 ms
Overhead:            28.24 ms (24%)

Overhead = message passing + queuing + scheduling
```

## Advanced Usage

### Extract Specific Metrics
```bash
# Detection times only
grep "stage=detection" pylot.log | \
    awk '{print $NF}' | \
    sed 's/response_ms=//' > detection_times.txt

# Calculate mean
awk '{sum+=$1; n++} END {print sum/n}' detection_times.txt
```

### Deadline Analysis
```python
import re
deadlines = {'detection': 50, 'tracking': 15, 'planning': 20}
misses = {s: 0 for s in deadlines}
totals = {s: 0 for s in deadlines}

with open('pylot.log') as f:
    for line in f:
        m = re.search(r'stage=(\w+).*response_ms=([\d.]+)', line)
        if m and m.group(1) in deadlines:
            totals[m.group(1)] += 1
            if float(m.group(2)) > deadlines[m.group(1)]:
                misses[m.group(1)] += 1

for stage in deadlines:
    rate = 100 * misses[stage] / totals[stage] if totals[stage] > 0 else 0
    print(f"{stage}: {misses[stage]}/{totals[stage]} ({rate:.1f}%)")
```

### Compare Configurations
```bash
# Run different models
python3 pylot.py --obstacle_detection_model_names=efficientdet-d2 --log_file_name=d2.log --v=1
python3 pylot.py --obstacle_detection_model_names=efficientdet-d4 --log_file_name=d4.log --v=1

# Analyze each
./scripts/scn_quick_timing_analysis.sh d2.log results_d2/
./scripts/scn_quick_timing_analysis.sh d4.log results_d4/

# Compare
diff results_d2/tier2_statistics.txt results_d4/tier2_statistics.txt
```

## Performance Tips

### Logging Overhead
**Logger-based (our approach):**
- ~30μs per log entry
- Buffered, async I/O
- <0.1% overhead

**Print-based (DON'T USE):**
- ~500μs per print
- Synchronous I/O
- Can slow pipeline by 5-10%

### Recommended Settings

| Scenario | Log Level | Skip Warmup | Notes |
|----------|-----------|-------------|-------|
| Production | `--v=0` | N/A | No timing |
| Benchmarking | `--v=1` | 5-10 | Skip init |
| Long runs | `--v=1` | 20-50 | Large dataset |
| Debugging | `--v=2` | 0 | All logs |

## Typical Values

**1920x1080, EfficientDet-D4:**
- Detection: 40-80ms (P95: 70ms)
- Tracking: 10-20ms (P95: 18ms)
- Prediction: 5-15ms (P95: 12ms)
- Planning: 10-25ms (P95: 22ms)
- Control: 1-5ms (P95: 6ms)
- **E2E: 100-150ms (P95: 150ms)**
- **Overhead: 20-30%**
