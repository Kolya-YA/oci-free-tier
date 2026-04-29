# Quick Start

## 1. Setup
```bash
chmod +x setup.sh run.sh
./setup.sh
```

## 2. Configure OCI credentials
Edit `config` and fill with your real OCI values (template created by setup script).

## 3. Configure launcher
Edit `launch_config_local.py` and set your OCIDs and SSH key.

Optional tuning:
- `AVAILABILITY_DOMAINS`
- `SHAPE_CONFIG_PRIORITY`
- `REQUEST_PACE_START_DELAY`, `REQUEST_PACE_MIN_DELAY`, `REQUEST_PACE_MAX_DELAY`
- `STATE_CHECK_DELAY`, `MAX_STATE_WAIT_SECONDS`
- `ENABLE_TUI`

## 4. Validate and Run
```bash
# Test connectivity and config
./run.sh --dry-run

# Start hunting
./run.sh
```

## What the script does
- Tries all configured ADs in rotation.
- Tries shape configs in rotation (larger to smaller by default).
- Uses `create_compute_capacity_report` pre-check for AD/shape capacity.
- Retries only transient/capacity OCI failures.
- Uses adaptive pacing: faster until throttled, then backs off and cools down.
- Waits for `RUNNING` with timeout + terminal-state checks.
- Uses single-screen TUI dashboard by default.

Note: repeated `500/InternalError` often means temporary OCI capacity shortage, not a bad config.

## Common checks
```bash
# Follow runtime logs
tail -f logs/hunt.log
```
