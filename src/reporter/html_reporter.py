from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:  # pragma: no cover - fallback for dependency-light offline mode.
    Environment = None  # type: ignore[assignment]
    FileSystemLoader = None  # type: ignore[assignment]
    select_autoescape = None  # type: ignore[assignment]

try:
    from markupsafe import Markup  # Jinja2 3.x moved Markup here
except ImportError:
    try:
        from jinja2 import Markup  # type: ignore[no-redef]  # Jinja2 2.x
    except ImportError:
        Markup = None  # type: ignore[assignment,misc]


def generate_html_report(app_data: dict[str, Any], scoring: dict[str, Any], output_path: str = "output/report.html") -> str:
    searches = app_data.get("saved_searches", [])
    critical   = [s for s in searches if s.get("score", 100) < 20]
    needs_work = [s for s in searches if 20 <= s.get("score", 100) < 60]
    good       = [s for s in searches if s.get("score", 0) >= 60]

    output_dir = Path(output_path).parent

    # Embed file contents inline so download buttons work without a server
    def _read(filename: str) -> str:
        p = output_dir / filename
        try:
            return p.read_text(encoding="utf-8") if p.exists() else ""
        except Exception:
            return ""

    file_data = {
        "agent_ready_patch.conf": _read("agent_ready_patch.conf"),
        "migration_plan.md":      _read("migration_plan.md"),
        "raw_analysis.json":      _read("raw_analysis.json"),
    }

    if Environment is not None:
        template_dir = Path(__file__).parent / "templates"
        # autoescape=False because we manually sanitize the one risky value
        # (the embedded JSON blob). Enabling autoescape encodes JSON quotes as
        # &quot;, which breaks the FILE_DATA JS assignment in the browser.
        env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
        )
        template = env.get_template("report.html")
        html = template.render(
            app_name=app_data.get("app_name"),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            scoring=scoring,
            searches=searches,
            critical=critical,
            needs_work=needs_work,
            good=good,
            dashboards=app_data.get("dashboards", []),
            macros=app_data.get("macros", []),
            total_objects=len(searches) + len(app_data.get("macros", [])),
            # Sanitize: </script> inside JSON would close the <script> tag early.
            # autoescape is disabled on this env, so plain str is safe here.
            file_data_json=json.dumps(file_data).replace("</", "<\/"),
        )
    else:
        html = _fallback_html(app_data, scoring, searches, good)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return str(path)


def _fallback_html(
    app_data: dict[str, Any],
    scoring: dict[str, Any],
    searches: list[dict[str, Any]],
    good: list[dict[str, Any]],
) -> str:
    rows = []
    for search in searches:
        rows.append(
            "<tr>"
            f"<td>{_escape(str(search.get('name', '')))}</td>"
            f"<td>{search.get('score', 0)}/100</td>"
            f"<td>{_escape(str(search.get('plain_english', 'Not analyzed')))}</td>"
            f"<td>{_escape(str(search.get('mcp_description', 'Not generated')))}</td>"
            f"<td>{len(search.get('health_issues', []))}</td>"
            "</tr>"
        )
    classic_count = len([d for d in app_data.get("dashboards", []) if d.get("version") in ("simple_xml","simple_xml_form")])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agent-Readiness Report - {_escape(str(app_data.get('app_name', 'Splunk app')))}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0b1020; color: #e5edf7; padding: 32px; }}
    main {{ max-width: 1100px; margin: 0 auto; }}
    section {{ background: #171f32; border: 1px solid #334155; border-radius: 8px; padding: 24px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-top: 1px solid #334155; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ color: #9fb0c3; }}
    .score {{ font-size: 56px; font-weight: 900; color: {scoring.get('grade_color', '#e5edf7')}; }}
  </style>
</head>
<body>
<main>
  <section>
    <div class="score">{scoring.get('overall_score', 0)}/100</div>
    <h1>{_escape(str(app_data.get('app_name', 'Splunk app')))}</h1>
    <p>{_escape(str(scoring.get('grade', 'Not scored')))}. {scoring.get('mcp_blockers', 0)} MCP blocker(s), {classic_count} classic dashboard(s), {len(good)} ready object(s).</p>
  </section>
  <section>
    <h2>Saved Searches</h2>
    <table><thead><tr><th>Name</th><th>Score</th><th>Plain English</th><th>MCP Description</th><th>Issues</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
  </section>
</main>
</body>
</html>"""


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def generate_migration_plan(app_data: dict[str, Any], scoring: dict[str, Any], output_path: str = "output/migration_plan.md") -> str:
    lines = [
        f"# Migration Plan: {app_data.get('app_name')}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        f"## Overall Agent-Readiness Score: {scoring['overall_score']}/100 - {scoring['grade']}",
        "",
        "## Priority Actions",
        "",
        "### Critical: Fix Before MCP Use",
    ]

    searches = app_data.get("saved_searches", [])
    critical = [search for search in searches if search.get("score", 100) < 20]
    if not critical:
        lines.append("- No critical saved searches found.")
    for search in critical:
        lines.append(f"- **{search['name']}** - Score: {search.get('score')}/100")
        for issue in search.get("health_issues", []):
            lines.append(f"  - {issue.get('severity')}: {issue.get('message')}")

    lines += [
        "",
        "### Add MCP Descriptions",
        "",
        f"Apply `agent_ready_patch.conf` to add descriptions to {scoring.get('mcp_blockers', 0)} blocker object(s).",
        "",
        "### Deprecated Dashboard Migration",
    ]

    classic_dashboards = [d for d in app_data.get("dashboards", []) if d.get("version") in ("simple_xml", "simple_xml_form")]
    if not classic_dashboards:
        lines.append("- No classic XML dashboards found.")
    for dashboard in classic_dashboards:
        effort = dashboard.get("estimated_effort") or _dashboard_effort_from_issues(dashboard)
        lines.append(f"- **{dashboard['label']}** - Migrate to Dashboard Studio (estimated: {effort})")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def write_raw_analysis(app_data: dict[str, Any], scoring: dict[str, Any], output_path: str = "output/raw_analysis.json") -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"app_data": app_data, "scoring": scoring}, indent=2), encoding="utf-8")
    return str(path)


def _dashboard_effort_from_issues(dashboard: dict[str, Any]) -> str:
    for issue in dashboard.get("health_issues", []):
        if issue.get("effort_hours"):
            return str(issue["effort_hours"])
    return "unknown"
