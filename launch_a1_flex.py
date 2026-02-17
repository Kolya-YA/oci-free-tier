"""Retry OCI A1.Flex launch requests until an instance is RUNNING."""
from __future__ import annotations

import logging
import random
import time
import uuid
from pathlib import Path
from typing import Any

import oci
from oci.exceptions import ServiceError

import launch_config as cfg

TERMINAL_INSTANCE_STATES = {"TERMINATED", "STOPPED", "STOPPING", "FAULTY"}
RETRYABLE_HTTP_STATUSES = {409, 429, 500, 502, 503, 504}


logger = logging.getLogger("a1_flex_hunter")


def setup_logging() -> None:
    """Configure console + optional file logging."""
    level_name = str(getattr(cfg, "LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_file = str(getattr(cfg, "LOG_FILE", "")).strip()
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path))

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
    )


def validate_config() -> None:
    """Fail fast for clearly invalid local configuration."""
    if not cfg.AVAILABILITY_DOMAINS:
        raise ValueError("AVAILABILITY_DOMAINS must not be empty")

    required_keys = ("compartment_id", "subnet_id", "image_id", "ssh_public_key", "display_name", "shape")
    missing = [key for key in required_keys if key not in cfg.LAUNCH_OPTIONS or not cfg.LAUNCH_OPTIONS[key]]
    if missing:
        raise ValueError(f"Missing required LAUNCH_OPTIONS keys: {', '.join(missing)}")

    for key in ("compartment_id", "subnet_id", "image_id"):
        value = str(cfg.LAUNCH_OPTIONS[key])
        if "<replace_me>" in value or not value.startswith("ocid1."):
            raise ValueError(f"Invalid {key}: configure launch_config_local.py")

    ssh_key = str(cfg.LAUNCH_OPTIONS["ssh_public_key"])
    if "<replace_me>" in ssh_key or not ssh_key.startswith("ssh-"):
        raise ValueError("Invalid ssh_public_key: configure launch_config_local.py")


def shape_priority() -> list[dict[str, Any]]:
    """Return validated shape configs in launch priority order."""
    raw = list(getattr(cfg, "SHAPE_CONFIG_PRIORITY", []))
    if not raw:
        raise ValueError("SHAPE_CONFIG_PRIORITY must contain at least one shape config")

    normalized: list[dict[str, Any]] = []
    for item in raw:
        ocpus = int(item["ocpus"])
        memory = int(item["memory_in_gbs"])
        if ocpus <= 0 or memory <= 0:
            raise ValueError("Shape values must be positive")
        normalized.append({"ocpus": ocpus, "memory_in_gbs": memory})
    return normalized


def build_launch_details(ad: str, shape_cfg: dict[str, Any]) -> oci.core.models.LaunchInstanceDetails:
    """Build OCI launch request payload."""
    return oci.core.models.LaunchInstanceDetails(
        availability_domain=ad,
        compartment_id=cfg.LAUNCH_OPTIONS["compartment_id"],
        shape=cfg.LAUNCH_OPTIONS["shape"],
        subnet_id=cfg.LAUNCH_OPTIONS["subnet_id"],
        metadata={"ssh_authorized_keys": cfg.LAUNCH_OPTIONS["ssh_public_key"]},
        create_vnic_details=oci.core.models.CreateVnicDetails(
            assign_public_ip=True,
            assign_private_dns_record=True,
            subnet_id=cfg.LAUNCH_OPTIONS["subnet_id"],
        ),
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=shape_cfg["ocpus"],
            memory_in_gbs=shape_cfg["memory_in_gbs"],
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=cfg.LAUNCH_OPTIONS["image_id"],
        ),
        display_name=cfg.LAUNCH_OPTIONS["display_name"],
    )


def is_retryable_service_error(exc: ServiceError) -> bool:
    """Retry only transient OCI API failures and explicit capacity errors."""
    if exc.status in RETRYABLE_HTTP_STATUSES:
        if exc.status != 409:
            return True
        code = str(getattr(exc, "code", "") or "").lower()
        message = str(getattr(exc, "message", "") or "").lower()
        return "outofhostcapacity" in code or "out of host capacity" in message

    return False


def backoff_delay(consecutive_failures: int) -> float:
    """Exponential backoff with jitter for retry loops."""
    base = max(1, int(getattr(cfg, "RETRY_BASE_DELAY", 12)))
    max_delay = max(base, int(getattr(cfg, "RETRY_MAX_DELAY", 120)))
    jitter_max = max(0.0, float(getattr(cfg, "RETRY_JITTER_MAX", 0.0)))

    exp_delay = min(max_delay, base * (2 ** max(0, consecutive_failures - 1)))
    jitter = random.uniform(0.0, jitter_max)
    return exp_delay + jitter


