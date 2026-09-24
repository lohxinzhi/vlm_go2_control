#!/usr/bin/env bash

set -euo pipefail

repository_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="${repository_dir}/.venv"

# ROS 2 Jazzy installs rclpy and message packages system-wide. Retaining access
# to them lets ROS nodes run from the virtual environment.
python3 -m venv --system-site-packages "${venv_dir}"
"${venv_dir}/bin/python" -m pip install --upgrade pip
"${venv_dir}/bin/python" -m pip install \
  --requirement "${repository_dir}/requirements.txt"

echo "Virtual environment ready: ${venv_dir}"
echo "Activate it with: source ${venv_dir}/bin/activate"
