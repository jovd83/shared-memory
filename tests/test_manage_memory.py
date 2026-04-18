import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "manage_memory.py"


class ManageMemoryCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory_file = Path(self.temp_dir.name) / "shared-memory.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, expect_success: bool = True):
        env = os.environ.copy()
        env["AGENT_SHARED_MEMORY_PATH"] = str(self.memory_file)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--format", "json"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if expect_success and result.returncode != 0:
            self.fail(f"CLI failed with code {result.returncode}: {result.stderr}")
        return result

    def parse_stdout(self, result: subprocess.CompletedProcess) -> dict:
        self.assertTrue(result.stdout.strip(), "Expected JSON output on stdout.")
        return json.loads(result.stdout)

    def test_write_read_and_search_round_trip(self) -> None:
        write_result = self.run_cli(
            "write",
            "--topic",
            "CommitConventions",
            "--content",
            "Use Conventional Commits for shared repositories.",
            "--source",
            "UnitTest",
            "--confidence",
            "0.9",
            "--tags",
            "git,conventions",
        )
        write_payload = self.parse_stdout(write_result)
        self.assertTrue(write_payload["created"])
        self.assertEqual(write_payload["entry"]["id"], 1)

        read_result = self.run_cli("read", "--topic", "CommitConventions")
        read_payload = self.parse_stdout(read_result)
        self.assertEqual(len(read_payload["entries"]), 1)
        self.assertEqual(read_payload["entries"][0]["content"], "Use Conventional Commits for shared repositories.")

        search_result = self.run_cli("search", "--query", "conventional")
        search_payload = self.parse_stdout(search_result)
        self.assertEqual(len(search_payload["matches"]), 1)
        self.assertEqual(search_payload["matches"][0]["topic"], "CommitConventions")

    def test_duplicate_active_entries_are_blocked_by_default(self) -> None:
        self.run_cli(
            "write",
            "--topic",
            "DocumentationConventions",
            "--content",
            "Use sentence-case headings.",
            "--source",
            "UnitTest",
            "--confidence",
            "0.95",
        )
        duplicate_result = self.run_cli(
            "write",
            "--topic",
            "DocumentationConventions",
            "--content",
            "Use sentence-case headings.",
            "--source",
            "UnitTest",
            "--confidence",
            "0.95",
        )
        duplicate_payload = self.parse_stdout(duplicate_result)
        self.assertFalse(duplicate_payload["created"])
        self.assertEqual(duplicate_payload["reason"], "duplicate_active_entry")

        read_result = self.run_cli("read", "--topic", "DocumentationConventions")
        read_payload = self.parse_stdout(read_result)
        self.assertEqual(len(read_payload["entries"]), 1)

    def test_deprecate_hides_entry_from_default_reads(self) -> None:
        self.run_cli(
            "write",
            "--topic",
            "PromptPatterns",
            "--content",
            "Prefer concise summaries for executive updates.",
            "--source",
            "UnitTest",
            "--confidence",
            "0.85",
        )
        deprecate_result = self.run_cli(
            "deprecate",
            "--topic",
            "PromptPatterns",
            "--id",
            "1",
            "--reason",
            "Superseded by updated reporting pattern.",
        )
        deprecate_payload = self.parse_stdout(deprecate_result)
        self.assertTrue(deprecate_payload["updated"])
        self.assertEqual(deprecate_payload["entry"]["status"], "deprecated")

        read_result = self.run_cli("read", "--topic", "PromptPatterns")
        read_payload = self.parse_stdout(read_result)
        self.assertEqual(read_payload["entries"], [])

        read_all_result = self.run_cli(
            "read",
            "--topic",
            "PromptPatterns",
            "--include-deprecated",
        )
        read_all_payload = self.parse_stdout(read_all_result)
        self.assertEqual(len(read_all_payload["entries"]), 1)
        self.assertEqual(read_all_payload["entries"][0]["status"], "deprecated")

    def test_validate_accepts_legacy_store_shape(self) -> None:
        legacy_store = {
            "LegacyTopic": [
                {
                    "timestamp": "2026-03-18T10:00:00Z",
                    "source": "LegacyAgent",
                    "confidence": 0.8,
                    "content": "Legacy entry",
                    "deprecated": False,
                }
            ]
        }
        self.memory_file.write_text(json.dumps(legacy_store), encoding="utf-8")

        result = self.run_cli("validate")
        payload = self.parse_stdout(result)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["stats"]["topics"], 1)
        self.assertEqual(payload["stats"]["entries"], 1)

    def test_invalid_json_returns_nonzero_exit_code(self) -> None:
        self.memory_file.write_text("{not-valid-json", encoding="utf-8")

        result = self.run_cli("validate", expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not valid JSON", result.stderr)

    def test_assess_recommends_shared_memory_for_stable_cross_agent_fact(self) -> None:
        result = self.run_cli(
            "assess",
            "--candidate",
            "Use Conventional Commits across shared repositories unless a local guide overrides them.",
            "--scope",
            "cross-agent",
            "--stability",
            "stable",
            "--sensitivity",
            "internal",
            "--context-independent",
            "yes",
        )
        payload = self.parse_stdout(result)
        self.assertEqual(payload["assessment"]["decision"], "shared-memory")
        self.assertTrue(payload["assessment"]["should_invoke_skill"])

    def test_assess_rejects_secret_candidate(self) -> None:
        result = self.run_cli(
            "assess",
            "--candidate",
            "Production API token for billing service.",
            "--scope",
            "cross-agent",
            "--stability",
            "stable",
            "--sensitivity",
            "secret",
            "--context-independent",
            "yes",
        )
        payload = self.parse_stdout(result)
        self.assertEqual(payload["assessment"]["decision"], "reject")
        self.assertFalse(payload["assessment"]["should_invoke_skill"])

    def test_read_filters_low_confidence_and_stale_entries(self) -> None:
        store = {
            "schema_version": "2.0",
            "topics": {
                "RoutingPolicies": [
                    {
                        "id": 1,
                        "status": "active",
                        "created_at": "2024-01-01T00:00:00Z",
                        "last_reviewed_at": "2024-01-01T00:00:00Z",
                        "review_after_days": 30,
                        "source": "UnitTest",
                        "confidence": 0.95,
                        "content": "Old policy that should be treated as stale.",
                        "tags": ["routing"],
                    },
                    {
                        "id": 2,
                        "status": "active",
                        "created_at": "2026-04-01T00:00:00Z",
                        "last_reviewed_at": "2026-04-01T00:00:00Z",
                        "review_after_days": 365,
                        "source": "UnitTest",
                        "confidence": 0.9,
                        "content": "Fresh policy that should remain readable.",
                        "tags": ["routing"],
                    },
                    {
                        "id": 3,
                        "status": "active",
                        "created_at": "2026-04-10T00:00:00Z",
                        "last_reviewed_at": "2026-04-10T00:00:00Z",
                        "review_after_days": 365,
                        "source": "UnitTest",
                        "confidence": 0.2,
                        "content": "Low confidence policy that should be filtered.",
                        "tags": ["routing"],
                    },
                ]
            },
        }
        self.memory_file.write_text(json.dumps(store), encoding="utf-8")

        result = self.run_cli(
            "read",
            "--topic",
            "RoutingPolicies",
            "--min-confidence",
            "0.8",
            "--max-age-days",
            "365",
        )
        payload = self.parse_stdout(result)
        self.assertEqual(len(payload["entries"]), 1)
        self.assertEqual(payload["entries"][0]["content"], "Fresh policy that should remain readable.")
        self.assertEqual(payload["skipped"]["stale"], 1)
        self.assertEqual(payload["skipped"]["low_confidence"], 1)

    def test_promote_writes_candidate_only_when_boundary_passes(self) -> None:
        result = self.run_cli(
            "promote",
            "--candidate",
            "Prefer repository-native stacks over shared defaults unless compliance requires otherwise.",
            "--topic",
            "RoutingPolicies",
            "--source",
            "UnitTest",
            "--confidence",
            "0.92",
            "--tags",
            "routing,policy",
            "--kind",
            "policy",
            "--review-after-days",
            "365",
            "--scope",
            "cross-agent",
            "--stability",
            "stable",
            "--sensitivity",
            "internal",
            "--context-independent",
            "yes",
        )
        payload = self.parse_stdout(result)
        self.assertTrue(payload["created"])
        self.assertEqual(payload["topic"], "RoutingPolicies")
        self.assertEqual(payload["entry"]["kind"], "policy")

        read_result = self.run_cli("read", "--topic", "RoutingPolicies")
        read_payload = self.parse_stdout(read_result)
        self.assertEqual(len(read_payload["entries"]), 1)
        self.assertEqual(
            read_payload["entries"][0]["content"],
            "Prefer repository-native stacks over shared defaults unless compliance requires otherwise.",
        )


if __name__ == "__main__":
    unittest.main()
