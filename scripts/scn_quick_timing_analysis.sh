#!/bin/bash
#
# Quick Timing Analysis Wrapper Script
#
# This script runs both analyze_timing.py and plot_cumulative_cdf.py
# with sensible defaults.
#
# Usage:
#   ./scripts/quick_timing_analysis.sh pylot.log
#   ./scripts/quick_timing_analysis.sh pylot.log timing_results/
#   ./scripts/quick_timing_analysis.sh pylot.log timing_results/ 10

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}Error: Missing log file argument${NC}"
    echo ""
    echo "Usage: $0 <log_file> [output_dir] [skip_warmup]"
    echo ""
    echo "Arguments:"
    echo "  log_file     Path to Pylot log file (required)"
    echo "  output_dir   Output directory (default: timing_results/)"
    echo "  skip_warmup  Number of warmup samples to skip (default: 5)"
    echo ""
    echo "Example:"
    echo "  $0 pylot.log"
    echo "  $0 pylot.log my_results/ 10"
    exit 1
fi

LOG_FILE="$1"
OUTPUT_DIR="${2:-timing_results}"
SKIP_WARMUP="${3:-5}"

# Check if log file exists
if [ ! -f "$LOG_FILE" ]; then
    echo -e "${RED}Error: Log file not found: $LOG_FILE${NC}"
    exit 1
fi

# Check if log file has TIMING data
TIMING_COUNT=$(grep -c "TIMING" "$LOG_FILE" || true)
if [ "$TIMING_COUNT" -eq 0 ]; then
    echo -e "${RED}Error: No TIMING data found in log file!${NC}"
    echo ""
    echo "Make sure you:"
    echo "  1. Ran Pylot with --v=1 flag (enable INFO logging)"
    echo "  2. Have timing instrumentation enabled in the code"
    echo ""
    exit 1
fi

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Pylot Timing Analysis${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Log file:       $LOG_FILE"
echo "Output dir:     $OUTPUT_DIR"
echo "Skip warmup:    $SKIP_WARMUP samples"
echo "Timing entries: $TIMING_COUNT"
echo ""

# Get script directory (where this script lives)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Run comprehensive analysis
echo -e "${YELLOW}[1/2] Running comprehensive timing analysis...${NC}"
python3 "$SCRIPT_DIR/scn_analyze_timing.py" "$LOG_FILE" \
    --output "$OUTPUT_DIR" \
    --skip-warmup "$SKIP_WARMUP"

echo ""

# Run cumulative CDF plot
echo -e "${YELLOW}[2/2] Generating cumulative CDF plot...${NC}"
python3 "$SCRIPT_DIR/scn_plot_cumulative_cdf.py" "$LOG_FILE" \
    --output "$OUTPUT_DIR" \
    --skip-warmup "$SKIP_WARMUP"

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Analysis Complete!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Results saved to: $OUTPUT_DIR/"
echo ""
echo "Key files:"
echo "  - tier2_statistics.txt         (per-stage statistics)"
echo "  - tier2_breakdown.png          (pie + bar charts)"
echo "  - tier2_cdf_cumulative_all_stages.png  (all stages CDF)"
echo "  - tier3_statistics.txt         (E2E latency stats)"
echo "  - system_overhead.txt          (overhead analysis)"
echo ""
echo "To view results:"
echo "  cat $OUTPUT_DIR/tier2_statistics.txt"
echo "  open $OUTPUT_DIR/tier2_breakdown.png"
echo ""
