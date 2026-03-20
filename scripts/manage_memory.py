from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "2.0"
DEFAULT_MEMORY_FILE = Path("~/.agent_shared_memory.json").expanduser()
ACTIVE_STATUS = "active"
DEPRECATED_STATUS = "deprecated"
VALID_STATUSES = {ACTIVE_STATUS, DEPRECATED_STATUS}
VALID_MEMORY_SCOPES = {"runtime", "project", "cross-agent"}
VALID_STABILITY_LEVELS = {"ephemeral", "evolving", "stable"}
VALID_SENSITIVITY_LEVELS = {"public", "internal", "secret"}
VALID_CONTEXT_LEVELS = {"yes", "no"}


class MemoryStoreError(Exception):
    exit_code = 1


class InputValidationError(MemoryStoreError):
    exit_code = 2


class MissingEntryError(MemoryStoreError):
    exit_code = 3


class StoreFormatError(MemoryStoreError):
    exit_code = 4


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_memory_file(explicit_path: Optional[str]) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser()
    env_path = os.environ.get("AGENT_SHARED_MEMORY_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_MEMORY_FILE


def default_store() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "topics": {}}


def ensure_topic_name(topic: str) -> str:
    cleaned = topic.strip()
    if not cleaned:
        raise InputValidationError("Topic must not be empty.")
    if len(cleaned) > 80:
        raise InputValidationError("Topic must be 80 characters or fewer.")
    return cleaned


def ensure_source(source: str) -> str:
    cleaned = source.strip()
    if not cleaned:
        raise InputValidationError("Source must not be empty.")
    return cleaned


def ensure_content(content: str) -> str:
    cleaned = " ".join(content.split())
    if not cleaned:
        raise InputValidationError("Content must not be empty.")
    return cleaned


def ensure_confidence(confidence: float) -> float:
    value = float(confidence)
    if not 0.0 <= value <= 1.0:
        raise InputValidationError("Confidence must be between 0.0 and 1.0.")
    return round(value, 4)


