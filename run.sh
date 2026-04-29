#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "${SCRIPT_DIR}/.venv" ]]; then
    echo "Error: Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi

source "${SCRIPT_DIR}/.venv/bin/activate"

# Use caffeinate on macOS to prevent sleep, if available.
if command -v caffeinate >/dev/null 2>&1; then
    echo "Starting with caffeinate (macOS)..."
    exec caffeinate -is python3 "${SCRIPT_DIR}/launch_a1_flex.py" "$@"
else
    exec python3 "${SCRIPT_DIR}/launch_a1_flex.py" "$@"
fi
