#!/bin/bash
set -euo pipefail

# OCI Free Tier Capacity Helper - Setup Script

echo "Starting setup..."

if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt

if [[ ! -f "config" ]]; then
    echo "Creating config from template..."
    cp config.template config
    echo "!!! Action Required: Edit 'config' with your OCI API credentials."
fi

if [[ ! -f "launch_config_local.py" ]]; then
    echo "Creating launch_config_local.py from template..."
    cp launch_config_local.template.py launch_config_local.py
    echo "!!! Action Required: Edit 'launch_config_local.py' with your tenancy details."
fi

mkdir -p logs

echo "Setup complete. After configuring 'config' and 'launch_config_local.py', run ./run.sh"
