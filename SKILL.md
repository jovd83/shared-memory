---
name: shared-memory
description: Deliberately assess, retrieve, validate, write, or deprecate persistent cross-agent knowledge that should be reused across multiple agents, skills, or repositories. Use when Codex needs a durable shared ledger for stable conventions, reusable prompt patterns, organization-wide defaults, or broad operating guardrails. Do not use for runtime notes, task plans, repo-local context, secrets, or speculative observations.
metadata:
    dispatcher-layer: execution
    dispatcher-lifecycle: active
  author: jovd83
  version: "2.3.0"
  dispatcher-output-artifacts: shared_policy_entry, policy_lookup_result, deprecation_record
  dispatcher-risk: medium
  dispatcher-writes-files: true
  dispatcher-input-artifacts: memory_query, policy_candidate, validation_evidence, deprecation_request
  dispatcher-capabilities: shared-policy-management, memory-curation, durable-convention-storage
  dispatcher-stack-tags: memory, governance, cross-project
  dispatcher-accepted-intents: read_shared_policy, write_shared_policy, deprecate_shared_policy
  dispatcher-category: analysis
---
# Shared Memory Skill

[![Version](https://img.shields.io/badge/version-2.2.0-blue.svg)](CHANGELOG.md)


Use this skill only for deliberate promotion of durable cross-agent knowledge.


## Telemetry & Logging
> [!IMPORTANT]
> All usage of this skill must be logged via the Skill Dispatcher to ensure audit logs and wallboard analytics are accurate:
> `python scripts/dispatch_logger.py --skill <skill_name> --intent <intent> --reason <reason>`

## Core Boundary

Shared memory is the top persistence layer in a three-layer model:

- Runtime memory: ephemeral notes for the current task or thread
- Project / skill memory: persistent but local to one repository, project, or skill
- Shared memory: persistent knowledge that should be reused across multiple agents, skills, or repositories

If the information does not clearly belong in the third layer, do not write it here.

## Decision Gate

Before invoking a write, confirm every condition:

1. The information is useful beyond the current task.
2. It applies across multiple agents, skills, or repositories.
3. Another agent can use it safely without hidden local context.
4. It is stable enough to remain useful after the current task ends.
5. It contains no secrets, credentials, personal data, customer data, or sensitive one-off artifacts.

If any condition fails:

- Use runtime memory for task-local notes.
- Use project / skill memory for repository-local persistent knowledge.
- Reject the candidate entirely if it is secret, unstable, or speculative.

## Available Resources

- `scripts/manage_memory.py`: supported CLI for assessing candidates and managing the shared store
- `references/promotion-guide.md`: promotion checklist, anti-patterns, and topic naming guidance
- `references/schema.md`: canonical store schema and CLI response contract
- `assets/shared-memory-template.json`: example store layout

## Required Workflow

1. Assess the candidate before writing if the boundary is not obviously shared.

```bash
python scripts/manage_memory.py assess \
  --candidate "Use Conventional Commits across shared repositories unless a local guide overrides them." \
  --scope cross-agent \
  --stability stable \
  --sensitivity internal \
  --context-independent yes \
  --format json
```

2. Discover what already exists before creating or updating anything.

```bash
python scripts/manage_memory.py list-topics --format json
python scripts/manage_memory.py search --query "commit convention" --format json
```

3. Read the closest existing topic before deciding to append a new entry.

```bash
python scripts/manage_memory.py read --topic "CommitConventions" --format json
```

4. Write only verified, reusable knowledge.

```bash
python scripts/manage_memory.py write \
  --topic "CommitConventions" \
  --content "Use Conventional Commits across shared repositories unless a repository-specific guide overrides them." \
  --source "Codex" \
  --confidence 0.95 \
  --tags "git,conventions" \
  --evidence "Repeated across shared engineering guidance and multiple repositories." \
  --format json
```

5. Deprecate obsolete guidance instead of deleting it.

```bash
python scripts/manage_memory.py deprecate \
  --topic "CommitConventions" \
  --id 3 \
  --reason "Superseded by the updated shared engineering standard." \
  --format json
```

6. Validate the store before relying on it if it looks legacy, hand-edited, or inconsistent.

```bash
python scripts/manage_memory.py validate --format json
```

## Response Contract

When you use this skill, drive to one of four explicit outcomes:

- `shared-memory`: read existing shared guidance or write a new shared entry
- `project-memory`: redirect the information to project-local persistent storage
- `runtime-memory`: keep the information in the current task or thread only
- `reject`: refuse to persist the information because it is secret, unstable, or otherwise unsafe

Prefer making that decision explicit in your reasoning and output, especially when the user asks to "remember" something.

## Writing Standard

Every shared-memory entry should be:

- concise
- auditable
- context-independent
- stable
- safe to apply outside the originating repository

Good entry shapes:

- "Use sentence-case headings in shared technical docs unless a local style guide overrides them."
- "Prefer JSON output from CLIs when the tool supports both text and JSON modes."
- "When using Vite 7 with React 19, ensure the `@vitejs/plugin-react` version is 4.3.0+ to avoid HMR metadata bugs."
- "Standardize on `reports/` as the default directory for all diagnostic and audit outputs."
- "Use `py` launcher on Windows instead of `python` to ensure consistent version selection in multi-python environments."

Avoid entries that are:

- task-local
- repository-local
- low-confidence
- vague
- dependent on hidden context
- sensitive

## Guardrails

- Read before write.
- Reuse durable topic names instead of creating near-duplicates.
- Do not edit the JSON store manually; use `scripts/manage_memory.py`.
- Do not promote runtime memory directly into shared memory without deliberate review.
- Deprecate outdated entries instead of deleting them so the audit trail remains intact.
- If confidence is low, either gather evidence first or do not write the entry.

## Gotchas

- **Direct File Editing**: Manually editing the `~/.agent_shared_memory.json` file can cause validation errors and data loss if the CLI overwrites it. Always use the provided CLI tools.
- **Topic Fragmentation**: Creating near-duplicate topic names (e.g., `CommitConvention` vs `CommitConventions`) fractures memory. Search and read existing topics before adding new ones.
- **Implicit Context Dependency**: Storing entries that rely on local paths or repository-specific knowledge ("use the build script") makes them useless to other agents. Ensure entries are context-independent.
- **Low Confidence Promotion**: Promoting information with a confidence lower than 0.5 will trigger warnings in `validate` and risk polluting the store with unstable guidance.
- **Deletion vs Deprecation**: Attempting to delete an entry manually is discouraged. Use the `deprecate` command to maintain a stable audit trail for all shared knowledge.

## Failure Handling

- If `assess` returns `project-memory`, `runtime-memory`, or `reject`, honor that boundary instead of forcing a write.
- If `validate` reports malformed data, stop and repair the store before writing more entries.
- If `write` returns `created: false`, inspect the existing active entry instead of forcing a duplicate.
- If the candidate belongs to only one repository or skill, keep it in project-local memory instead.

## Integration Boundary

This skill is responsible only for cross-agent shared memory.

It does not implement:

- runtime scratchpads
- project-local memory systems
- secret management
- autonomous self-modifying memory pipelines

Treat those as adjacent systems with clear boundaries, not as responsibilities of this skill.
