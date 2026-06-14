from __future__ import annotations

import unittest
from pathlib import Path

from src.health.deprecated_checker import check_saved_search
from src.pipeline import analyze_app
from src.scanner.app_scanner import scan_local_app


ROOT = Path(__file__).resolve().parents[1]


class ScannerTests(unittest.TestCase):
    def test_scan_local_app_reads_core_objects(self) -> None:
        app_data = scan_local_app(ROOT / "tests" / "mock_app", "DemoSecurityApp")

        self.assertEqual(app_data["app_name"], "DemoSecurityApp")
        self.assertEqual(len(app_data["saved_searches"]), 3)
        self.assertEqual(len(app_data["macros"]), 1)
        self.assertEqual(len(app_data["dashboards"]), 1)
        self.assertEqual(app_data["dashboards"][0]["version"], "classic_1.0")

    def test_health_checker_flags_missing_description_and_bad_spl(self) -> None:
        issues = check_saved_search({"name": "bad", "search": 'index=* host="web-prod-1"', "description": ""})
        issue_types = {issue["type"] for issue in issues}

        self.assertIn("missing_mcp_description", issue_types)
        self.assertIn("performance", issue_types)
        self.assertIn("hardcoded_value", issue_types)

    def test_pipeline_generates_outputs_offline(self) -> None:
        result = analyze_app(
            app="DemoSecurityApp",
            config_path=str(ROOT / "config" / "config.yaml.example"),
            app_path=str(ROOT / "tests" / "mock_app"),
            offline_ai=True,
        )

        self.assertGreater(result["scoring"]["objects_scored"], 0)
        for path in result["paths"].values():
            self.assertTrue(Path(path).exists(), path)


if __name__ == "__main__":
    unittest.main()

