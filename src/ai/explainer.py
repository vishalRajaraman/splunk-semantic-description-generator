from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from .prompts import build_explain_prompt, build_macro_prompt

PLACEHOLDER_KEYS = {"your_gemini_api_key_here", "your_api_key_here", "your_claude_api_key_here", "your_groq_api_key_here"}
GROQ_API_BASE = "https://api.groq.com/openai/v1"
DEFAULT_GEMINI_MODEL = "llama-3.3-70b-versatile"  # Groq model (variable kept for compatibility)


@dataclass
class GroqClient:
    api_keys: list[str]
    api_base: str = GROQ_API_BASE
    timeout: int = 30
    _idx: int = 0  # round-robin pointer

    def generate_text(
        self, prompt: str, *, model: str = DEFAULT_GEMINI_MODEL, max_tokens: int = 1000
    ) -> str:
        try:
            import requests as _r
        except ImportError as exc:
            raise RuntimeError("Install requests.") from exc

        # Groq uses OpenAI-compatible /chat/completions endpoint
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        n = len(self.api_keys)
        for attempt in range(2):              # try all keys; if all 429, wait 60s once
            for i in range(n):
                key = self.api_keys[(self._idx + i) % n]
                # Groq uses Bearer token auth (OpenAI-compatible)
                try:
                    resp = _r.post(
                        url,
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json=payload,
                        timeout=self.timeout,
                    )
                    if resp.status_code == 429:
                        print(f"  [key {(self._idx+i)%n+1}/{n}] 429")
                        continue
                    resp.raise_for_status()
                    self._idx = (self._idx + i + 1) % n
                    return _extract_groq_text(resp.json())
                except Exception as e:
                    if "429" in str(e):
                        continue
                    raise
            if attempt == 0:
                print(f"  [rate-limit] all {n} keys exhausted — waiting 60s…")
                time.sleep(60)
        raise RuntimeError("All keys rate-limited after retry")


# Keep GeminiClient as alias for backward compatibility
GeminiClient = GroqClient


def get_client(
    api_key: str | list[str] | None,
    *,
    api_base: str = GROQ_API_BASE,
) -> "GroqClient | None":
    """Return a GroqClient. Accepts a single key string or a list of keys for rotation."""
    if not api_key:
        return None
    # Normalise to list
    if isinstance(api_key, str):
        keys = [api_key]
    else:
        keys = list(api_key)
    # Filter out placeholders
    keys = [k.strip() for k in keys if k and k.strip().lower() not in PLACEHOLDER_KEYS]
    if not keys:
        return None
    print(f"  [Groq] Using {len(keys)} API key(s) with rotation enabled")
    return GroqClient(api_keys=keys, api_base=api_base)


def explain_saved_search(
    client: Any,
    saved_search: dict[str, Any],
    *,
    model: str = DEFAULT_GEMINI_MODEL,
    max_tokens: int = 1000,
) -> dict[str, Any]:
    if client is None:
        return heuristic_saved_search_explanation(saved_search)

    prompt = build_explain_prompt(saved_search)
    try:
        return _parse_json_response(
            client.generate_text(prompt, model=model, max_tokens=max_tokens)
        )
    except Exception as exc:
        print(f"  [warn] Gemini error for '{saved_search.get('name')}': {exc} — using heuristic fallback")
        return heuristic_saved_search_explanation(saved_search)


def explain_macro(
    client: Any,
    macro: dict[str, Any],
    *,
    model: str = DEFAULT_GEMINI_MODEL,
    max_tokens: int = 500,
) -> dict[str, Any]:
    if client is None:
        return _heuristic_macro_explanation(macro)

    prompt = build_macro_prompt(macro)
    try:
        return _parse_json_response(
            client.generate_text(prompt, model=model, max_tokens=max_tokens)
        )
    except Exception as exc:
        print(f"  [warn] Gemini error for macro '{macro.get('name')}': {exc} — using heuristic fallback")
        return _heuristic_macro_explanation(macro)