def pick_existing_instance(compute: oci.core.ComputeClient) -> str | None:
    """Return an already-existing active instance id for configured display name."""
    response = oci.pagination.list_call_get_all_results(
        compute.list_instances,
        compartment_id=cfg.LAUNCH_OPTIONS["compartment_id"],
        display_name=cfg.LAUNCH_OPTIONS["display_name"],
    )
    active = [item for item in response.data if item.lifecycle_state not in TERMINAL_INSTANCE_STATES]
    if not active:
        return None

    if len(active) > 1:
        ids = ", ".join(item.id for item in active[:3])
        logger.warning("Found %s active instances with display_name=%s (%s)", len(active), cfg.LAUNCH_OPTIONS["display_name"], ids)

    # Use most recently created active instance.
    active.sort(key=lambda item: (item.time_created is not None, item.time_created), reverse=True)
    return active[0].id


def wait_for_running(compute: oci.core.ComputeClient, instance_id: str) -> None:
    """Poll instance state until RUNNING, terminal failure, or timeout."""
    timeout = max(60, int(getattr(cfg, "MAX_STATE_WAIT_SECONDS", 1800)))
    poll_delay = max(1, int(getattr(cfg, "STATE_CHECK_DELAY", 20)))
    started = time.monotonic()

    while True:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise TimeoutError(f"Timed out waiting for RUNNING after {timeout}s")

        try:
            instance = compute.get_instance(instance_id).data
        except ServiceError as exc:
            if is_retryable_service_error(exc):
                logger.warning("State check transient error (%s), retrying", exc)
                time.sleep(min(poll_delay, timeout))
                continue
            raise

        state = instance.lifecycle_state
        if state == "RUNNING":
            logger.info("Instance %s is RUNNING", instance_id)
            return

        if state in TERMINAL_INSTANCE_STATES:
            raise RuntimeError(f"Instance {instance_id} entered terminal state: {state}")

        logger.info("Instance %s state=%s, waiting %ss", instance_id, state, poll_delay)
        time.sleep(poll_delay)


def cycle_launch_requests() -> int:
    """Continuously try to create an instance until it reaches RUNNING."""
    validate_config()
    shapes = shape_priority()

    oci_config = oci.config.from_file(file_location=cfg.CONFIG_PATH, profile_name=cfg.CONFIG_PROFILE)
    compute = oci.core.ComputeClient(oci_config)

    attempt = 0
    consecutive_failures = 0

    while True:
        existing_id = pick_existing_instance(compute)
        if existing_id:
            logger.info("Reusing existing instance %s for display_name=%s", existing_id, cfg.LAUNCH_OPTIONS["display_name"])
            wait_for_running(compute, existing_id)
            return 0

        attempt += 1
        ad = cfg.AVAILABILITY_DOMAINS[(attempt - 1) % len(cfg.AVAILABILITY_DOMAINS)]
        shape_cfg = shapes[(attempt - 1) % len(shapes)]

        logger.info(
            "Attempt %s: launching in %s with %s OCPU / %s GB",
            attempt,
            ad,
            shape_cfg["ocpus"],
            shape_cfg["memory_in_gbs"],
        )

        launch_token = str(uuid.uuid4())
        try:
            response = compute.launch_instance(
                launch_instance_details=build_launch_details(ad, shape_cfg),
                opc_retry_token=launch_token,
            )
        except ServiceError as exc:
            if not is_retryable_service_error(exc):
                logger.error("Non-retryable OCI error: status=%s code=%s message=%s", exc.status, exc.code, exc.message)
                return 2

            consecutive_failures += 1
            delay = backoff_delay(consecutive_failures)
            logger.warning(
                "Retryable launch failure (status=%s code=%s): retrying in %.1fs",
                exc.status,
                exc.code,
                delay,
            )
            time.sleep(delay)
            continue
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected non-retryable client error: %s", exc)
            return 2

        instance_id = response.data.id
        logger.info("Launch request accepted, instance id=%s", instance_id)
        wait_for_running(compute, instance_id)
        return 0


if __name__ == "__main__":
    setup_logging()
    try:
        raise SystemExit(cycle_launch_requests())
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Fatal error: %s", exc)
        raise SystemExit(1) from exc
