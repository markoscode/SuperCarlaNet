#!/bin/bash

# SuperCarlaNet - Pylot Setup and Run Script
# This script provides functions for setting up and running Pylot with SCN timing instrumentation

set -e  # Exit on error

# Configuration
CONTAINER_NAME="pylot2scn"
DOCKER_IMAGE="erdosproject/pylot"
PYLOT_HOME_CONTAINER="/home/erdos/workspace/pylot"
CARLA_HOME_CONTAINER="${PYLOT_HOME_CONTAINER}/dependencies/CARLA_0.9.10.1"
SSH_PORT="22022"  # SSH port mapping (host:container)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
}

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"
}

container_running() {
    docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"
}

# 1. Create Docker container with GPU support
create_container() {
    log_info "Creating Docker container: ${CONTAINER_NAME}"

    if container_exists; then
        log_warn "Container ${CONTAINER_NAME} already exists"
        read -p "Remove and recreate? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker rm -f ${CONTAINER_NAME}
        else
            log_info "Skipping container creation"
            return
        fi
    fi

    docker run -itd \
        --gpus all \
        --shm-size=16g \
        --name ${CONTAINER_NAME} \
        -p ${SSH_PORT}:22 \
        ${DOCKER_IMAGE} \
        /bin/bash

    log_info "Container created successfully"
}

# 2. Fix pylot.utils package structure
fix_utils_package() {
    log_info "Fixing pylot.utils package structure"

    docker exec ${CONTAINER_NAME} bash -c "mkdir -p ${PYLOT_HOME_CONTAINER}/pylot/utils && \
        cp ${PYLOT_HOME_CONTAINER}/pylot/utils.py ${PYLOT_HOME_CONTAINER}/pylot/utils/__init__.py"

    log_info "Package structure fixed"
}

# 3. Copy SCN timing files
copy_timing_files() {
    log_info "Copying SCN timing files"

    docker cp pylot/utils/scn_timing.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/utils/
    docker cp pylot/utils/scn_timing_config.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/utils/

    log_info "Timing files copied"
}

# 4. Copy analysis scripts
copy_analysis_scripts() {
    log_info "Copying analysis scripts"

    docker cp scripts/scn_analyze_timing.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/scripts/
    docker cp scripts/scn_plot_cumulative_cdf.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/scripts/
    docker cp scripts/scn_quick_timing_analysis.sh ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/scripts/

    log_info "Analysis scripts copied"
}

# 5. Copy all 14 modified operators
copy_operators() {
    log_info "Copying modified operators (14 files)"

    # Detection (4)
    log_info "  Copying detection operators..."
    docker cp pylot/perception/detection/detection_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/perception/detection/
    docker cp pylot/perception/detection/efficientdet_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/perception/detection/
    docker cp pylot/perception/detection/lanenet_detection_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/perception/detection/
    docker cp pylot/perception/detection/traffic_light_det_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/perception/detection/

    # Segmentation (1)
    log_info "  Copying segmentation operators..."
    docker cp pylot/perception/segmentation/segmentation_drn_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/perception/segmentation/

    # Tracking (1)
    log_info "  Copying tracking operators..."
    docker cp pylot/perception/tracking/object_tracker_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/perception/tracking/

    # Localization (1)
    log_info "  Copying localization operators..."
    docker cp pylot/localization/localization_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/localization/

    # Prediction (2)
    log_info "  Copying prediction operators..."
    docker cp pylot/prediction/linear_predictor_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/prediction/
    docker cp pylot/prediction/r2p2_predictor_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/prediction/

    # Planning (2)
    log_info "  Copying planning operators..."
    docker cp pylot/planning/planning_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/planning/
    docker cp pylot/planning/behavior_planning_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/planning/

    # Control (2)
    log_info "  Copying control operators..."
    docker cp pylot/control/pid_control_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/control/
    docker cp pylot/control/mpc/mpc_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/control/mpc/

    # Camera driver (1)
    log_info "  Copying camera driver..."
    docker cp pylot/drivers/carla_camera_driver_operator.py ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot/drivers/

    log_info "All operators copied successfully"
}

# Setup: Run all setup steps
setup_all() {
    check_docker
    create_container
    sleep 2  # Wait for container to be ready
    fix_utils_package
    copy_timing_files
    copy_analysis_scripts
    copy_operators
    log_info "Setup complete!"
}

# Start CARLA Simulator
start_carla() {
    log_info "Starting CARLA simulator"

    if ! container_running; then
        log_error "Container ${CONTAINER_NAME} is not running"
        exit 1
    fi

    docker exec ${CONTAINER_NAME} bash -c "export CARLA_HOME=${CARLA_HOME_CONTAINER} && \
        nohup bash ${PYLOT_HOME_CONTAINER}/scripts/run_simulator.sh > /tmp/carla.log 2>&1 &"

    log_info "Waiting 30 seconds for CARLA to initialize..."
    sleep 30
    log_info "CARLA should be ready"
}

# Run Pylot with timing (foreground)
run_pylot() {
    log_info "Running Pylot with timing instrumentation"

    if ! container_running; then
        log_error "Container ${CONTAINER_NAME} is not running"
        exit 1
    fi

    docker exec ${CONTAINER_NAME} bash -c "export PYLOT_HOME=${PYLOT_HOME_CONTAINER} && \
        export CARLA_HOME=${CARLA_HOME_CONTAINER} && \
        source ${PYLOT_HOME_CONTAINER}/scripts/set_pythonpath.sh && \
        cd ${PYLOT_HOME_CONTAINER} && \
        python3 pylot.py --flagfile=configs/detection.conf --v=1 --log_file_name=pylot_timing.log"
}

