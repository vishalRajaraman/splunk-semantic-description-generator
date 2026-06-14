from __future__ import annotations

import json
from typing import Any


def build_explain_prompt(saved_search: dict[str, Any]) -> str:
    name = saved_search.get("name", "unknown")
    spl = saved_search.get("search", "")
    is_scheduled = saved_search.get("is_scheduled", "0") == "1"
    schedule = saved_search.get("cron_schedule", "")
    earliest = saved_search.get("dispatch_earliest_time", "")
    latest = saved_search.get("dispatch_latest_time", "")
    alert_type = saved_search.get("alert_type", "")
    existing_desc = saved_search.get("description", "")

    return f"""You are a senior Splunk architect and threat intelligence analyst with 15 years of experience.
Your task is to deeply analyse this Splunk saved search and extract maximum semantic meaning from it.

=== SEARCH METADATA ===
Name: {name}
Scheduled: {'YES — cron: ' + schedule if is_scheduled else 'No'}
Time window: {earliest or 'not set'} to {latest or 'not set'}
Alert type: {alert_type or 'none'}
Existing description: {existing_desc or '(empty — this is the core problem we are solving)'}

=== SPL QUERY ===
{spl}

=== YOUR ANALYSIS TASK ===
Examine the SPL carefully. Identify:
- Which data sources (index, sourcetype, host) are queried
- What events or patterns are being searched for
- What transformations/aggregations are applied (stats, eval, rex, join, etc.)
- What the output looks like (fields returned, groupings)
- What operational question this answers for a security/ops team
- Any performance concerns (index=*, no time filter, unbounded search)

Return EXACTLY this JSON (all 8 keys required, no extra keys, no markdown fences):
{{
  "plain_english": "3-4 sentences. What data it reads, what pattern it finds, what output it produces, and what action a team should take based on results. Be specific about field names and thresholds if present in the SPL.",
  "data_source": "Exact indexes and sourcetypes queried (e.g. 'index=wineventlog sourcetype=WinEventLog:Security, EventCode 4625'). If lookup tables are joined, name them.",
  "business_question": "The precise operational question this answers (e.g. 'Which user accounts had 10+ failed authentication attempts from a single IP in the last hour, grouped by user and source?')",
  "trigger_condition": "When should an analyst use this search? What specific scenario or alert would make them run this? Be concrete.",
  "output_fields": "Key fields returned by this search (e.g. 'user, src_ip, count, first_seen, last_seen'). Infer from SPL if not explicit.",
  "likely_owner_team": "One of exactly: security | devops | netops | cloud | compliance | platform | unknown",
  "complexity": "One of exactly: simple | moderate | complex | very_complex",
  "performance_concerns": "Specific SPL anti-patterns (e.g. 'Uses index=* — will scan all indexes, very slow on large environments'). Say 'None detected' if clean."
}}"""


def build_macro_prompt(macro: dict[str, Any]) -> str:
    name = macro.get("name", "unknown")
    definition = macro.get("definition", "")
    args = macro.get("args", "")
    existing_desc = macro.get("description", "")

    return f"""You are a senior Splunk engineer. Analyse this Splunk macro deeply.
Return JSON ONLY — no preamble, no markdown fences.

=== MACRO METADATA ===
Name: {name}
Arguments: {args if args else 'None (zero-argument macro)'}
Existing description: {existing_desc or '(empty)'}

=== MACRO DEFINITION ===
{definition}

=== YOUR TASK ===
Understand exactly what SPL this macro expands to and what role it plays.
Identify: what filter/logic it encodes, what arguments it accepts and how they change the output,
what searches would call this macro and in what context.

Return EXACTLY this JSON:
{{
  "plain_english": "2-3 sentences. What SPL this expands to, what it filters/computes, and in what context searches use it.",
  "purpose": "One of exactly: reusable_filter | time_window_helper | lookup_wrapper | stat_aggregation | field_transformer | eval_expression | subsearch | other",
  "arg_descriptions": "For each argument, explain its role (e.g. 'index_name: the Splunk index to search; time_range: earliest time offset'). Say 'No arguments' if zero-arg.",
  "example_usage": "A concrete example of how a saved search would call this macro (e.g. '| `failed_logins(security, -1h)` | stats count by user')",
  "used_in_context": "What type of searches typically call this macro and why."
}}"""


def build_mcp_prompt(saved_search: dict[str, Any], explanation: dict[str, Any]) -> str:
    name = saved_search.get("name", "unknown")
    spl = (saved_search.get("search", "") or "")[:600]
    plain = explanation.get("plain_english", "")
    question = explanation.get("business_question", "")
    trigger = explanation.get("trigger_condition", "")
    source = explanation.get("data_source", "")
    output_fields = explanation.get("output_fields", "")
    team = explanation.get("likely_owner_team", "unknown")
    complexity = explanation.get("complexity", "moderate")

    return f"""You are writing the semantic `description` field for a Splunk saved search that will be exposed to AI agents via the Splunk MCP (Model Context Protocol) Server.

CONTEXT: AI agents (like Claude, GPT-4, Gemini) use this description as a "tool card" to decide:
1. WHETHER to call this search (does it answer the user's question?)
2. WHEN to call it (what scenario triggers it?)
3. WHAT to expect back (what fields/data will it return?)

The description MUST be specific enough that an AI agent with no prior Splunk knowledge can correctly invoke this search in the right situation.

=== SEARCH CONTEXT ===
Name: {name}
Owner team: {team}
Complexity: {complexity}
What it does: {plain}
Business question answered: {question}
When to trigger: {trigger}
Data source: {source}
Output fields: {output_fields}
SPL snippet: {spl[:300]}

=== RULES ===
- Length: 2-4 sentences (60–180 words)
- Start with: "Use this search when..." OR "Returns..." OR "Detects..."
- Sentence 1: trigger condition (when/why to call this)
- Sentence 2: what data it reads and what it finds
- Sentence 3: what the output contains (fields, groupings, counts)
- Sentence 4 (optional): specific threshold or action threshold if known
- Include the data source name (index/sourcetype) in plain terms
- Include key output field names so the agent knows what to parse
- Do NOT use: "dashboard", "visualization", "chart", "panel", generic filler
- Do NOT use passive voice excessively
- Be concrete and specific — avoid "this search analyzes data to provide insights"

Return the description as plain text ONLY — no JSON, no quotes, no markdown."""
