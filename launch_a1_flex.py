"""Retry OCI A1.Flex launch requests until an instance is RUNNING."""
from __future__ import annotations

import logging
import random
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import oci
from oci.exceptions import RequestException, ServiceError

import launch_config as cfg

TERMINAL_INSTANCE_STATES = {"TERMINATED", "STOPPED", "STOPPING", "FAULTY"}
RETRYABLE_HTTP_STATUSES = {409, 429, 500, 502, 503, 504}


logger = logging.getLogger("a1_flex_hunter")


class TerminalUI:
    """Single-screen terminal dashboard to avoid log scrolling."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = bool(enabled and sys.stdout.isatty())
        self._curses = None
        self._screen = None
        self._last_render = 0.0
        self._start_time = time.monotonic()
        self._events: deque[str] = deque(maxlen=max(3, int(getattr(cfg, "TUI_EVENT_LINES", 8))))
        self._state: dict[str, str] = {
            "phase": "init",
            "attempt": "0",
            "ad": "-",
            "shape": "-",
            "next_delay": "-",
            "retries": "0",
            "throttles": "0",
            "network_errors": "0",
            "capacity_skips": "0",
            "instance_id": "-",
            "last_status": "-",
            "last_error": "-",
        }

        if not self.enabled:
            return

        try:
            import curses

            self._curses = curses
            self._screen = curses.initscr()
            curses.noecho()
            curses.cbreak()
            self._screen.nodelay(True)
            self._screen.keypad(True)
        except Exception:
            self.enabled = False
            self._curses = None
            self._screen = None

    def set_state(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            self._state[key] = str(value)
        self.render()

    def add_event(self, level: str, message: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._events.appendleft(f"{ts} [{level}] {message}")
        self.render()

    def _elapsed(self) -> str:
        seconds = int(time.monotonic() - self._start_time)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _fit(text: str, width: int) -> str:
        if width <= 0:
            return ""
        if len(text) <= width:
            return text
        if width == 1:
            return text[:1]
        return text[: width - 1] + "…"

    def render(self, force: bool = False) -> None:
        if not self.enabled or self._screen is None:
            return

        now = time.monotonic()
        if not force and now - self._last_render < 0.1:
            return
        self._last_render = now

        try:
            height, width = self._screen.getmaxyx()
            content_width = max(10, width - 1)

            lines = [
                "OCI A1 Flex Hunter",
                f"Elapsed: {self._elapsed()} | Phase: {self._state['phase']}",
                f"Attempt: {self._state['attempt']} | AD: {self._state['ad']}",
                f"Shape: {self._state['shape']} | Next delay: {self._state['next_delay']}",
                (
                    "Retries: {retries} | Throttles: {throttles} | Network: {network_errors} | "
                    "Capacity skips: {capacity_skips}"
                ).format(**self._state),
                f"Instance: {self._state['instance_id']}",
                f"Last status: {self._state['last_status']}",
                f"Last error: {self._state['last_error']}",
                "",
                "Recent events:",
            ]
            lines.extend(list(self._events))

            self._screen.erase()
            for row, line in enumerate(lines[:height]):
                self._screen.addnstr(row, 0, self._fit(line, content_width), content_width)
            self._screen.refresh()
        except Exception:
            # If terminal rendering fails, disable TUI and continue in logging mode.
            self.enabled = False

    def close(self) -> None:
        if not self.enabled or self._screen is None or self._curses is None:
            return
        try:
            self._curses.nocbreak()
            self._screen.keypad(False)
            self._curses.echo()
            self._curses.endwin()
        except Exception:
            pass


ACTIVE_UI: TerminalUI | None = None


def _format_message(message: str, args: tuple[Any, ...]) -> str:
    if not args:
        return str(message)
    try:
        return message % args
    except Exception:
        rendered_args = " ".join(str(arg) for arg in args)
        return f"{message} {rendered_args}".strip()


def _ui_emit(level: str, message: str) -> None:
    if ACTIVE_UI and ACTIVE_UI.enabled:
        ACTIVE_UI.add_event(level, message)


def log_info(message: str, *args: Any) -> None:
    logger.info(message, *args)
    _ui_emit("INFO", _format_message(message, args))


def log_warning(message: str, *args: Any) -> None:
    logger.warning(message, *args)
    _ui_emit("WARN", _format_message(message, args))


def log_error(message: str, *args: Any) -> None:
    logger.error(message, *args)
    _ui_emit("ERROR", _format_message(message, args))


def log_exception(message: str, *args: Any) -> None:
    logger.exception(message, *args)
    _ui_emit("ERROR", _format_message(message, args))


def setup_logging(console_output: bool) -> None:
    """Configure logging handlers."""
    level_name = str(getattr(cfg, "LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    handlers: list[logging.Handler] = []
    if console_output:
        handlers.append(logging.StreamHandler())

    log_file = str(getattr(cfg, "LOG_FILE", "")).strip()
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path))

    if not handlers:
        handlers.append(logging.NullHandler())

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


def is_retryable_request_exception(_exc: RequestException) -> bool:
    """Treat transport-level SDK failures as retryable."""
    return True


def is_throttle_service_error(exc: ServiceError) -> bool:
    """Detect API throttling responses."""
    if exc.status == 429:
        return True

    code = str(getattr(exc, "code", "") or "").lower()
    message = str(getattr(exc, "message", "") or "").lower()
    return "throttl" in code or "throttl" in message or "too many requests" in message


class RequestPacer:
    """
    Adaptive request pacing:
    - Reduce delays while there is no throttling.
    - Increase delays when throttled, then keep cooldown before speeding up again.
    """

    def __init__(self) -> None:
        self.start_delay = max(0.1, float(getattr(cfg, "REQUEST_PACE_START_DELAY", 8.0)))
        self.min_delay = max(0.1, float(getattr(cfg, "REQUEST_PACE_MIN_DELAY", 0.8)))
        self.max_delay = max(self.min_delay, float(getattr(cfg, "REQUEST_PACE_MAX_DELAY", 20.0)))
        self.decrease_factor = float(getattr(cfg, "REQUEST_PACE_DECREASE_FACTOR", 0.75))
        self.increase_factor = float(getattr(cfg, "REQUEST_PACE_INCREASE_FACTOR", 1.25))
        self.cooldown_seconds = max(0.0, float(getattr(cfg, "THROTTLE_COOLDOWN_SECONDS", 45.0)))
        self.jitter_max = max(0.0, float(getattr(cfg, "REQUEST_PACE_JITTER_MAX", 0.3)))
        self.current_delay = min(self.max_delay, max(self.min_delay, self.start_delay))
        self.cooldown_until = 0.0

    def _bounded(self, value: float) -> float:
        return min(self.max_delay, max(self.min_delay, value))

    def next_delay(self, throttled: bool) -> float:
        """Return next sleep duration based on observed response type."""
        now = time.monotonic()
        if throttled:
            self.current_delay = self._bounded(self.current_delay * self.increase_factor)
            self.cooldown_until = now + self.cooldown_seconds
        elif now >= self.cooldown_until:
            self.current_delay = self._bounded(self.current_delay * self.decrease_factor)

        return self.current_delay + random.uniform(0.0, self.jitter_max)


def pick_existing_instance(compute: oci.core.ComputeClient) -> str | None:
    """Return an already-existing active instance id for configured display name."""
    try:
        response = oci.pagination.list_call_get_all_results(
            compute.list_instances,
            compartment_id=cfg.LAUNCH_OPTIONS["compartment_id"],
            display_name=cfg.LAUNCH_OPTIONS["display_name"],
        )
    except ServiceError as exc:
        if is_retryable_service_error(exc):
            log_warning(
                "Existing-instance probe transient OCI error: status=%s code=%s message=%s",
                exc.status,
                exc.code,
                exc.message,
            )
            return None
        raise
    except RequestException as exc:
        if is_retryable_request_exception(exc):
            log_warning("Existing-instance probe transient network error: %s", exc)
            return None
        raise

    active = [item for item in response.data if item.lifecycle_state not in TERMINAL_INSTANCE_STATES]
    if not active:
        return None

    if len(active) > 1:
        ids = ", ".join(item.id for item in active[:3])
        log_warning("Found %s active instances with display_name=%s (%s)", len(active), cfg.LAUNCH_OPTIONS["display_name"], ids)

    # Use most recently created active instance.
    active.sort(key=lambda item: (item.time_created is not None, item.time_created), reverse=True)
    return active[0].id


def capacity_report_has_room(
    compute: oci.core.ComputeClient, ad: str, shape_cfg: dict[str, Any]
) -> bool | None:
    """
    Probe AD capacity before launch.

    Returns:
      - True: capacity appears available
      - False: no capacity / not supported for this shape
      - None: probe failed transiently; caller may still try launch
    """
    if not bool(getattr(cfg, "USE_CAPACITY_REPORT", True)):
        return None

    details = oci.core.models.CreateComputeCapacityReportDetails(
        compartment_id=cfg.LAUNCH_OPTIONS["compartment_id"],
        availability_domain=ad,
        shape_availabilities=[
            oci.core.models.CreateCapacityReportShapeAvailabilityDetails(
                instance_shape=cfg.LAUNCH_OPTIONS["shape"],
                instance_shape_config=oci.core.models.CapacityReportInstanceShapeConfig(
                    ocpus=shape_cfg["ocpus"],
                    memory_in_gbs=shape_cfg["memory_in_gbs"],
                ),
            )
        ],
    )

    try:
        response = compute.create_compute_capacity_report(details)
    except ServiceError as exc:
        if is_retryable_service_error(exc):
            log_warning(
                "Capacity report transient OCI error: status=%s code=%s message=%s",
                exc.status,
                exc.code,
                exc.message,
            )
            return None
        raise
    except RequestException as exc:
        if is_retryable_request_exception(exc):
            log_warning("Capacity report transient network error: %s", exc)
            return None
        raise

    entries = response.data.shape_availabilities or []
    if not entries:
        return None

    entry = entries[0]
    status = str(entry.availability_status or "").upper()
    available_count = int(entry.available_count or 0)
    log_info(
        "Capacity report %s %s/%s: status=%s available=%s",
        ad,
        shape_cfg["ocpus"],
        shape_cfg["memory_in_gbs"],
        status or "UNKNOWN",
        available_count,
    )

    if ACTIVE_UI and ACTIVE_UI.enabled:
        ACTIVE_UI.set_state(last_status=f"capacity={status or 'UNKNOWN'} available={available_count}")

    if status == "AVAILABLE" and available_count > 0:
        return True
    if status in {"OUT_OF_HOST_CAPACITY", "HARDWARE_NOT_SUPPORTED"} or available_count <= 0:
        return False
    return None


def wait_for_running(compute: oci.core.ComputeClient, instance_id: str) -> None:
    """Poll instance state until RUNNING, terminal failure, or timeout."""
    timeout = max(60, int(getattr(cfg, "MAX_STATE_WAIT_SECONDS", 1800)))
    poll_delay = max(1, int(getattr(cfg, "STATE_CHECK_DELAY", 20)))
    started = time.monotonic()

    if ACTIVE_UI and ACTIVE_UI.enabled:
        ACTIVE_UI.set_state(phase="waiting_running", instance_id=instance_id)

    while True:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise TimeoutError(f"Timed out waiting for RUNNING after {timeout}s")

        try:
            instance = compute.get_instance(instance_id).data
        except ServiceError as exc:
            if is_retryable_service_error(exc):
                log_warning("State check transient error (%s), retrying", exc)
                if ACTIVE_UI and ACTIVE_UI.enabled:
                    ACTIVE_UI.set_state(last_status="state-check transient error", next_delay=f"{poll_delay}s")
                time.sleep(min(poll_delay, timeout))
                continue
            raise
        except RequestException as exc:
            if is_retryable_request_exception(exc):
                log_warning("State check transient network error (%s), retrying", exc)
                if ACTIVE_UI and ACTIVE_UI.enabled:
                    ACTIVE_UI.set_state(last_status="state-check network error", next_delay=f"{poll_delay}s")
                time.sleep(min(poll_delay, timeout))
                continue
            raise

        state = instance.lifecycle_state
        if state == "RUNNING":
            log_info("Instance %s is RUNNING", instance_id)
            if ACTIVE_UI and ACTIVE_UI.enabled:
                ACTIVE_UI.set_state(phase="running", last_status="RUNNING", next_delay="-")
            return

        if state in TERMINAL_INSTANCE_STATES:
            raise RuntimeError(f"Instance {instance_id} entered terminal state: {state}")

        log_info("Instance %s state=%s, waiting %ss", instance_id, state, poll_delay)
        if ACTIVE_UI and ACTIVE_UI.enabled:
            ACTIVE_UI.set_state(last_status=f"state={state}", next_delay=f"{poll_delay}s")
        time.sleep(poll_delay)


def cycle_launch_requests() -> int:
    """Continuously try to create an instance until it reaches RUNNING."""
    validate_config()
    shapes = shape_priority()

    oci_config = oci.config.from_file(file_location=cfg.CONFIG_PATH, profile_name=cfg.CONFIG_PROFILE)
    compute = oci.core.ComputeClient(oci_config)
    pacer = RequestPacer()

    attempt = 0
    retries = 0
    throttle_hits = 0
    network_errors = 0
    capacity_skips = 0

    if ACTIVE_UI and ACTIVE_UI.enabled:
        ACTIVE_UI.set_state(phase="hunting", next_delay=f"{pacer.current_delay:.1f}s")

    while True:
        existing_id = pick_existing_instance(compute)
        if existing_id:
            log_info("Reusing existing instance %s for display_name=%s", existing_id, cfg.LAUNCH_OPTIONS["display_name"])
            if ACTIVE_UI and ACTIVE_UI.enabled:
                ACTIVE_UI.set_state(phase="reuse_existing", instance_id=existing_id)
            wait_for_running(compute, existing_id)
            return 0

        attempt += 1
        ad = cfg.AVAILABILITY_DOMAINS[(attempt - 1) % len(cfg.AVAILABILITY_DOMAINS)]
        shape_cfg = shapes[(attempt - 1) % len(shapes)]

        if ACTIVE_UI and ACTIVE_UI.enabled:
            ACTIVE_UI.set_state(
                phase="launch_attempt",
                attempt=attempt,
                ad=ad,
                shape=f"{shape_cfg['ocpus']} OCPU / {shape_cfg['memory_in_gbs']} GB",
                retries=retries,
                throttles=throttle_hits,
                network_errors=network_errors,
                capacity_skips=capacity_skips,
            )

        log_info(
            "Attempt %s: launching in %s with %s OCPU / %s GB",
            attempt,
            ad,
            shape_cfg["ocpus"],
            shape_cfg["memory_in_gbs"],
        )

        capacity_ok = capacity_report_has_room(compute, ad, shape_cfg)
        if capacity_ok is False:
            capacity_skips += 1
            delay = pacer.next_delay(throttled=False)
            log_info("Capacity report says no room yet; next attempt in %.1fs", delay)
            if ACTIVE_UI and ACTIVE_UI.enabled:
                ACTIVE_UI.set_state(
                    phase="capacity_wait",
                    capacity_skips=capacity_skips,
                    next_delay=f"{delay:.1f}s",
                    retries=retries,
                    throttles=throttle_hits,
                    network_errors=network_errors,
                )
            time.sleep(delay)
            continue

        launch_token = str(uuid.uuid4())
        try:
            response = compute.launch_instance(
                launch_instance_details=build_launch_details(ad, shape_cfg),
                opc_retry_token=launch_token,
            )
        except ServiceError as exc:
            if not is_retryable_service_error(exc):
                log_error("Non-retryable OCI error: status=%s code=%s message=%s", exc.status, exc.code, exc.message)
                if ACTIVE_UI and ACTIVE_UI.enabled:
                    ACTIVE_UI.set_state(phase="failed", last_error=f"{exc.status} {exc.code}: {exc.message}")
                return 2

            retries += 1
            throttled = is_throttle_service_error(exc)
            if throttled:
                throttle_hits += 1
            delay = pacer.next_delay(throttled=throttled)

            if throttled:
                log_warning(
                    "Throttled by OCI (status=%s code=%s message=%s): backing off to %.1fs",
                    exc.status,
                    exc.code,
                    exc.message,
                    delay,
                )
            else:
                log_warning(
                    "Retryable launch failure (status=%s code=%s message=%s): next attempt in %.1fs",
                    exc.status,
                    exc.code,
                    exc.message,
                    delay,
                )

            if ACTIVE_UI and ACTIVE_UI.enabled:
                ACTIVE_UI.set_state(
                    phase="retry_wait",
                    retries=retries,
                    throttles=throttle_hits,
                    network_errors=network_errors,
                    next_delay=f"{delay:.1f}s",
                    last_error=f"{exc.status} {exc.code}",
                )
            time.sleep(delay)
            continue
        except RequestException as exc:
            if not is_retryable_request_exception(exc):
                log_error("Non-retryable network error: %s", exc)
                if ACTIVE_UI and ACTIVE_UI.enabled:
                    ACTIVE_UI.set_state(phase="failed", last_error=str(exc))
                return 2

            retries += 1
            network_errors += 1
            delay = pacer.next_delay(throttled=False)
            log_warning("Retryable network error during launch: next attempt in %.1fs (%s)", delay, exc)
            if ACTIVE_UI and ACTIVE_UI.enabled:
                ACTIVE_UI.set_state(
                    phase="retry_wait",
                    retries=retries,
                    network_errors=network_errors,
                    throttles=throttle_hits,
                    next_delay=f"{delay:.1f}s",
                    last_error="network error",
                )
            time.sleep(delay)
            continue
        except Exception as exc:  # pylint: disable=broad-except
            log_exception("Unexpected non-retryable client error: %s", exc)
            if ACTIVE_UI and ACTIVE_UI.enabled:
                ACTIVE_UI.set_state(phase="failed", last_error=str(exc))
            return 2

        instance_id = response.data.id
        log_info("Launch request accepted, instance id=%s", instance_id)
        if ACTIVE_UI and ACTIVE_UI.enabled:
            ACTIVE_UI.set_state(phase="launch_accepted", instance_id=instance_id, last_status="launch accepted")
        wait_for_running(compute, instance_id)
        return 0


if __name__ == "__main__":
    ACTIVE_UI = TerminalUI(enabled=bool(getattr(cfg, "ENABLE_TUI", True)))
    setup_logging(console_output=not ACTIVE_UI.enabled)

    if ACTIVE_UI.enabled:
        ACTIVE_UI.set_state(phase="starting")
        ACTIVE_UI.render(force=True)

    try:
        raise SystemExit(cycle_launch_requests())
    except Exception as exc:  # pylint: disable=broad-except
        log_exception("Fatal error: %s", exc)
        if ACTIVE_UI and ACTIVE_UI.enabled:
            ACTIVE_UI.set_state(phase="failed", last_error=str(exc))
            ACTIVE_UI.render(force=True)
        raise SystemExit(1) from exc
    finally:
        if ACTIVE_UI:
            ACTIVE_UI.close()
