#!/usr/bin/env bash
# Written by Claude Code
#
# Calibrates a camera's intrinsics with cameracalibrator (with the ROS2 package camera_calibration) and a printed
# checkerboard. Pass the board's inner corners (columns x rows) and the side of one square, measured on the print:
#   scripts/run_cameracalibrator.sh <inner corners, e.g. 8x6> <square size in m> [more cameracalibrator options]
#   scripts/run_cameracalibrator.sh 8x6 0.031

# Some cameras such as the Azure Kinect do not need this script. Their driver already publishes its factory calibration.

# It works on a camera's image_raw and set_camera_info in the camera's namespace, which CAMERA_NAMESPACE names:
# /cameras/<camera> for a framework camera (each camera's launch file maps its driver onto these names), e.g.
#   CAMERA_NAMESPACE=/cameras/blackfly scripts/run_cameracalibrator.sh 8x6 0.031
# or any other camera node's namespace.
#
# COMMIT stores the result through set_camera_info at the node's camera_info_url, which the framework's launch
# files set to config/calibration/intrinsics/<profile>/camera_info_<camera>.yaml (without profile:=, the shared
# config/calibration/intrinsics/camera_info_<camera>.yaml), so start the camera with the profile it is calibrated
# for.

# Needs ROS sourced and the camera node running and publishing with qos_reliability:=reliable.
# The calibrator only copies the publisher's QoS if it discovers the topic at startup, and otherwise subscribes reliably.


source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if (( $# < 2 )); then
    die "usage: $0 <inner corners, e.g. 8x6> <square size in m> [cameracalibrator options]"
fi
if ! command_exists ros2; then
    die "ROS is not sourced -- run: source /opt/ros/${ROS_DISTRO}/setup.bash"
fi

board_size="$1"
square_size_m="$2"
shift 2    # the remaining arguments are passed on to cameracalibrator
camera_namespace="${CAMERA_NAMESPACE:-}"
if [[ -z "$camera_namespace" ]]; then
    die "CAMERA_NAMESPACE is not set -- run e.g.: CAMERA_NAMESPACE=/cameras/blackfly $0 $board_size $square_size_m (ros2 topic list shows the cameras)"
fi

if [[ ! "$board_size" =~ ^[0-9]+x[0-9]+$ ]]; then
    die "inner corners must look like 8x6 (columns x rows), got '$board_size' -- run: $0 8x6 0.031"
fi

# Must match the camera node's transport (the framework's terminals export LARGE_DATA), otherwise the two
# don't see each other at all
export FASTDDS_BUILTIN_TRANSPORTS="${FASTDDS_BUILTIN_TRANSPORTS:-LARGE_DATA}"

# Simplification: workarounds for camera_calibration 7.1.7, patched in at runtime instead of forking the
# package. Drop them once apt ships a fixed version.
calibrator_code="$(cat <<'EOF'
import sys
# Its option parser would read sys.argv[0], which is "-c" here, as --camera_name
sys.argv[0] = 'cameracalibrator'

import rclpy
# A successful COMMIT shuts rclpy down, then main() shuts it down again, which this rclpy rejects with
# "Context must be initialized before it can be shutdown". try_shutdown skips an already shut down context.
rclpy.shutdown = rclpy.try_shutdown

from rclpy.impl.rcutils_logger import RcutilsLogger
# It calls logger.warn(), which rclpy no longer has, for every topic without a publisher (/left and /right
# always in a monocular run)
RcutilsLogger.warn = RcutilsLogger.warning

from camera_calibration.nodes.cameracalibrator import main
main()
EOF
)"

# exec replaces this shell with the calibrator, so its exit code is the script's.
# --no-service-check: its startup check waits only 1 s for set_camera_info, less than discovery can take.
exec python3 -c "$calibrator_code" \
    --size "$board_size" --square "$square_size_m" --no-service-check "$@" \
    --ros-args \
    -r image:="${camera_namespace}/image_raw" \
    -r camera/set_camera_info:="${camera_namespace}/set_camera_info"
