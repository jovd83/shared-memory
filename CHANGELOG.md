# Changelog

All notable changes to this skill are documented here.

## [2.1.0] - 2026-03-20

### Changed

- Rewrote `SKILL.md` into a stricter agent contract with an explicit four-outcome memory decision model: `shared-memory`, `project-memory`, `runtime-memory`, or `reject`.
- Refined the repository documentation for faster adoption, clearer architectural boundaries, and stronger GitHub-readiness.
- Strengthened `agents/openai.yaml` metadata so the skill advertises both assessment and store-management behavior.
- Expanded evaluation cases to cover hidden-context failures and runtime-memory routing.

### Added

- `assess` command in `scripts/manage_memory.py` for deterministic pre-write boundary decisions.
- Repository contract tests for `SKILL.md`, `agents/openai.yaml`, and evaluation artifacts.

### Fixed

- Removed non-standard frontmatter metadata from `SKILL.md`.
- Clarified schema and promotion guidance so maintainers and agents can distinguish shared memory from project-local and runtime memory more reliably.

## [2.0.0] - 2026-03-18

### Changed

- Rewrote `SKILL.md` into a portable, agent-first contract with clear promotion criteria, guardrails, and failure handling.
- Rebuilt the shared-memory CLI around a versioned schema, structured JSON output, atomic writes, stronger validation, and legacy-store normalization.
- Reframed the repository documentation around explicit architectural boundaries and GitHub-ready usage guidance.

### Added

- `agents/openai.yaml` for UI-facing skill metadata.
- `references/promotion-guide.md` with concrete decision rules and anti-patterns.
- `references/schema.md` documenting the store schema and CLI output contract.
- `tests/test_manage_memory.py` for regression coverage.
- `evals/shared-memory-cases.json` for invocation and boundary evaluation.
- `LICENSE` and `.gitignore` for repository hygiene.

### Removed

- Prototype-only repository state files and vague documentation that blurred runtime, project-local, and shared-memory concerns.

## [1.0.0] - 2026-03-18

### Added

- Initial prototype of the shared-memory skill, reference notes, and Python CLI.
