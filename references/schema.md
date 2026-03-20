# Shared Memory Store Schema

This document defines the canonical shared-memory file format and the CLI response contract implemented by `scripts/manage_memory.py`.

## Store Path Resolution

The CLI resolves the store path in this order:

1. `--memory-file`
2. `AGENT_SHARED_MEMORY_PATH`
3. `~/.agent_shared_memory.json`

The file is created on the first successful write if it does not already exist.

## Canonical Store Schema

```json
{
  "schema_version": "2.0",
  "topics": {
    "CommitConventions": [
      {
        "id": 1,
        "status": "active",
        "created_at": "2026-03-18T10:00:00Z",
        "source": "Codex",
        "confidence": 0.95,
        "content": "Use Conventional Commits across shared repositories unless a repository-specific guide overrides them.",
        "tags": ["git", "conventions"],
        "evidence": "Observed in shared engineering guidance across multiple repositories."
      }
    ]
  }
}
```

## Entry Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | Yes | Unique within a topic |
| `status` | string | Yes | `active` or `deprecated` |
| `created_at` | string | Yes | UTC timestamp in ISO 8601 form |
| `source` | string | Yes | Agent, maintainer, or system identifier |
| `confidence` | number | Yes | Floating-point value from `0.0` to `1.0` |
| `content` | string | Yes | Reusable shared-memory statement |
| `tags` | array of strings | No | Lightweight discovery aids |
| `evidence` | string | No | Short explanation for why the entry is trustworthy |
| `deprecated_at` | string | No | Present when `status` is `deprecated` |
| `deprecation_reason` | string | No | Audit note explaining the deprecation |

## Legacy Compatibility

The CLI accepts the earlier flat format where topics were top-level keys and entries used `timestamp` plus `deprecated: true|false`.

Legacy stores are normalized in memory and saved back in canonical form the next time a write or deprecate operation succeeds.

## Command Output Contract

JSON is the default stdout format for every command.

Common top-level fields:

- `command`
- `schema_version`

Commands that operate on the store also return:

- `memory_file`

### `assess`

Returns:

- `candidate`
- `assessment.decision`
- `assessment.should_invoke_skill`
- `assessment.recommended_action`
- `assessment.reasons`
- `assessment.inputs`

Possible decisions:

- `shared-memory`
- `project-memory`
- `runtime-memory`
- `reject`

### `list-topics`

Returns:

- `topics`

Each topic row contains:

- `topic`
- `active_entries`
- `deprecated_entries`
- `total_entries`

### `search`

Returns:

- `query`
- `matches`

Each match contains:

- `topic`
- `entry`

### `read`

Returns:

- `topic`
- `entries`

### `write`

Returns:

- `created`
- `topic`
- `entry`
- `dry_run` when requested

If an exact active duplicate is found, `created` is `false` and `reason` is `duplicate_active_entry`.

### `deprecate`

Returns:

- `updated`
- `topic`
- `entry`
- `dry_run` when requested

If the target is already deprecated, `updated` is `false` and `reason` is `already_deprecated`.

### `validate`

Returns:

- `valid`
- `issues`
- `stats`

## Validation Rules

The CLI validates that:

- topic names are non-empty
- topic names are 80 characters or fewer
- entries are JSON objects
- `id` values are positive integers and unique within a topic
- `confidence` is between `0.0` and `1.0`
- `status` is `active` or `deprecated`
- duplicate active entries within a topic are flagged

Warnings may also appear for:

- low-confidence entries
- deprecated entries missing deprecation metadata

## Safety Properties

- Writes are atomic through temporary-file replacement.
- Deprecated entries remain in the store for auditability.
- Exact duplicate active entries are blocked by default.
- Structured JSON output keeps the CLI composable for agents and automation.
