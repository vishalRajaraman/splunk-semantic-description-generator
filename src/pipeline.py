from __future__ import annotations

from typing import Any

from pathlib import Path

from src.ai.explainer import DEFAULT_GEMINI_MODEL, explain_batch, explain_macro, explain_saved_search, get_client
from src.ai.mcp_generator import generate_mcp_description
from src.config import load_yaml_config
from src.health.activity_checker import check_activity
from src.health.deprecated_checker import check_dashboard_deprecation, check_saved_search
from src.reporter.conf_patcher import generate_conf_patch
from src.reporter.html_reporter import generate_html_report, generate_migration_plan, write_raw_analysis
from src.scanner.app_scanner import connect_to_splunk, scan_app, scan_local_app
from src.scorer.readiness_scorer import score_app


def load_config(config_path: str) -> dict[str, Any]:
    return load_yaml_config(config_path)


def analyze_app(
    *,
    app: str,
    config_path: str = "config/config.yaml",
    app_path: str | None = None,
    check_activity_enabled: bool = False,
    limit: int = 0,
    offline_ai: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    output_dir = Path(config.get("analysis", {}).get("output_dir", "./output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    service = None
    if app_path:
        app_data = scan_local_app(app_path, app)
    else:
        service, _ = connect_to_splunk(config_path)
        app_data = scan_app(service, app, verify_ssl=config.get("splunk", {}).get("verify_ssl", False))

    searches = app_data["saved_searches"]
    if limit:
        searches = searches[:limit]
        app_data["saved_searches"] = searches

    for saved_search in searches:
        saved_search["health_issues"] = check_saved_search(saved_search)

    for dashboard in app_data["dashboards"]:
        dashboard["health_issues"] = check_dashboard_deprecation(dashboard)

    if check_activity_enabled and service is not None:
        window = config.get("analysis", {}).get("activity_window_hours", 720)
        activity_limit = config.get("analysis", {}).get("activity_limit", 15)
        for saved_search in searches[:activity_limit]:
            saved_search["activity"] = check_activity(service, saved_search, window)

    groq_cfg = config.get("groq", config.get("gemini", {}))  # fallback to gemini for backward compat
    # Support both api_keys (list) and api_key (single string)
    api_key = groq_cfg.get("api_keys") or groq_cfg.get("api_key")
    client = None if offline_ai else get_client(
        api_key,
        api_base=groq_cfg.get("api_base", "https://api.groq.com/openai/v1"),
    )
    model = groq_cfg.get("model", DEFAULT_GEMINI_MODEL)
    max_tokens = int(groq_cfg.get("max_tokens", 1000))
    batch_size = int(config.get("analysis", {}).get("batch_size", 5))

    explain_batch(client, searches, explain_saved_search, batch_size=batch_size, model=model, max_tokens=max_tokens)
    explain_batch(client, app_data["macros"], explain_macro, batch_size=batch_size, model=model, max_tokens=500)

    for saved_search in searches:
        saved_search["mcp_description"] = generate_mcp_description(
            client, saved_search, saved_search, model=model, max_tokens=500,
        )

    # Also generate MCP descriptions for macros
    for macro in app_data["macros"]:
        macro["mcp_description"] = generate_mcp_description(
            client, macro, macro, model=model, max_tokens=400,
        )

    scoring = score_app(app_data)

    paths = {
        "report": generate_html_report(app_data, scoring, str(output_dir / "report.html")),
        "migration_plan": generate_migration_plan(app_data, scoring, str(output_dir / "migration_plan.md")),
        "raw_analysis": write_raw_analysis(app_data, scoring, str(output_dir / "raw_analysis.json")),
        "conf_patch": str(output_dir / "agent_ready_patch.conf"),
    }
    Path(paths["conf_patch"]).write_text(generate_conf_patch(searches), encoding="utf-8")

    return {"app_data": app_data, "scoring": scoring, "paths": paths}
