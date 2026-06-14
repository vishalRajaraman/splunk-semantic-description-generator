from __future__ import annotations

from typing import Any


def check_activity(service: Any, saved_search: dict[str, Any], window_hours: int = 720) -> dict[str, Any]:
    """Run a bounded activity check for a saved search against live Splunk."""
    try:
        import splunklib.results as results
    except ImportError as exc:
        return {"active": False, "event_count": 0, "error": f"splunk-sdk unavailable: {exc}"}

    spl = saved_search.get("search", "")
    if spl.startswith("search "):
        spl = spl[7:]

    test_spl = f"search {spl} earliest=-{window_hours}h latest=now | stats count | head 1"

    try:
        job = service.jobs.create(test_spl, exec_mode="blocking", timeout=30)
        reader = results.JSONResultsReader(job.results(output_mode="json"))
        for result in reader:
            if isinstance(result, dict):
                count = int(result.get("count", 0))
                return {"active": count > 0, "event_count": count, "error": None}
        return {"active": False, "event_count": 0, "error": None}
    except Exception as exc:  # Splunk SDK raises several non-shared exception types.
        return {"active": False, "event_count": 0, "error": str(exc)}

