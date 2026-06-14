from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# Force UTF-8 output on Windows (prevents charmap encode errors)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import analyze_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Splunk Agent-Readiness Engine")
    parser.add_argument("--app", required=True, help="Splunk app name to analyze")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config YAML")
    parser.add_argument("--app-path", help="Local Splunk app folder for offline scanning")
    parser.add_argument("--check-activity", action="store_true", help="Run saved searches to check live data activity")
    parser.add_argument("--limit", type=int, default=0, help="Limit to N saved searches")
    parser.add_argument("--offline-ai", action="store_true", help="Use deterministic local explanations instead of Gemini")
    args = parser.parse_args()

    print(f"\nScanning Splunk app: {args.app}")
    if args.app_path:
        print(f"Using local app path: {args.app_path}")

    result = analyze_app(
        app=args.app,
        config_path=args.config,
        app_path=args.app_path,
        check_activity_enabled=args.check_activity,
        limit=args.limit,
        offline_ai=args.offline_ai,
    )

    app_data = result["app_data"]
    scoring = result["scoring"]
    paths = result["paths"]

    print(
        "Found: "
        f"{len(app_data['saved_searches'])} saved searches, "
        f"{len(app_data['macros'])} macros, "
        f"{len(app_data['dashboards'])} dashboards"
    )
    print(f"Overall Score: {scoring['overall_score']}/100 - {scoring['grade']}")
    print(f"MCP Blockers: {scoring['mcp_blockers']}")
    print("\nOutputs:")
    print(f"  report.html: {paths['report']}")
    print(f"  agent_ready_patch.conf: {paths['conf_patch']}")
    print(f"  migration_plan.md: {paths['migration_plan']}")
    print(f"  raw_analysis.json: {paths['raw_analysis']}")


if __name__ == "__main__":
    main()

