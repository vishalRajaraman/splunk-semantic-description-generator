from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - exercised only in minimal runtimes.
    requests = None  # type: ignore[assignment]

try:
    import urllib3
except ImportError:  # pragma: no cover
    urllib3 = None  # type: ignore[assignment]

from src.config import load_yaml_config
from .conf_parser import merge_conf_dirs
from .dashboard_parser import extract_dashboard_version, parse_dashboard_dir

if urllib3 is not None:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def connect_to_splunk(config_path: str = "config/config.yaml"):
    """Create a Splunk SDK service from config."""
    try:
        import splunklib.client as client
    except ImportError as exc:
        raise RuntimeError("Install splunk-sdk to connect to Splunk.") from exc

    config = load_yaml_config(config_path)

    cfg = config["splunk"]
    service = client.connect(
        host=cfg["host"],
        port=cfg["port"],
        username=cfg["username"],
        password=cfg["password"],
        scheme=cfg.get("scheme", "https"),
    )
    # Attach raw credentials so _request_collection can use basic auth
    service._raw_username = cfg["username"]
    service._raw_password = cfg["password"]
    return service, config


def _request_collection(service: Any, app_name: str, endpoint: str, verify_ssl: bool) -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("Install requests to scan live Splunk REST collections.")
    base = f"{getattr(service, 'scheme', 'https')}://{service.host}:{service.port}"
    # Use basic auth — more reliable than SDK session tokens across all Splunk versions
    auth = (
        getattr(service, '_raw_username', None) or service.username,
        getattr(service, '_raw_password', None) or '',
    )
    response = requests.get(
        f"{base}/servicesNS/-/{app_name}/{endpoint}",
        auth=auth,
        params={"output_mode": "json", "count": 0},
        timeout=30,
        verify=verify_ssl,
    )
    response.raise_for_status()
    return response.json().get("entry", [])


def scan_app(service: Any, app_name: str, *, verify_ssl: bool = False) -> dict[str, Any]:
    """Scan knowledge objects from a live Splunk service via REST API."""
    app_data: dict[str, Any] = _empty_app_data(app_name)

    # ── Saved Searches (via REST — SDK .get() triggers HTTP 404 on some builds) ──
    for entry in _safe_collection(service, app_name, "saved/searches", verify_ssl):
        content = entry.get("content", {})
        app_data["saved_searches"].append(
            {
                "name": entry.get("name", ""),
                "search": content.get("search", ""),
                "description": content.get("description", ""),
                "cron_schedule": content.get("cron_schedule", ""),
                "is_scheduled": content.get("is_scheduled", "0"),
                "next_scheduled_time": content.get("next_scheduled_time", ""),
                "dispatch_earliest_time": content.get("dispatch.earliest_time", ""),
                "dispatch_latest_time": content.get("dispatch.latest_time", ""),
                "alert_type": content.get("alert_type", ""),
            }
        )

    for entry in _safe_collection(service, app_name, "admin/macros", verify_ssl):
        app_data["macros"].append(
            {
                "name": entry.get("name", ""),
                "definition": entry.get("content", {}).get("definition", ""),
                "description": entry.get("content", {}).get("description", ""),
                "args": entry.get("content", {}).get("args", ""),
            }
        )

    for entry in _safe_collection(service, app_name, "admin/transforms-extract", verify_ssl):
        app_data["field_extractions"].append(
            {
                "name": entry.get("name", ""),
                "regex": entry.get("content", {}).get("REGEX", ""),
                "source_key": entry.get("content", {}).get("SOURCE_KEY", ""),
                "description": entry.get("content", {}).get("description", ""),
            }
        )

    for entry in _safe_collection(service, app_name, "saved/eventtypes", verify_ssl):
        app_data["event_types"].append(
            {
                "name": entry.get("name", ""),
                "search": entry.get("content", {}).get("search", ""),
                "description": entry.get("content", {}).get("description", ""),
            }
        )

    for entry in _safe_collection(service, app_name, "data/ui/views", verify_ssl):
        xml = entry.get("content", {}).get("eai:data", "")
        app_data["dashboards"].append(
            {
                "name": entry.get("name", ""),
                "label": entry.get("content", {}).get("label", entry.get("name", "")),
                "xml": xml,
                "version": extract_dashboard_version(xml),
            }
        )

    for entry in _safe_collection(service, app_name, "data/transforms/lookups", verify_ssl):
        app_data["lookups"].append(
            {
                "name": entry.get("name", ""),
                "filename": entry.get("content", {}).get("filename", ""),
                "description": entry.get("content", {}).get("description", ""),
            }
        )

    return app_data



def scan_local_app(app_path: str | Path, app_name: str | None = None) -> dict[str, Any]:
    """Scan a Splunk app folder from disk for offline tests and demos."""
    base = Path(app_path)
    if not base.exists():
        raise FileNotFoundError(f"App path does not exist: {base}")

    app_data = _empty_app_data(app_name or base.name)

    saved = merge_conf_dirs(base, "savedsearches.conf")
    for name, values in saved.items():
        app_data["saved_searches"].append(
            {
                "name": name,
                "search": values.get("search", ""),
                "description": values.get("description", ""),
                "cron_schedule": values.get("cron_schedule", ""),
                "is_scheduled": values.get("is_scheduled", "0"),
                "dispatch_earliest_time": values.get("dispatch.earliest_time", ""),
                "dispatch_latest_time": values.get("dispatch.latest_time", ""),
                "alert_type": values.get("alert_type", ""),
            }
        )

    macros = merge_conf_dirs(base, "macros.conf")
    for name, values in macros.items():
        app_data["macros"].append(
            {
                "name": name,
                "definition": values.get("definition", ""),
                "description": values.get("description", ""),
                "args": values.get("args", ""),
            }
        )

    event_types = merge_conf_dirs(base, "eventtypes.conf")
    for name, values in event_types.items():
        app_data["event_types"].append(
            {
                "name": name,
                "search": values.get("search", ""),
                "description": values.get("description", ""),
            }
        )

    transforms = merge_conf_dirs(base, "transforms.conf")
    for name, values in transforms.items():
        if "REGEX" in values:
            app_data["field_extractions"].append(
                {
                    "name": name,
                    "regex": values.get("REGEX", ""),
                    "source_key": values.get("SOURCE_KEY", ""),
                    "description": values.get("description", ""),
                }
            )
        if "filename" in values or "external_cmd" in values:
            app_data["lookups"].append(
                {
                    "name": name,
                    "filename": values.get("filename", ""),
                    "description": values.get("description", ""),
                }
            )

    app_data["dashboards"] = parse_dashboard_dir(base)
    return app_data


def _safe_collection(service: Any, app_name: str, endpoint: str, verify_ssl: bool) -> list[dict[str, Any]]:
    try:
        return _request_collection(service, app_name, endpoint, verify_ssl)
    except Exception as exc:
        print(f"  [warn] {endpoint}: {exc}")
        return []


def _empty_app_data(app_name: str) -> dict[str, Any]:
    return {
        "app_name": app_name,
        "saved_searches": [],
        "macros": [],
        "field_extractions": [],
        "event_types": [],
        "dashboards": [],
        "lookups": [],
    }
