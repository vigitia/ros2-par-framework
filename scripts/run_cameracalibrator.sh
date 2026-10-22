#!/usr/bin/env bash
# Written by Claude Code
#
# Calibrates a camera's intrinsics with cameracalibrator (package camera_calibration) and the board from
# utils/checkerboard.png (8x6 inner corners; print it and measure one square):
#   scripts/run_cameracalibrator.sh <square size in m> [more cameracalibrator options]
#   scripts/run_cameracalibrator.sh 0.031
#
# It works on the framework's camera topics /camera/image_raw and /camera/set_camera_info, which the launch
# files remap every camera driver onto (launch_helpers.DRIVER_REMAPPINGS), so the same call fits the Brio and
# the webcam. CAMERA_NAMESPACE points it at a camera node outside the framework, e.g.
#   CAMERA_NAMESPACE=/my_camera scripts/run_cameracalibrator.sh 0.031
#
# COMMIT stores the result through set_camera_info at the node's camera_info_url, which the framework's launch
# files set to config/calibration/intrinsics/camera_info_<camera>.yaml. The Kinect needs none: its driver
# publishes its factory calibration.
#
# Needs ROS sourced and the camera node running and publishing reliably (the Brio with
# qos_reliability:=reliable; v4l2_camera does already): the calibrator only copies the publisher's QoS if it
# discovers the topic at startup, and otherwise subscribes reliably.
# Moved here from the logitech_brio repository (calibration/), whose history has the earlier versions.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if (( $# < 1 )); then
    die "usage: $0 <square size in m> [cameracalibrator options]"
fi
if ! command_exists ros2; then
    die "ROS is not sourced -- run: source /opt/ros/${ROS_DISTRO}/setup.bash"
fi

square_size_m="$1"
shift    # the remaining arguments are passed on to cameracalibrator
camera_namespace="${CAMERA_NAMESPACE:-/camera}"

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
    --size 8x6 --square "$square_size_m" --no-service-check "$@" \
    --ros-args \
    -r image:="${camera_namespace}/image_raw" \
    -r camera/set_camera_info:="${camera_namespace}/set_camera_info"
