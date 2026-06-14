from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_conf_file(path: str | Path) -> dict[str, dict[str, str]]:
    """Parse a Splunk-style .conf file into stanza dictionaries."""
    conf_path = Path(path)
    stanzas: dict[str, dict[str, str]] = {}
    current: str | None = None
    last_key: str | None = None

    if not conf_path.exists():
        return stanzas

    for raw_line in conf_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip()
            stanzas.setdefault(current, {})
            last_key = None
            continue

        if current is None:
            continue

        if line[:1].isspace() and last_key:
            stanzas[current][last_key] = f"{stanzas[current][last_key]}\n{stripped}"
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            last_key = key.strip()
            stanzas[current][last_key] = value.strip()

    return stanzas


def merge_conf_dirs(app_path: str | Path, relative_conf: str) -> dict[str, dict[str, str]]:
    """Merge default and local conf files, with local overriding default."""
    base = Path(app_path)
    merged: dict[str, dict[str, str]] = {}

    for layer in ("default", "local"):
        parsed = parse_conf_file(base / layer / relative_conf)
        for stanza, values in parsed.items():
            merged.setdefault(stanza, {}).update(values)

    return merged


def stanzas_to_objects(
    stanzas: dict[str, dict[str, str]],
    *,
    name_key: str = "name",
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for stanza, values in stanzas.items():
        obj: dict[str, Any] = {name_key: stanza, **values}
        if extra:
            obj.update(extra)
        objects.append(obj)
    return objects

