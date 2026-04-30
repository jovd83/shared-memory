---
name: shared-memory
description: Manage persistent cross-agent knowledge across agents, skills, and repos. Trigger to assess, retrieve, validate, or deprecate shared conventions, prompts, and org defaults. ALWAYS trigger on "remember", "save", or "note" for cross-turn info.
metadata:
  dispatcher-layer: information
  dispatcher-lifecycle: active
  dispatcher-output-artifacts: shared_policy_entry, policy_lookup_result, deprecation_record, handoff_summary
  dispatcher-risk: medium
  dispatcher-writes-files: true
  dispatcher-input-artifacts: memory_query, policy_candidate, validation_evidence, deprecation_request
  dispatcher-capabilities: shared-policy-management, memory-curation, durable-convention-storage, mission-state-tracking, handoff-coordination
  dispatcher-stack-tags: memory, governance, cross-project, handoff
  dispatcher-accepted-intents: read_shared_policy, write_shared_policy, deprecate_shared_policy, record_handoff, query_mission_state
  dispatcher-category: analysis

---

## Telemetry & Logging
> [!IMPORTANT]
> All usage of this skill must be logged via the Skill Dispatcher to ensure audit logs and wallboard analytics are accurate:
> `./log-dispatch.cmd --skill <skill_name> --intent <intent> --model <model_name> --reason <reason>` (or `./log-dispatch.sh` on Linux)

# Shared Memory Skill

> **Author:** jovd83 | **Version:** 2.5.1


[![Version](https://img.shields.io/badge/version-2.5.0-blue.svg)](CHANGELOG.md)

Use this skill only for deliberate promotion of durable cross-agent knowledge.

## Core Boundary

Shared memory is the top persistence layer in a three-layer model:

- Runtime memory: ephemeral notes for the current task or thread
- Project / skill memory: persistent but local to one repository or skill
- Shared memory: persistent knowledge that should be reused across multiple agents, skills, or repositories, INCLUDING cross-agent project handoffs and mission state.

If the information has value for the *next* agent picking up a project, it belongs in the shared layer.

## Decision Gate

Before invoking a write, confirm every condition:

1. The information is useful beyond the current task.
2. It applies across multiple agents, skills, or repositories (OR it is a project handoff for a multi-agent mission).
3. Another agent can use it safely without hidden local context.
4. It is stable enough to remain useful after the current task ends.
5. It contains no secrets, credentials, personal data, customer data, or sensitive one-off artifacts.

If any condition fails:

- Use runtime memory for task-local notes.
- Use project / skill memory for repository-local persistent knowledge that doesn't need to be seen by agents in other repositories.
- Reject the candidate entirely if it is secret, unstable, or speculative.
## Available Resources

- `scripts/manage_memory.py`: supported CLI for assessing candidates and managing the shared store. Includes `list-active` for mission discovery and `status-report` for health checks.
- `references/promotion-guide.md`: promotion checklist, anti-patterns, and topic naming guidance
- `references/schema.md`: canonical store schema and CLI response contract
- `assets/shared-memory-template.json`: example store layout

## Required Workflow

### 0. Mission Start (Mandatory)
Before starting any complex task, high-risk execution, or multi-agent mission, ALWAYS search shared memory for relevant `MissionState` or `RoutingPolicies`.
If you are unsure of the project name, use the discovery command:
```bash
python scripts/manage_memory.py list-active --format json
```
Then read the specific state:
```bash
python scripts/manage_memory.py search --query "Auth Migration" --format json
python scripts/manage_memory.py read --topic "RoutingPolicies" --format json
```

### 1. Assess the candidate
...
### 8. Maintenance & Health (Janitor Routine)
Periodically check the health of shared memory to identify stale mission states or outdated policies.
```bash
python scripts/manage_memory.py status-report --format json
```
If an entry is flagged as stale (>30 days), either **Renew** it with a fresh status update or **Deprecate** it.

Assess the candidate before writing if the boundary is not obviously shared.
...
(rest of the numbered workflow)
...
### 7. The Rule of Three (Proactive Promotion)
If you find yourself writing or reading the same convention, policy, or fact in **3 or more** different repositories or projects, you MUST promote it to shared memory to ensure global consistency.

## Canonical Topic Taxonomy
To prevent fragmentation, always use these standard topic names unless a specialized domain requires a new one:

| Topic Name | Purpose |
| :--- | :--- |
| `MissionState` | Active project handoffs, status syncs, and multi-agent coordination. |
| `RoutingPolicies` | Global rules for the `skill-dispatcher` and tool selection logic. |
| `GlobalConventions` | Shared engineering standards (e.g. commit styles, linting rules). |
| `SecurityPolicies` | Mandatory security workflows (e.g. `npm audit` requirements). |
| `UserPreferences` | Durable cross-project user settings (e.g. "Prefer Playwright for E2E"). |

## Writing Standard

### Handoff Template (Auditable & Actionable)
When recording a project handoff in `MissionState`, use this structure:
- **Project:** [Name]
- **Status:** [Current Progress %]
- **Done:** [Verified milestones]
- **Blocked/Pending:** [Known bugs or missing prerequisites]
- **Next Step:** [Specific action for the next agent]
- **Context Link:** [Path to local logs or artifacts]

Good entry shapes:
- "Handoff: 'Auth Migration' (50%). Done: JWT implementation. Blocked: Refresh token bug in prod. Next: Debug /tmp/auth-debug.log."
- "Policy: Use sentence-case headings in shared technical docs unless a local style guide overrides them."

Avoid entries that are:

- task-local (e.g. "I fixed line 42")
- low-confidence
- vague
- dependent on hidden context
- sensitive

## Guardrails

- Read before write.
- Reuse durable topic names (e.g., `MissionState`, `RoutingPolicies`, `SecurityStandards`) instead of creating near-duplicates.
- Do not edit the JSON store manually; use `scripts/manage_memory.py`.
- Do not promote runtime memory directly into shared memory without deliberate review.
- Deprecate outdated entries instead of deleting them so the audit trail remains intact.
- If confidence is low, either gather evidence first or do not write the entry.

## Gotchas

- **Topic Fragmentation**: Creating near-duplicate topic names (e.g., `Handoff` vs `MissionState`) fractures memory. Search and read existing topics before adding new ones.
- **Implicit Context Dependency**: Storing entries that rely on local paths or repository-specific knowledge ("use the build script") makes them useless to other agents. Ensure entries are context-independent.
- **Deletion vs Deprecation**: Attempting to delete an entry manually is discouraged. Use the `deprecate` command to maintain a stable audit trail for all shared knowledge.

## Failure Handling

- If `assess` returns `project-memory`, `runtime-memory`, or `reject`, honor that boundary instead of forcing a write.
- If `validate` reports malformed data, stop and repair the store before writing more entries.
- If `write` returns `created: false`, inspect the existing active entry instead of forcing a duplicate.

## Integration Boundary

This skill is responsible only for cross-agent shared memory and cross-session mission state.

It does not implement:

- runtime scratchpads
- repository-local file management
- secret management
- autonomous self-modifying memory pipelines

Treat those as adjacent systems with clear boundaries, not as responsibilities of this skill.
