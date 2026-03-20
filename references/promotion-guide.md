# Shared Memory Promotion Guide

Use this guide when the correct memory layer is unclear.

## Promotion Checklist

Promote a candidate into shared memory only when every statement is true:

1. It remains useful after the current task ends.
2. It applies across multiple agents, skills, or repositories.
3. Another agent can use it without hidden local context.
4. It is stable enough to be worth preserving.
5. It contains no secrets, credentials, customer data, personal data, or sensitive one-off artifacts.

If any statement is false, do not write it to shared memory.

## Boundary Matrix

| Candidate | Correct Home | Why |
| --- | --- | --- |
| "Step 4 passed; rerun the flaky test." | Runtime memory | Ephemeral and task-local |
| "This repository keeps snapshots under `__snapshots__`." | Project / skill memory | Persistent, but only useful in one codebase |
| "Use ISO 8601 timestamps in cross-repo documentation unless local policy overrides it." | Shared memory | Durable and reusable across repositories |
| "Production billing token is ..." | Reject | Sensitive data must not be stored |
| "Maybe the formatting rule changed last week." | Reject | Unverified and unstable |

## Strong Shared-Memory Entries

Good shared-memory entries are:

- concise
- auditable
- context-independent
- broadly reusable
- stable enough to survive beyond one thread

Examples:

- "Prefer JSON output from CLIs when a tool supports both JSON and text."
- "Use sentence-case headings in shared technical docs unless a local style guide overrides them."
- "Use Conventional Commits across shared repositories unless a local guide overrides them."

## Common Failure Modes

### Promotion pollution

Do not promote every useful observation. Shared memory is valuable because it stays selective.

### Repo leakage

Do not export repository-local paths, setup steps, or conventions simply because they may help in later sessions on the same repository.

### Secret retention

Never store credentials, tokens, private endpoints, customer data, or any comparable sensitive material.

### Guess persistence

Do not store rumors, unverified guesses, or low-confidence assumptions just to avoid rediscovering them later.

### Hidden-context dependency

If another agent needs unwritten repository context to use the entry safely, it is not ready for shared memory.

## Topic Naming Guidance

Prefer topic names that are:

- stable over time
- broad enough to avoid fragmentation
- specific enough to stay searchable

Good examples:

- `CommitConventions`
- `DocumentationConventions`
- `SharedPromptPatterns`
- `ReviewPreferences`

Avoid:

- near-duplicate topics created only because of wording differences
- one-off topics named after a single task or repository
- overly generic buckets such as `MiscNotes`

## Deprecation Guidance

Deprecate an entry when it is outdated, contradicted, harmful, or promoted too aggressively. Do not delete it through the normal workflow.

Good reasons:

- "Superseded by shared writing standard v3."
- "No longer valid after migration to the new release process."
- "Promoted prematurely; this turned out to be repository-local only."

## Assessment Pattern

If the boundary is unclear, use the CLI to make the decision explicit before writing:

```bash
python scripts/manage_memory.py assess \
  --candidate "Use Conventional Commits across shared repositories unless a local guide overrides them." \
  --scope cross-agent \
  --stability stable \
  --sensitivity internal \
  --context-independent yes \
  --format json
```

Expected decision outcomes:

- `shared-memory`
- `project-memory`
- `runtime-memory`
- `reject`

Treat those outcomes as architectural boundaries, not suggestions to work around.