# Run Pylot with timing (background)
run_pylot_bg() {
    log_info "Running Pylot in background with timing instrumentation"

    if ! container_running; then
        log_error "Container ${CONTAINER_NAME} is not running"
        exit 1
    fi

    docker exec ${CONTAINER_NAME} bash -c "export PYLOT_HOME=${PYLOT_HOME_CONTAINER} && \
        export CARLA_HOME=${CARLA_HOME_CONTAINER} && \
        source ${PYLOT_HOME_CONTAINER}/scripts/set_pythonpath.sh && \
        cd ${PYLOT_HOME_CONTAINER} && \
        nohup python3 pylot.py --flagfile=configs/detection.conf --v=1 --log_file_name=pylot_timing.log > /tmp/pylot_run.log 2>&1 &"

    log_info "Pylot started in background"
}

# Stop Pylot
stop_pylot() {
    log_info "Stopping Pylot"

    docker exec ${CONTAINER_NAME} pkill -f "python3 pylot.py" || log_warn "No Pylot process found"

    log_info "Pylot stopped"
}

# Verify timing logs
verify_timing() {
    log_info "Verifying timing logs"

    docker exec ${CONTAINER_NAME} bash -c "grep 'TIMING' ${PYLOT_HOME_CONTAINER}/pylot_timing.log | head -5"

    log_info "Expected format: TIMING tier=2 stage=detection ts=..."
}

# Analyze timing data
analyze_timing() {
    local skip_warmup=${1:-10}

    log_info "Analyzing timing data (skip first ${skip_warmup} samples)"

    docker exec ${CONTAINER_NAME} bash -c "cd ${PYLOT_HOME_CONTAINER} && \
        bash scripts/scn_quick_timing_analysis.sh pylot_timing.log timing_results ${skip_warmup}"

    log_info "Analysis complete. Copying results to host..."

    docker cp ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/timing_results ./
    docker cp ${CONTAINER_NAME}:${PYLOT_HOME_CONTAINER}/pylot_timing.log ./

    log_info "Results copied to ./timing_results and ./pylot_timing.log"

    if [ -f timing_results/tier2_statistics.txt ]; then
        log_info "Tier 2 Statistics:"
        cat timing_results/tier2_statistics.txt
    fi
}

# Manual analysis
analyze_timing_manual() {
    local skip_warmup=${1:-10}

    log_info "Running manual timing analysis"

    docker exec ${CONTAINER_NAME} bash -c "cd ${PYLOT_HOME_CONTAINER} && \
        python3 scripts/scn_analyze_timing.py pylot_timing.log --output timing_results/ --skip-warmup ${skip_warmup}"

    log_info "Analysis complete"
}

# Full workflow: setup and run
full_run() {
    log_info "Starting full workflow"
    setup_all
    start_carla
    run_pylot_bg
    log_info "Full workflow started. Pylot is running in background."
    log_info "Use 'stop_pylot' to stop and 'analyze_timing' to analyze results"
}

# Show usage
usage() {
    cat << EOF
SuperCarlaNet - Pylot Setup and Run Script

Usage: $0 <command> [args]

Commands:
  setup_all               - Run complete setup (create container, copy files)
  create_container        - Create Docker container with GPU support
  fix_utils_package       - Fix pylot.utils package structure
  copy_timing_files       - Copy SCN timing instrumentation files
  copy_analysis_scripts   - Copy analysis scripts
  copy_operators          - Copy all 14 modified operators

  start_carla            - Start CARLA simulator
  run_pylot              - Run Pylot with timing (foreground)
  run_pylot_bg           - Run Pylot with timing (background)
  stop_pylot             - Stop running Pylot
  verify_timing          - Verify timing logs are being generated

  analyze_timing [N]     - Analyze timing data (skip first N samples, default 10)
  analyze_timing_manual [N] - Manual analysis (skip first N samples, default 10)

  full_run               - Complete workflow: setup, start CARLA, run Pylot

  help                   - Show this help message

Examples:
  $0 setup_all           # Complete setup
  $0 start_carla         # Start CARLA
  $0 run_pylot_bg        # Run Pylot in background
  $0 analyze_timing 10   # Analyze results, skip first 10 samples
  $0 full_run            # Do everything

EOF
}

# Main script logic
main() {
    # Default to full_run if no arguments provided
    local command="${1:-full_run}"

    case "$command" in
        setup_all)
            setup_all
            ;;
        create_container)
            check_docker
            create_container
            ;;
        fix_utils_package)
            fix_utils_package
            ;;
        copy_timing_files)
            copy_timing_files
            ;;
        copy_analysis_scripts)
            copy_analysis_scripts
            ;;
        copy_operators)
            copy_operators
            ;;
        start_carla)
            start_carla
            ;;
        run_pylot)
            run_pylot
            ;;
        run_pylot_bg)
            run_pylot_bg
            ;;
        stop_pylot)
            stop_pylot
            ;;
        verify_timing)
            verify_timing
            ;;
        analyze_timing)
            analyze_timing "$2"
            ;;
        analyze_timing_manual)
            analyze_timing_manual "$2"
            ;;
        full_run)
            full_run
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log_error "Unknown command: $1"
            usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
