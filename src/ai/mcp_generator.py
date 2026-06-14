from __future__ import annotations

import re
from typing import Any

from .explainer import DEFAULT_GEMINI_MODEL
from .prompts import build_mcp_prompt


def generate_mcp_description(
    client: Any,
    saved_search: dict[str, Any],
    explanation: dict[str, Any] | None = None,
    *,
    model: str = DEFAULT_GEMINI_MODEL,
    max_tokens: int = 500,
) -> str:
    explanation = explanation or saved_search
    if client is None:
        return heuristic_mcp_description(saved_search, explanation)

    try:
        response_text = client.generate_text(
            build_mcp_prompt(saved_search, explanation),
            model=model,
            max_tokens=max_tokens,
        )
        text = response_text.strip().strip('"').strip("'")
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return text
    except Exception as exc:
        print(f"  [warn] Gemini MCP error for '{saved_search.get('name')}': {exc} — using heuristic")
        return heuristic_mcp_description(saved_search, explanation)


def heuristic_mcp_description(
    saved_search: dict[str, Any],
    explanation: dict[str, Any] | None = None,
) -> str:
    """
    Build a proper 3-sentence MCP description from structured explanation fields.
    Never concatenates raw question strings or field values mechanically.
    Reads like natural English an AI agent or human can understand.
    """
    ex = explanation or {}
    name = saved_search.get("name", "this search")
    spl  = (saved_search.get("search") or saved_search.get("definition") or "").strip()
    name_readable = re.sub(r"[-_]", " ", name).strip().lower()

    # Extract structured context
    plain       = (ex.get("plain_english") or "").strip()
    trigger     = (ex.get("trigger_condition") or "").strip()
    source      = (ex.get("data_source") or "").strip()
    output_flds = (ex.get("output_fields") or "").strip()
    team        = (ex.get("likely_owner_team") or "security").strip()
    complexity  = (ex.get("complexity") or "moderate").strip()
    purpose     = (ex.get("purpose") or "").strip()  # for macros

    # Remove garbage values
    if source in ("Not explicit in SPL", "Not explicit in definition", ""):
        source = _infer_source_from_spl(spl)

    # ── Sentence 1: Trigger / When to use ─────────────────────────────────────
    if trigger and len(trigger) > 30 and "investigating" not in trigger.lower()[:15]:
        s1 = trigger.rstrip(".") + "."
    else:
        # Smart trigger from the search name
        words = re.findall(r"[A-Za-z][a-z]+|[A-Z]+(?=[A-Z][a-z]|$)", name)
        meaningful = [w.lower() for w in words if w.lower() not in
                      ("the", "a", "an", "of", "for", "by", "and", "or", "in", "to",
                       "from", "with", "at", "this", "that", "generate", "get")]
        topic = " ".join(meaningful[:5]) if meaningful else name_readable
        s1 = f"Use this when a {team} team needs to investigate {topic} across your Splunk environment."

    # ── Sentence 2: What it reads and computes ────────────────────────────────
    # Clean the plain_english — strip mechanical prefixes
    clean_plain = re.sub(
        r"^(Runs SPL to find events for|Searches .* for events related to|Expands macro .* to reusable SPL:)\s*",
        "", plain, flags=re.IGNORECASE
    ).strip()

    if clean_plain and len(clean_plain) > 50:
        # Use the clean plain_english but cap to first 2 sentences
        sentences = re.split(r'\. +', clean_plain)
        s2 = ". ".join(sentences[:2]).rstrip(".") + "."
    elif source:
        commands = [p.strip().split()[0] for p in spl.split("|")[1:] if p.strip()]
        cmd_str = f" applying {', '.join(dict.fromkeys(commands[:3]))} transformations" if commands else ""
        s2 = f"Queries {source}{cmd_str} to surface relevant events and patterns."
    else:
        s2 = f"Analyzes {team} telemetry from Splunk to detect patterns relevant to {name_readable}."

    # ── Sentence 3: What it returns ───────────────────────────────────────────
    fields_clean = output_flds.strip() if output_flds not in ("search results", "results from the search", "") else ""

    if fields_clean:
        s3 = f"Returns results grouped by {fields_clean}, enabling rapid analyst triage and prioritisation."
    elif purpose == "lookup_wrapper":
        s3 = "Returns enriched events with additional context fields joined from lookup tables."
    elif purpose == "stat_aggregation":
        s3 = "Returns aggregated counts and statistics summarised for dashboard or alert consumption."
    elif complexity in ("complex", "very_complex"):
        s3 = "Returns a structured, multi-field result set enriched with computed attributes for detailed investigation."
    else:
        s3 = "Returns a concise result set ready for direct analyst review, alerting, or dashboard display."

    return f"{s1} {s2} {s3}"


def _infer_source_from_spl(spl: str) -> str:
    """Extract data source from SPL including tstats, inputlookup, datamodel patterns."""
    parts = []
    # Standard index/sourcetype
    indexes = re.findall(r"\bindex=(\S+)", spl)
    stypes  = re.findall(r"\bsourcetype=(\S+)", spl)
    if indexes:
        parts.append(f"index={', '.join(dict.fromkeys(indexes[:2]))}") 
    if stypes:
        parts.append(f"sourcetype={', '.join(dict.fromkeys(stypes[:2]))}")
    if parts:
        return "; ".join(parts)
    # tstats over datamodel
    dm = re.findall(r"tstats\b.*?from\s+datamodel=(\S+)", spl, re.IGNORECASE)
    if dm:
        return f"datamodel={', '.join(dict.fromkeys(dm[:2]))}"
    # inputlookup
    lk = re.findall(r"inputlookup\s+(\S+)", spl, re.IGNORECASE)
    if lk:
        return f"lookup={', '.join(dict.fromkeys(lk[:2]))}"
    # REST endpoint
    if "rest splunk_server" in spl.lower() or "/services/" in spl:
        return "Splunk REST API (internal platform data)"
    return "Splunk event data"


def generate_conf_patch(saved_searches: list[dict[str, Any]]) -> str:
    from src.reporter.conf_patcher import generate_conf_patch as _gen
    return _gen(saved_searches)
