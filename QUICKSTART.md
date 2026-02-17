# Quick Start

## 1. Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure OCI credentials
```bash
cp config.template config
```
Fill `config` with your real OCI values.

## 3. Configure launcher
```bash
cp launch_config_local.template.py launch_config_local.py
```
Edit `launch_config_local.py` and set:
- `AVAILABILITY_DOMAINS`
- `LAUNCH_OPTIONS.compartment_id`
- `LAUNCH_OPTIONS.subnet_id`
- `LAUNCH_OPTIONS.image_id`
- `LAUNCH_OPTIONS.ssh_public_key`
- `LAUNCH_OPTIONS.display_name`

Optional tuning:
- `SHAPE_CONFIG_PRIORITY`
- `RETRY_BASE_DELAY`, `RETRY_MAX_DELAY`, `RETRY_JITTER_MAX`
- `STATE_CHECK_DELAY`, `MAX_STATE_WAIT_SECONDS`

## 4. Run
```bash
./run.sh
```

## What the script does
- Tries all configured ADs in rotation.
- Tries shape configs in rotation (larger to smaller by default).
- Retries only transient/capacity OCI failures.
- Uses exponential backoff with jitter.
- Waits for `RUNNING` with timeout + terminal-state checks.

## Common checks
```bash
# Validate syntax
python3 -m py_compile launch_a1_flex.py launch_config.py launch_config_local.template.py

# Follow runtime logs (if LOG_FILE is enabled)
tail -f logs/hunt.log
```
