#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WS="$(cd -- "${GO2_WORKSPACE:-$SCRIPT_DIR/..}" && pwd)"
if [[ ${GO2_CLEAN_ENV:-} != 1 ]]; then
  exec env -i HOME="$HOME" USER="$USER" LOGNAME="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C.UTF-8 DISPLAY="${DISPLAY:-}" XAUTHORITY="${XAUTHORITY:-}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" GO2_WORKSPACE="$WS" GO2_CLEAN_ENV=1 "$SCRIPT_DIR/jazzy_exec.bash" "$@"
fi
export GO2_WORKSPACE="$WS"
export ROS_HOME="$WS/.ros" ROS_LOG_DIR="$WS/.ros/log"
export XDG_CACHE_HOME="$WS/.runtime/cache" XDG_CONFIG_HOME="$WS/.runtime/config" TMPDIR="$WS/.runtime/tmp"
mkdir -p "$ROS_LOG_DIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$TMPDIR"
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
source /opt/ros/jazzy/setup.bash
if [[ -f "$WS/install/local_setup.bash" ]]; then source "$WS/install/local_setup.bash"; fi
cd "$WS"
exec "$@"
