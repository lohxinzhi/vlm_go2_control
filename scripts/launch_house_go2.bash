#!/usr/bin/env bash
# Shared apartment + existing team controllers/camera; no motion commands.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/jazzy_exec.bash" ros2 launch go2_house_world apartment_go2.launch.py "$@"