def normalize_tags(raw_tags: Optional[Any]) -> List[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        items = raw_tags.split(",")
    elif isinstance(raw_tags, list):
        items = raw_tags
    else:
        raise InputValidationError("Tags must be a comma-separated string or a list of strings.")

    seen = set()
    normalized: List[str] = []
    for item in items:
        tag = str(item).strip()
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(tag)
    return normalized


def normalize_entry(topic: str, raw_entry: Dict[str, Any], fallback_id: int) -> Dict[str, Any]:
    if not isinstance(raw_entry, dict):
        raise StoreFormatError(f"Entry in topic '{topic}' must be a JSON object.")

    entry_id = raw_entry.get("id", fallback_id)
    try:
        entry_id = int(entry_id)
    except (TypeError, ValueError) as exc:
        raise StoreFormatError(f"Entry id in topic '{topic}' must be an integer.") from exc
    if entry_id <= 0:
        raise StoreFormatError(f"Entry id in topic '{topic}' must be positive.")

    status = raw_entry.get("status", ACTIVE_STATUS)
    if raw_entry.get("deprecated") is True:
        status = DEPRECATED_STATUS
    if status not in VALID_STATUSES:
        raise StoreFormatError(
            f"Entry id {entry_id} in topic '{topic}' has invalid status '{status}'."
        )

    created_at = raw_entry.get("created_at") or raw_entry.get("timestamp")
    if not created_at:
        raise StoreFormatError(f"Entry id {entry_id} in topic '{topic}' is missing a timestamp.")

    source = ensure_source(str(raw_entry.get("source", "")))
    content = ensure_content(str(raw_entry.get("content", "")))
    confidence = ensure_confidence(float(raw_entry.get("confidence", 0.0)))
    tags = normalize_tags(raw_entry.get("tags"))

    normalized = {
        "id": entry_id,
        "status": status,
        "created_at": str(created_at),
        "source": source,
        "confidence": confidence,
        "content": content,
        "tags": tags,
    }

    evidence = raw_entry.get("evidence")
    if evidence:
        normalized["evidence"] = str(evidence).strip()

    deprecated_at = raw_entry.get("deprecated_at")
    if deprecated_at:
        normalized["deprecated_at"] = str(deprecated_at)

    deprecation_reason = raw_entry.get("deprecation_reason")
    if deprecation_reason:
        normalized["deprecation_reason"] = str(deprecation_reason).strip()

    return normalized


def normalize_store(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_data, dict):
        raise StoreFormatError("Shared memory file must contain a JSON object at the top level.")

    if "topics" in raw_data:
        topics_raw = raw_data.get("topics")
        if not isinstance(topics_raw, dict):
            raise StoreFormatError("'topics' must be a JSON object.")
    else:
        topics_raw = {
            key: value
            for key, value in raw_data.items()
            if key not in {"schema_version", "__meta__"}
        }

    normalized_topics: Dict[str, List[Dict[str, Any]]] = {}
    for raw_topic, raw_entries in topics_raw.items():
        topic = ensure_topic_name(str(raw_topic))
        if not isinstance(raw_entries, list):
            raise StoreFormatError(f"Topic '{topic}' must map to a list of entries.")
        entries = [normalize_entry(topic, entry, index) for index, entry in enumerate(raw_entries, start=1)]
        entries.sort(key=lambda item: item["id"])
        normalized_topics[topic] = entries

    store = {"schema_version": SCHEMA_VERSION, "topics": normalized_topics}
    hard_errors = [issue for issue in collect_issues(store) if issue["severity"] == "error"]
    if hard_errors:
        messages = "; ".join(issue["message"] for issue in hard_errors)
        raise StoreFormatError(messages)
    return store


def load_store(memory_file: Path) -> Dict[str, Any]:
    if not memory_file.exists():
        return default_store()

    try:
        raw_text = memory_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreFormatError(f"Unable to read shared memory file: {exc}") from exc

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise StoreFormatError(
            f"Shared memory file '{memory_file}' is not valid JSON: {exc}"
        ) from exc

    return normalize_store(raw_data)


def save_store(memory_file: Path, store: Dict[str, Any]) -> None:
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

    temp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(memory_file.parent),
            encoding="utf-8",
            prefix=".shared-memory-",
            suffix=".json",
        ) as handle:
            handle.write(payload)
            temp_path = handle.name
        os.replace(temp_path, memory_file)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def count_entries(entries: List[Dict[str, Any]]) -> Dict[str, int]:
    active_entries = [entry for entry in entries if entry["status"] == ACTIVE_STATUS]
    deprecated_entries = [entry for entry in entries if entry["status"] == DEPRECATED_STATUS]
    return {
        "active_entries": len(active_entries),
        "deprecated_entries": len(deprecated_entries),
        "total_entries": len(entries),
    }


