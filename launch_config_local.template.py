"""
Copy this file to launch_config_local.py and fill with your real values.

cp launch_config_local.template.py launch_config_local.py
"""

CONFIG_PATH = "./config"
CONFIG_PROFILE = "DEFAULT"

AVAILABILITY_DOMAINS = [
    "Avtw:EU-FRANKFURT-1-AD-1",
    "Avtw:EU-FRANKFURT-1-AD-2",
    "Avtw:EU-FRANKFURT-1-AD-3",
]

LAUNCH_OPTIONS = {
    "compartment_id": "ocid1.tenancy.oc1..<replace_me>",
    "subnet_id": "ocid1.subnet.oc1..<replace_me>",
    "image_id": "ocid1.image.oc1..<replace_me>",
    "ssh_public_key": "ssh-rsa <replace_me>",
    "display_name": "my-a1-instance",
    "shape": "VM.Standard.A1.Flex",
}

# Priority fallback sequence: try bigger configs first.
SHAPE_CONFIG_PRIORITY = [
    {"ocpus": 4, "memory_in_gbs": 24},
    {"ocpus": 2, "memory_in_gbs": 12},
    {"ocpus": 1, "memory_in_gbs": 6},
]

USE_CAPACITY_REPORT = True

REQUEST_PACE_START_DELAY = 8.0
REQUEST_PACE_MIN_DELAY = 0.8
REQUEST_PACE_MAX_DELAY = 20.0
REQUEST_PACE_DECREASE_FACTOR = 0.75
REQUEST_PACE_INCREASE_FACTOR = 1.25
THROTTLE_COOLDOWN_SECONDS = 45.0
REQUEST_PACE_JITTER_MAX = 0.3

STATE_CHECK_DELAY = 20
MAX_STATE_WAIT_SECONDS = 1800

LOG_LEVEL = "INFO"
LOG_FILE = "./logs/hunt.log"
ENABLE_TUI = True
TUI_EVENT_LINES = 8
