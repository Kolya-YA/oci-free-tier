# OCI Free Tier Capacity Helper

A resilient automation tool for launching `VM.Standard.A1.Flex` (ARM Ampere) instances in Oracle Cloud Infrastructure (OCI).
 The script continuously retries launch requests until an instance is successfully `RUNNING`.

## Key Features
- **Automation**: `setup.sh` handles virtual environment creation and configuration templating.
- **Safety**: Sensitive credentials are kept in `launch_config_local.py` (git-ignored).
- **Adaptive Pacing**: Request intervals decrease on success and increase on throttling (429 Error) to avoid bans.
- **Log Rotation**: Prevents disk exhaustion using `RotatingFileHandler` (keeps the last 3 files, 5MB each).
- **Validation Mode**: Test your OCI connectivity and config without launching an instance using `--dry-run`.
- **Modern TUI Dashboard**: Real-time monitoring of attempts, capacity reports, and events in a clean terminal UI.

## Prerequisites
- Python 3.9+.
- OCI API Key and tenancy details (`user`, `fingerprint`, `tenancy`, `region`, `key_file`).

## Quick Start
1. Run the automatic setup script:
   ```bash
   chmod +x setup.sh run.sh
   ./setup.sh
   ```
2. Fill the `config` file with your OCI SDK credentials.
3. Edit `launch_config_local.py` with your OCIDs (compartment, subnet, image) and SSH public key.

## Run
Use the wrapper script (it includes `caffeinate` to prevent Mac from sleeping):
```bash
# Validate connectivity and config
./run.sh --dry-run

# Start hunting for capacity
./run.sh
```

## How It Works
- **AD Rotation**: Cycles through all configured Availability Domains.
- **Shape Strategy**: Prioritizes larger shapes (e.g., 4 OCPU) and falls back to smaller ones (2, then 1) to maximize success odds.
- **Pre-flight Checks**: Probes for capacity using OCI `Capacity Report` before attempting a launch.
- **Idempotency**: Automatically reuses an existing active instance with the same `display_name` if found.

## Project Structure
- `launch_a1_flex.py` — Main logic and TUI.
- `setup.sh` — Environment and config initialization.
- `run.sh` — Execution wrapper (venv activation + sleep prevention).
- `launch_config.py` — Baseline configuration.
- `launch_config_local.py` — Local overrides and secrets.
- `logs/` — Directory for runtime logs.

## Security
- Never commit your `config`, `launch_config_local.py`, or private `.pem` keys.
- All sensitive files are pre-configured in `.gitignore`.
