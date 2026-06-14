from __future__ import annotations

import re
from typing import Any


DEPRECATED_COMMANDS = [
    ("| bucket_sweep", "Deprecated in Splunk 9.x; use bin instead."),
    ("createrss", "RSS output is deprecated; remove or migrate this output path."),
    ("| findtypes", "Removed in Splunk 9; use fieldsummary instead."),
    ("earlybreak=true", "The earlybreak parameter was removed in Splunk 8.2."),
    ("| convert num(", "Old convert syntax; use eval tonumber() instead."),
]

PERFORMANCE_ISSUES = [
    (r"index=\*", "CRITICAL: index=* searches all indexes and can be very slow."),
    (r"^\s*\*", "Wildcard-only search; add index, sourcetype, and time constraints."),
    (r"\|\s*rex\s+mode=sed", "rex mode=sed is slow; prefer eval replace() when possible."),
    (r"search\s+\*", "search * without constraints; add index and sourcetype filters."),
]

HARDCODED_PATTERNS = [
    (r"host=\"[a-zA-Z0-9-]+-(?:prod|staging|dev)-\d+\"", "Hardcoded hostname; use host tags or a lookup."),
    (r"source=\"/var/log/[^\"*]+[^\"]\"", "Hardcoded log path; prefer sourcetype or a lookup."),
    (r"ip=\"\d{1,3}(?:\.\d{1,3}){3}\"", "Hardcoded IP address; use a lookup table instead."),
]


def check_dashboard_deprecation(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if dashboard.get("version") == "classic_1.0":
        issues.append(
            {
                "severity": "WARNING",
                "type": "deprecated_format",
                "message": "Classic Dashboard XML is deprecated in recent Splunk versions; migrate to Dashboard Studio.",
                "effort_hours": estimate_migration_effort(dashboard.get("xml", "")),
            }
        )
    return issues


def estimate_migration_effort(xml_str: str) -> str:
    panel_count = (
        xml_str.count("<panel")
        + xml_str.count("<chart")
        + xml_str.count("<table")
        + xml_str.count("<single")
    )
    if panel_count <= 3:
        return "0.5-1 hour"
    if panel_count <= 8:
        return "2-4 hours"
    return "5-8 hours"


def check_saved_search(saved_search: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    spl = saved_search.get("search", "")

    for pattern, message in DEPRECATED_COMMANDS:
        if pattern in spl:
            issues.append(
                {
                    "severity": "ERROR",
                    "type": "deprecated_command",
                    "message": message,
                    "matched": pattern,
                }
            )

    for pattern, message in PERFORMANCE_ISSUES:
        if re.search(pattern, spl):
            issues.append(
                {
                    "severity": "WARNING",
                    "type": "performance",
                    "message": message,
                    "matched": pattern,
                }
            )

    for pattern, message in HARDCODED_PATTERNS:
        if re.search(pattern, spl):
            issues.append(
                {
                    "severity": "WARNING",
                    "type": "hardcoded_value",
                    "message": message,
                    "matched": pattern,
                }
            )

    # NOTE: We intentionally do NOT flag missing descriptions here.
    # The pipeline generates mcp_description via Gemini/heuristic AFTER this checker runs.
    # MCP_BLOCKER status is determined by readiness_scorer.py based on the FINAL description.

    return issues

