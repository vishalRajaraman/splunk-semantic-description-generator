from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree


def extract_dashboard_version(xml_str: str, label: str = "") -> str:
    """Detect classic XML vs Dashboard Studio vs nav views."""
    if not xml_str or not xml_str.strip():
        # Empty XML = this is a nav/menu view, not a real dashboard
        return "nav_view"
    lowered = xml_str.lower().strip()
    # Dashboard Studio (JSON-based)
    if "dashboardstudio" in lowered or '"visualizations"' in lowered or '"definition"' in lowered:
        return "studio_v2"
    if 'version="1.1"' in xml_str:
        return "studio_v2"
    # Classic Simple XML
    if "<dashboard" in lowered:
        return "simple_xml"
    if "<form" in lowered:
        return "simple_xml_form"
    # Nav/search/other view types
    if "<nav" in lowered:
        return "nav_view"
    if "<saved" in lowered or "<alert" in lowered:
        return "saved_view"
    return "simple_xml"  # default assumption for non-empty XML


def parse_dashboard_file(path: str | Path) -> dict[str, object]:
    dashboard_path = Path(path)
    xml = dashboard_path.read_text(encoding="utf-8", errors="replace")
    label = dashboard_path.stem

    try:
        root = ElementTree.fromstring(xml)
        label = root.attrib.get("label") or root.findtext("label") or label
    except ElementTree.ParseError:
        pass

    return {
        "name": dashboard_path.stem,
        "label": label,
        "xml": xml,
        "version": extract_dashboard_version(xml),
        "path": str(dashboard_path),
    }


def parse_dashboard_dir(app_path: str | Path) -> list[dict[str, object]]:
    base = Path(app_path)
    dashboards: list[dict[str, object]] = []
    for layer in ("default", "local"):
        views_dir = base / layer / "data" / "ui" / "views"
        if not views_dir.exists():
            continue
        for xml_file in sorted(views_dir.glob("*.xml")):
            dashboards.append(parse_dashboard_file(xml_file))
    return dashboards