def ensure_choice(value: str, valid_values: set[str], field_name: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in valid_values:
        choices = ", ".join(sorted(valid_values))
        raise InputValidationError(f"{field_name} must be one of: {choices}.")
    return cleaned


def normalized_content_key(content: str) -> str:
    return " ".join(content.lower().split())


def list_topics(store: Dict[str, Any], memory_file: Path) -> Dict[str, Any]:
    topics = []
    for topic in sorted(store["topics"]):
        counts = count_entries(store["topics"][topic])
        topics.append({"topic": topic, **counts})

    return {
        "command": "list-topics",
        "memory_file": str(memory_file),
        "schema_version": SCHEMA_VERSION,
        "topics": topics,
    }


def search_entries(
    store: Dict[str, Any],
    memory_file: Path,
    query: str,
    topic_filter: Optional[str],
    include_deprecated: bool,
    limit: int,
) -> Dict[str, Any]:
    query_text = query.strip().lower()
    if not query_text:
        raise InputValidationError("Search query must not be empty.")

    requested_topic = ensure_topic_name(topic_filter) if topic_filter else None
    matches = []

    for topic in sorted(store["topics"]):
        if requested_topic and topic != requested_topic:
            continue
        for entry in store["topics"][topic]:
            if not include_deprecated and entry["status"] == DEPRECATED_STATUS:
                continue
            haystack = " ".join(
                [topic, entry["content"], entry["source"], " ".join(entry.get("tags", []))]
            ).lower()
            if query_text not in haystack:
                continue
            matches.append({"topic": topic, "entry": entry})
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break

    return {
        "command": "search",
        "memory_file": str(memory_file),
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "matches": matches,
    }


def read_topic(
    store: Dict[str, Any],
    memory_file: Path,
    topic: str,
    include_deprecated: bool,
) -> Dict[str, Any]:
    topic_name = ensure_topic_name(topic)
    entries = store["topics"].get(topic_name, [])
    filtered = [
        entry for entry in entries if include_deprecated or entry["status"] != DEPRECATED_STATUS
    ]

    return {
        "command": "read",
        "memory_file": str(memory_file),
        "schema_version": SCHEMA_VERSION,
        "topic": topic_name,
        "entries": filtered,
    }


def write_entry(
    store: Dict[str, Any],
    memory_file: Path,
    topic: str,
    content: str,
    source: str,
    confidence: float,
    tags: List[str],
    evidence: Optional[str],
    allow_duplicate: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    topic_name = ensure_topic_name(topic)
    normalized_source = ensure_source(source)
    normalized_content = ensure_content(content)
    normalized_confidence = ensure_confidence(confidence)
    normalized_tags = normalize_tags(tags)
    normalized_evidence = evidence.strip() if evidence else None

    entries = store["topics"].setdefault(topic_name, [])
    candidate_key = normalized_content_key(normalized_content)
    if not allow_duplicate:
        for existing_entry in entries:
            if existing_entry["status"] != ACTIVE_STATUS:
                continue
            if normalized_content_key(existing_entry["content"]) == candidate_key:
                return {
                    "command": "write",
                    "memory_file": str(memory_file),
                    "schema_version": SCHEMA_VERSION,
                    "created": False,
                    "topic": topic_name,
                    "entry": existing_entry,
                    "reason": "duplicate_active_entry",
                }

    next_id = max((entry["id"] for entry in entries), default=0) + 1
    entry = {
        "id": next_id,
        "status": ACTIVE_STATUS,
        "created_at": utc_now(),
        "source": normalized_source,
        "confidence": normalized_confidence,
        "content": normalized_content,
        "tags": normalized_tags,
    }
    if normalized_evidence:
        entry["evidence"] = normalized_evidence

    if not dry_run:
        entries.append(entry)
        save_store(memory_file, store)

    return {
        "command": "write",
        "memory_file": str(memory_file),
        "schema_version": SCHEMA_VERSION,
        "created": True,
        "topic": topic_name,
        "entry": entry,
        "dry_run": dry_run,
    }


def assess_candidate(
    candidate: str,
    scope: str,
    stability: str,
    sensitivity: str,
    context_independent: str,
) -> Dict[str, Any]:
    cleaned_candidate = ensure_content(candidate)
    normalized_scope = ensure_choice(scope, VALID_MEMORY_SCOPES, "--scope")
    normalized_stability = ensure_choice(stability, VALID_STABILITY_LEVELS, "--stability")
    normalized_sensitivity = ensure_choice(sensitivity, VALID_SENSITIVITY_LEVELS, "--sensitivity")
    normalized_context = ensure_choice(
        context_independent,
        VALID_CONTEXT_LEVELS,
        "--context-independent",
    )

    reasons: List[str] = []

    if normalized_sensitivity == "secret":
        reasons.append("Sensitive or secret material must never be promoted into shared memory.")
        decision = "reject"
        invoke_skill = False
        recommended_action = "Keep the information out of the shared store and use an approved secret-management system."
    elif normalized_scope == "runtime":
        reasons.append("The candidate is scoped to the current task or thread only.")
        decision = "runtime-memory"
        invoke_skill = False
        recommended_action = "Keep it in ephemeral runtime memory or the current thread context."
    elif normalized_scope == "project":
        reasons.append("The candidate is durable, but only within one repository, skill, or project.")
        decision = "project-memory"
        invoke_skill = False
        recommended_action = "Store it in project-local documentation or project-local persistent memory instead."
    elif normalized_context == "no":
        reasons.append("Another agent could not apply this safely without hidden local context.")
        decision = "project-memory"
        invoke_skill = False
        recommended_action = "Keep it local until it can be rewritten as a context-independent convention or fact."
    elif normalized_stability != "stable":
        reasons.append("Cross-agent shared memory should contain stable guidance rather than evolving or speculative material.")
        decision = "reject"
        invoke_skill = False
        recommended_action = "Wait until the information is verified and stable before promoting it."
    else:
        reasons.append("The candidate is cross-agent, stable, and safe to apply without hidden local context.")
        decision = "shared-memory"
        invoke_skill = True
        recommended_action = "Search existing topics first, then read the best match before deciding whether to write a new entry."

    return {
        "command": "assess",
        "schema_version": SCHEMA_VERSION,
        "candidate": cleaned_candidate,
        "assessment": {
            "decision": decision,
            "should_invoke_skill": invoke_skill,
            "recommended_action": recommended_action,
            "reasons": reasons,
            "inputs": {
                "scope": normalized_scope,
                "stability": normalized_stability,
                "sensitivity": normalized_sensitivity,
                "context_independent": normalized_context,
            },
        },
    }


def deprecate_entry(
    store: Dict[str, Any],
    memory_file: Path,
    topic: str,
    entry_id: int,
    reason: Optional[str],
    dry_run: bool,
) -> Dict[str, Any]:
    topic_name = ensure_topic_name(topic)
    entries = store["topics"].get(topic_name)
    if not entries:
        raise MissingEntryError(f"Topic '{topic_name}' was not found.")

    for entry in entries:
        if entry["id"] != entry_id:
            continue
        updated_entry = dict(entry)
        if updated_entry["status"] == DEPRECATED_STATUS:
            return {
                "command": "deprecate",
                "memory_file": str(memory_file),
                "schema_version": SCHEMA_VERSION,
                "updated": False,
                "topic": topic_name,
                "entry": updated_entry,
                "reason": "already_deprecated",
            }

        updated_entry["status"] = DEPRECATED_STATUS
        updated_entry["deprecated_at"] = utc_now()
        if reason:
            updated_entry["deprecation_reason"] = reason.strip()

        if not dry_run:
            index = entries.index(entry)
            entries[index] = updated_entry
            save_store(memory_file, store)

        return {
            "command": "deprecate",
            "memory_file": str(memory_file),
            "schema_version": SCHEMA_VERSION,
            "updated": True,
            "topic": topic_name,
            "entry": updated_entry,
            "dry_run": dry_run,
        }

    raise MissingEntryError(f"Entry id {entry_id} was not found in topic '{topic_name}'.")


def collect_issues(store: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for topic, entries in store["topics"].items():
        seen_ids = set()
        seen_active_content = set()

        for entry in entries:
            entry_id = entry["id"]
            if entry_id in seen_ids:
                issues.append(
                    {
                        "severity": "error",
                        "topic": topic,
                        "entry_id": str(entry_id),
                        "message": f"Duplicate entry id {entry_id} found in topic '{topic}'.",
                    }
                )
            seen_ids.add(entry_id)

            if entry["status"] not in VALID_STATUSES:
                issues.append(
                    {
                        "severity": "error",
                        "topic": topic,
                        "entry_id": str(entry_id),
                        "message": f"Entry id {entry_id} in topic '{topic}' has an invalid status.",
                    }
                )
            if not 0.0 <= entry["confidence"] <= 1.0:
                issues.append(
                    {
                        "severity": "error",
                        "topic": topic,
                        "entry_id": str(entry_id),
                        "message": f"Entry id {entry_id} in topic '{topic}' has confidence outside 0.0-1.0.",
                    }
                )

            if entry["status"] == ACTIVE_STATUS:
                content_key = normalized_content_key(entry["content"])
                if content_key in seen_active_content:
                    issues.append(
                        {
                            "severity": "warning",
                            "topic": topic,
                            "entry_id": str(entry_id),
                            "message": f"Topic '{topic}' contains duplicate active content.",
                        }
                    )
                seen_active_content.add(content_key)

            if entry["status"] == DEPRECATED_STATUS and not entry.get("deprecated_at"):
                issues.append(
                    {
                        "severity": "warning",
                        "topic": topic,
                        "entry_id": str(entry_id),
                        "message": f"Deprecated entry id {entry_id} in topic '{topic}' is missing 'deprecated_at'.",
                    }
                )

            if entry["confidence"] < 0.5:
                issues.append(
                    {
                        "severity": "warning",
                        "topic": topic,
                        "entry_id": str(entry_id),
                        "message": f"Entry id {entry_id} in topic '{topic}' has low confidence for shared memory.",
                    }
                )

    return issues


def validate_store_command(store: Dict[str, Any], memory_file: Path) -> Dict[str, Any]:
    issues = collect_issues(store)
    topic_count = len(store["topics"])
    entry_count = sum(len(entries) for entries in store["topics"].values())

    return {
        "command": "validate",
        "memory_file": str(memory_file),
        "schema_version": SCHEMA_VERSION,
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "issues": issues,
        "stats": {"topics": topic_count, "entries": entry_count},
    }


def render_text(result: Dict[str, Any]) -> str:
    command = result["command"]

    if command == "assess":
        assessment = result["assessment"]
        lines = [
            f"Decision: {assessment['decision']}",
            f"Invoke shared-memory skill: {'yes' if assessment['should_invoke_skill'] else 'no'}",
            f"Recommended action: {assessment['recommended_action']}",
            "Reasons:",
        ]
        for reason in assessment["reasons"]:
            lines.append(f"- {reason}")
        return "\n".join(lines)

    if command == "list-topics":
        topics = result["topics"]
        if not topics:
            return "No shared-memory topics found."
        lines = ["Available topics:"]
        for topic in topics:
            lines.append(
                f"- {topic['topic']} ({topic['active_entries']} active, "
                f"{topic['deprecated_entries']} deprecated, {topic['total_entries']} total)"
            )
        return "\n".join(lines)

    if command == "search":
        matches = result["matches"]
        if not matches:
            return f"No entries matched '{result['query']}'."
        lines = [f"Matches for '{result['query']}':"]
        for match in matches:
            entry = match["entry"]
            lines.append(
                f"- {match['topic']} #{entry['id']} [{entry['status']}] "
                f"{entry['content']} (source: {entry['source']}, confidence: {entry['confidence']})"
            )
        return "\n".join(lines)

    if command == "read":
        entries = result["entries"]
        if not entries:
            return f"No entries found for topic '{result['topic']}'."
        lines = [f"Entries for '{result['topic']}':"]
        for entry in entries:
            lines.append(
                f"- #{entry['id']} [{entry['status']}] {entry['content']} "
                f"(source: {entry['source']}, confidence: {entry['confidence']})"
            )
        return "\n".join(lines)

    if command == "write":
        entry = result["entry"]
        if result["created"]:
            suffix = " (dry-run)" if result.get("dry_run") else ""
            return f"Created entry #{entry['id']} in topic '{result['topic']}'{suffix}."
        return (
            f"Skipped write for topic '{result['topic']}' because an active duplicate already exists "
            f"(entry #{entry['id']})."
        )

    if command == "deprecate":
        entry = result["entry"]
        if result["updated"]:
            suffix = " (dry-run)" if result.get("dry_run") else ""
            return f"Deprecated entry #{entry['id']} in topic '{result['topic']}'{suffix}."
        return f"Entry #{entry['id']} in topic '{result['topic']}' was already deprecated."

    if command == "validate":
        status = "valid" if result["valid"] else "invalid"
        issues = result["issues"]
        if not issues:
            return f"Shared memory store is {status}."
        lines = [f"Shared memory store is {status}.", "Issues:"]
        for issue in issues:
            lines.append(
                f"- [{issue['severity']}] {issue['topic']} #{issue['entry_id']}: {issue['message']}"
            )
        return "\n".join(lines)

    raise InputValidationError(f"Unsupported render command '{command}'.")


def emit_result(result: Dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    if output_format == "text":
        print(render_text(result))
        return
    raise InputValidationError(f"Unsupported output format '{output_format}'.")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--memory-file",
        help="Override the shared-memory file path. Defaults to AGENT_SHARED_MEMORY_PATH or ~/.agent_shared_memory.json.",
    )
    common.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Choose stdout format. JSON is the default for agentic use.",
    )

    parser = argparse.ArgumentParser(
        description="Manage the shared cross-agent memory store."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    assess_parser = subparsers.add_parser(
        "assess",
        parents=[common],
        help="Assess whether a candidate belongs in shared memory, project memory, runtime memory, or nowhere.",
    )
    assess_parser.add_argument(
        "--candidate",
        required=True,
        help="Candidate statement being evaluated for promotion.",
    )
    assess_parser.add_argument(
        "--scope",
        required=True,
        choices=tuple(sorted(VALID_MEMORY_SCOPES)),
        help="Where the information is expected to remain useful: runtime, project, or cross-agent.",
    )
    assess_parser.add_argument(
        "--stability",
        required=True,
        choices=tuple(sorted(VALID_STABILITY_LEVELS)),
        help="How stable the information is: ephemeral, evolving, or stable.",
    )
    assess_parser.add_argument(
        "--sensitivity",
        required=True,
        choices=tuple(sorted(VALID_SENSITIVITY_LEVELS)),
        help="Whether the information is public/internal or secret.",
    )
    assess_parser.add_argument(
        "--context-independent",
        required=True,
        choices=tuple(sorted(VALID_CONTEXT_LEVELS)),
        help="Whether another agent can apply it safely without hidden local context.",
    )

    subparsers.add_parser(
        "list-topics",
        parents=[common],
        help="List known topics with active and deprecated counts.",
    )

    search_parser = subparsers.add_parser(
        "search",
        parents=[common],
        help="Search topics and entries for a string.",
    )
    search_parser.add_argument("--query", required=True, help="Case-insensitive search string.")
    search_parser.add_argument("--topic", help="Restrict search to a single topic.")
    search_parser.add_argument(
        "--include-deprecated",
        action="store_true",
        help="Include deprecated entries in results.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of matches to return.",
    )

    read_parser = subparsers.add_parser(
        "read",
        parents=[common],
        help="Read all entries for a topic.",
    )
    read_parser.add_argument("--topic", required=True, help="Topic to read.")
    read_parser.add_argument(
        "--include-deprecated",
        action="store_true",
        help="Include deprecated entries in the output.",
    )

    write_parser = subparsers.add_parser(
        "write",
        parents=[common],
        help="Write a new shared-memory entry.",
    )
    write_parser.add_argument("--topic", required=True, help="Topic to append to.")
    write_parser.add_argument("--content", required=True, help="Shared-memory statement.")
    write_parser.add_argument("--source", required=True, help="Who is writing the entry.")
    write_parser.add_argument(
        "--confidence",
        required=True,
        type=float,
        help="Confidence score between 0.0 and 1.0.",
    )
    write_parser.add_argument(
        "--tags",
        default="",
        help="Optional comma-separated tags.",
    )
    write_parser.add_argument(
        "--evidence",
        help="Optional short note explaining why the entry is trustworthy.",
    )
    write_parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="Allow an exact active duplicate inside the same topic.",
    )
    write_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Return the proposed entry without writing it.",
    )

    deprecate_parser = subparsers.add_parser(
        "deprecate",
        parents=[common],
        help="Deprecate an existing entry instead of deleting it.",
    )
    deprecate_parser.add_argument("--topic", required=True, help="Topic containing the entry.")
    deprecate_parser.add_argument("--id", required=True, type=int, help="Entry id within the topic.")
    deprecate_parser.add_argument("--reason", help="Optional audit reason for deprecation.")
    deprecate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Return the proposed deprecation without writing it.",
    )

    subparsers.add_parser(
        "validate",
        parents=[common],
        help="Validate the store shape and surface warnings.",
    )

    return parser


