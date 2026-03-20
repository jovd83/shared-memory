import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_FILE = ROOT / "SKILL.md"
OPENAI_YAML = ROOT / "agents" / "openai.yaml"
EVALS_FILE = ROOT / "evals" / "shared-memory-cases.json"


def parse_simple_frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise AssertionError("Expected YAML frontmatter.")

    payload = {}
    for line in parts[1].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key, value = stripped.split(":", 1)
        payload[key.strip()] = value.strip().strip('"')
    return payload


def parse_openai_yaml(text: str) -> dict:
    interface = {}
    policy = {}
    section = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            section = stripped[:-1]
            continue
        if ":" not in stripped or section is None:
            continue
        key, value = stripped.split(":", 1)
        normalized_value = value.strip().strip('"')
        if normalized_value in {"true", "false"}:
            normalized_value = normalized_value == "true"
        if section == "interface":
            interface[key.strip()] = normalized_value
        elif section == "policy":
            policy[key.strip()] = normalized_value

    return {"interface": interface, "policy": policy}


class RepositoryContractTests(unittest.TestCase):
    def test_skill_frontmatter_uses_only_trigger_fields(self) -> None:
        frontmatter = parse_simple_frontmatter(SKILL_FILE.read_text(encoding="utf-8"))
        self.assertEqual(set(frontmatter.keys()), {"name", "description"})
        self.assertEqual(frontmatter["name"], "shared-memory")
        self.assertIn("cross-agent", frontmatter["description"])

    def test_openai_metadata_has_required_interface_fields(self) -> None:
        payload = parse_openai_yaml(OPENAI_YAML.read_text(encoding="utf-8"))
        self.assertIn("interface", payload)
        interface = payload["interface"]
        self.assertTrue(interface["display_name"].strip())
        self.assertTrue(interface["short_description"].strip())
        self.assertTrue(interface["default_prompt"].strip())
        self.assertTrue(payload["policy"]["allow_implicit_invocation"])

    def test_eval_cases_follow_expected_shape(self) -> None:
        payload = json.loads(EVALS_FILE.read_text(encoding="utf-8"))
        self.assertIn("cases", payload)
        self.assertGreaterEqual(len(payload["cases"]), 6)

        for case in payload["cases"]:
            self.assertIn("id", case)
            self.assertIn("prompt", case)
            self.assertIn("expected_invocation", case)
            self.assertIn("expected_decision", case)
            self.assertIn("reason", case)
            self.assertIn(
                case["expected_decision"],
                {"write", "reject", "project-memory", "runtime-memory"},
            )


if __name__ == "__main__":
    unittest.main()
