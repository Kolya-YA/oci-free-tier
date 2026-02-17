"""
Safe, repository-tracked defaults for OCI A1.Flex launcher.

Place real tenancy values into launch_config_local.py.
This file is intentionally non-sensitive and can be committed.
"""

# Path/profile for the OCI config file
CONFIG_PATH = "./config"
CONFIG_PROFILE = "DEFAULT"

# Availability Domains to cycle through.
# Replace with AD names for your region in launch_config_local.py.
AVAILABILITY_DOMAINS = [
    "Avtw:REGION-AD-1",
    "Avtw:REGION-AD-2",
    "Avtw:REGION-AD-3",
]

# Base launch parameters (non-sensitive placeholders)
LAUNCH_OPTIONS = {
    "compartment_id": "ocid1.compartment.oc1..<replace_me>",
    "subnet_id": "ocid1.subnet.oc1..<replace_me>",
    "image_id": "ocid1.image.oc1..<replace_me>",
    "ssh_public_key": "ssh-rsa <replace_me>",
    "display_name": "a1-flex-hunter",
    "shape": "VM.Standard.A1.Flex",
}

# Adaptive shape strategy: larger first, then smaller fallback sizes.
SHAPE_CONFIG_PRIORITY = [
    {"ocpus": 4, "memory_in_gbs": 24},
    {"ocpus": 2, "memory_in_gbs": 12},
    {"ocpus": 1, "memory_in_gbs": 6},
]

# Retry tuning
RETRY_BASE_DELAY = 12
RETRY_MAX_DELAY = 120
RETRY_JITTER_MAX = 3.0

# Instance state polling
STATE_CHECK_DELAY = 20
MAX_STATE_WAIT_SECONDS = 1800

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "./logs/hunt.log"

# Optional local overrides (ignored by git)
try:
    from launch_config_local import *  # type: ignore # noqa: F401,F403
except ImportError:
    pass
