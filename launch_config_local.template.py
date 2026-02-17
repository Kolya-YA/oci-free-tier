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

RETRY_BASE_DELAY = 12
RETRY_MAX_DELAY = 120
RETRY_JITTER_MAX = 3.0

STATE_CHECK_DELAY = 20
MAX_STATE_WAIT_SECONDS = 1800

LOG_LEVEL = "INFO"
LOG_FILE = "./logs/hunt.log"