def explain_batch(
    client: Any,
    items: list[dict[str, Any]],
    explain_fn: Callable[..., dict[str, Any]],
    batch_size: int = 1,
    delay: float = 0.0,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Parallel AI processing with guaranteed AI responses — no heuristic fallback.

    All N API keys run as concurrent workers pulling from a shared queue.
    If a key hits 429 for an item, the item re-enters the queue tagged with
    that key so a different key handles it.
    If all N keys are exhausted for one item, waits 60s then resets and retries.
    Workers keep running until every item has an AI-generated result.
    """
    import threading
    from queue import Queue, Empty

    if not items:
        return []

    if client is None:
        # No AI client configured — caller should ensure client is set
        raise RuntimeError("No Gemini client available — set api_key in config.yaml")

    n_keys = len(client.api_keys)
    total  = len(items)
    print_lock = threading.Lock()

    # Per-key clients (isolated _idx so threads don't race on rotation)
    key_clients = [
        GeminiClient(api_keys=[k], api_base=client.api_base, timeout=client.timeout)
        for k in client.api_keys
    ]

    results: list[Any] = [None] * total
    done_count = [0]
    done_lock  = threading.Lock()

    # Queue entries: (orig_idx, item, frozenset of key_indices that already 429'd)
    pending: Queue = Queue()
    for idx, item in enumerate(items):
        pending.put((idx, item, frozenset()))

    def worker(key_idx: int) -> None:
        kc = key_clients[key_idx]
        while True:
            # Exit when all items are done
            with done_lock:
                if done_count[0] >= total:
                    return

            try:
                orig_idx, item, failed_keys = pending.get(timeout=2)
            except Empty:
                continue

            name = item.get("name", f"item {orig_idx + 1}")

            # If this key already failed for this item, hand it back for another key
            if key_idx in failed_keys:
                pending.put((orig_idx, item, failed_keys))
                time.sleep(0.05)   # brief yield so another worker can grab it
                continue

            with print_lock:
                print(f"  [{orig_idx+1}/{total}] key{key_idx+1}: {name}")

            try:
                explanation = explain_fn(kc, item, **kwargs)
                item.update(explanation)
                results[orig_idx] = item
                with done_lock:
                    done_count[0] += 1

            except RuntimeError as exc:
                if "rate-limited" in str(exc).lower() or "429" in str(exc):
                    new_failed = failed_keys | {key_idx}
                    with print_lock:
                        print(f"  [key{key_idx+1}] 429 on '{name}' "
                              f"({len(new_failed)}/{n_keys} keys tried)")

                    if len(new_failed) >= n_keys:
                        # Every key failed — wait 60s then reset and retry
                        with print_lock:
                            print(f"  [all keys exhausted for '{name}'] "
                                  f"waiting 60s then retrying with all keys…")
                        time.sleep(60)
                        pending.put((orig_idx, item, frozenset()))
                    else:
                        pending.put((orig_idx, item, new_failed))
                else:
                    # Non-rate-limit error — log and re-queue once, then raise
                    with print_lock:
                        print(f"  [key{key_idx+1}] ERROR on '{name}': {exc}")
                    pending.put((orig_idx, item, failed_keys | {key_idx}))

    threads = [
        threading.Thread(target=worker, args=(ki,), daemon=True)
        for ki in range(n_keys)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results

def _heuristic_macro_explanation(macro: dict[str, Any]) -> dict[str, Any]:
    """Parse a macro definition intelligently — never dump raw SPL."""
    name = macro.get("name", "this macro")
    defn = (macro.get("definition") or "").strip()
    args = (macro.get("args") or "").strip()
    name_readable = re.sub(r"[-_()]", " ", name).strip().rstrip("0123456789").strip()

    # Parse what the macro does from its definition
    commands = [p.strip().split()[0] for p in defn.split("|") if p.strip()] if defn else []
    indexes = re.findall(r"\bindex=(\S+)", defn)
    stypes  = re.findall(r"\bsourcetype=(\S+)", defn)
    has_stats   = any(c in ("stats", "timechart", "chart", "eventstats") for c in commands)
    has_lookup  = any(c in ("lookup", "inputlookup", "outputlookup") for c in commands)
    has_eval    = "eval" in commands
    has_append  = "append" in commands or "appendcols" in commands
    has_rex     = "rex" in commands or "regex" in commands
    has_fields  = "fields" in commands

    # Determine macro purpose
    if has_lookup:
        purpose = "lookup_wrapper"
        action = "joins a lookup table to enrich events with additional context"
    elif has_stats:
        purpose = "stat_aggregation"
        action = "aggregates events using statistical functions to produce summary counts or metrics"
    elif has_eval:
        purpose = "field_transformer"
        action = "applies computed field transformations using eval expressions"
    elif has_append:
        purpose = "subsearch"
        action = "appends or combines multiple result sets into a unified output"
    elif has_rex:
        purpose = "field_transformer"
        action = "extracts fields from raw event text using regex patterns"
    elif has_fields:
        purpose = "reusable_filter"
        action = "selects and filters specific fields from events"
    elif indexes or stypes:
        purpose = "reusable_filter"
        action = f"filters events from {', '.join(indexes or stypes)}"
    else:
        purpose = "other"
        action = "applies reusable SPL logic as a named building block"

    # Build plain English
    arg_list = [a.strip() for a in args.split(",") if a.strip()] if args else []
    if arg_list:
        arg_str = f" accepting {len(arg_list)} argument(s): {', '.join(arg_list)}"
    else:
        arg_str = " with no arguments"

    plain = (
        f"The `{name}` macro{arg_str} {action}. "
        f"It is designed to be embedded inside saved searches as a reusable SPL component, "
        f"reducing duplication across {name_readable}-related detection logic."
    )
    if commands:
        plain += f" Internally uses the SPL commands: {', '.join(dict.fromkeys(commands[:6]))}."

    return {
        "plain_english": plain,
        "purpose": purpose,
        "arg_descriptions": f"Arguments: {args}" if args else "No arguments",
        "example_usage": f"| `{name}` | stats count by _time",
        "used_in_context": f"Called by saved searches that need {action}.",
        "concerns": [],
        "likely_owner_team": "security" if any(k in defn.lower() for k in ("security", "auth", "winevent", "sysmon")) else "unknown",
        "complexity": "complex" if len(commands) > 5 else ("moderate" if len(commands) > 2 else "simple"),
        "performance_concerns": "None detected",
    }


def heuristic_saved_search_explanation(saved_search: dict[str, Any]) -> dict[str, Any]:
    spl = saved_search.get("search", "") or ""
    name = saved_search.get("name", "this saved search")
    indexes = sorted(set(re.findall(r"\bindex=([^\s|]+)", spl)))
    sourcetypes = sorted(set(re.findall(r"\bsourcetype=([^\s|]+)", spl)))
    commands = [p.strip().split()[0] for p in spl.split("|")[1:] if p.strip()]
    fields_match = re.findall(r"\bby\s+([\w,\s]+?)(?:\s*\||$)", spl)
    output_fields = fields_match[0].strip() if fields_match else "search results"

    data_bits = []
    if indexes:
        data_bits.append(f"index={', '.join(indexes)}")
    if sourcetypes:
        data_bits.append(f"sourcetype={', '.join(sourcetypes)}")
    data_source = "; ".join(data_bits) if data_bits else "Not explicit in SPL"

    team = "unknown"
    combined = (spl + " " + name).lower()
    if any(k in combined for k in ("security", "auth", "sysmon", "wineventlog", "aws:cloudtrail", "failed", "brute", "malware")):
        team = "security"
    elif any(k in combined for k in ("apache", "nginx", "web", "access_combined", "http")):
        team = "devops"
    elif any(k in combined for k in ("network", "cisco", "dns", "firewall", "netflow")):
        team = "netops"
    elif any(k in combined for k in ("aws", "azure", "gcp", "cloud", "s3", "iam")):
        team = "cloud"
    elif any(k in combined for k in ("compliance", "pci", "hipaa", "audit", "gdpr")):
        team = "compliance"

    perf = []
    if "index=*" in spl:
        perf.append("Uses index=* — scans all indexes, very slow in large environments")
    if not re.search(r"earliest=", spl):
        perf.append("No explicit time bounds — may scan excessive historical data")
    if re.search(r"^\s*\*", spl.strip()):
        perf.append("Search starts with wildcard — no index/sourcetype filter")

    n_cmds = len(commands)
    complexity = "very_complex" if n_cmds > 8 else ("complex" if n_cmds > 4 else ("moderate" if n_cmds > 1 else "simple"))
    name_readable = name.replace("_", " ").replace("-", " ").lower()

    plain = f"Searches {data_source} for events related to {name_readable}."
    if commands:
        plain += f" Applies pipeline stages: {', '.join(commands[:5])}."
    if output_fields and output_fields != "search results":
        plain += f" Groups results by {output_fields}."

    return {
        "plain_english": plain,
        "data_source": data_source,
        "business_question": f"What does '{name}' reveal about {team} operations in {data_source}?",
        "trigger_condition": f"Use when investigating {name_readable} in your {team} environment.",
        "output_fields": output_fields,
        "concerns": perf,
        "likely_owner_team": team,
        "complexity": complexity,
        "performance_concerns": "; ".join(perf) if perf else "None detected",
        "likely_user_intent": f"Use when a user asks about {name_readable}.",
    }


def _extract_groq_text(data: dict[str, Any]) -> str:
    """Extract text from Groq's OpenAI-compatible response format."""
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Groq response did not include choices: {data}")
    text = choices[0].get("message", {}).get("content", "")
    if not text.strip():
        raise RuntimeError(f"Groq response did not include text: {data}")
    return text.strip()


# Keep old name for any legacy references
_extract_gemini_text = _extract_groq_text


def _parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "parse_failed", "raw": text}