def run_command(args: argparse.Namespace) -> Dict[str, Any]:
    memory_file = resolve_memory_file(args.memory_file)
    if args.command == "assess":
        return assess_candidate(
            candidate=args.candidate,
            scope=args.scope,
            stability=args.stability,
            sensitivity=args.sensitivity,
            context_independent=args.context_independent,
        )

    store = load_store(memory_file)

    if args.command == "list-topics":
        return list_topics(store, memory_file)
    if args.command == "search":
        if args.limit <= 0:
            raise InputValidationError("--limit must be a positive integer.")
        return search_entries(
            store=store,
            memory_file=memory_file,
            query=args.query,
            topic_filter=args.topic,
            include_deprecated=args.include_deprecated,
            limit=args.limit,
        )
    if args.command == "read":
        return read_topic(
            store=store,
            memory_file=memory_file,
            topic=args.topic,
            include_deprecated=args.include_deprecated,
        )
    if args.command == "write":
        return write_entry(
            store=store,
            memory_file=memory_file,
            topic=args.topic,
            content=args.content,
            source=args.source,
            confidence=args.confidence,
            tags=args.tags,
            evidence=args.evidence,
            allow_duplicate=args.allow_duplicate,
            dry_run=args.dry_run,
        )
    if args.command == "deprecate":
        return deprecate_entry(
            store=store,
            memory_file=memory_file,
            topic=args.topic,
            entry_id=args.id,
            reason=args.reason,
            dry_run=args.dry_run,
        )
    if args.command == "validate":
        return validate_store_command(store, memory_file)
    raise InputValidationError(f"Unsupported command '{args.command}'.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = run_command(args)
        emit_result(result, args.format)
        return 0
    except MemoryStoreError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # pragma: no cover - defensive safeguard
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
