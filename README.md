# OCI Free Tier Capacity Helper

A resilient launcher for `VM.Standard.A1.Flex` that keeps trying until an instance is `RUNNING`.

## What is improved
- Safe config split: repository-safe defaults in `launch_config.py`, real secrets in `launch_config_local.py` (git-ignored).
- Retry policy: retries only transient OCI errors and capacity errors.
- Exponential backoff with jitter to avoid aggressive fixed-loop retries.
- Idempotency guard via `opc_retry_token`.
- Duplicate protection by checking existing active instances with the same `display_name`.
- Adaptive shape strategy (4/24 -> 2/12 -> 1/6) for better capacity acquisition odds.
- Timeout and terminal-state handling while waiting for `RUNNING`.

## Prerequisites
- Python 3.9+.
- OCI API key with permissions to launch instances.
- OCI config file values (`user`, `fingerprint`, `tenancy`, `region`, `key_file`).

## Setup
1. Create venv and install deps:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Create OCI SDK config:
   ```bash
   cp config.template config
   ```
3. Create local launch config:
   ```bash
   cp launch_config_local.template.py launch_config_local.py
   ```
4. Edit `launch_config_local.py` with your real OCIDs, SSH key, ADs, and preferred tuning values.

## Run
Preferred wrapper (keeps Mac awake):
```bash
./run.sh
```

Direct run:
```bash
source .venv/bin/activate
python3 launch_a1_flex.py
```

## Runtime behavior
- Cycles over availability domains.
- Cycles over shape fallback strategy in order.
- Retries transient failures with exponential backoff + jitter.
- Stops immediately on non-retryable OCI errors.
- Reuses an already active instance with the same `display_name` if found.
- Exits with non-zero status on fatal/terminal/timeout failures.

## Project structure
- `launch_a1_flex.py` - Main launcher logic.
- `launch_config.py` - Safe defaults tracked in git.
- `launch_config_local.template.py` - Copy to create your local config.
- `launch_config_local.py` - Local overrides (ignored by git).
- `run.sh` - Wrapper with `caffeinate` and venv activation.
- `config.template` - OCI SDK config template.

## Security notes
- Never commit `launch_config_local.py`, private keys, or OCI credentials.
- Rotate credentials if secrets were previously committed.
