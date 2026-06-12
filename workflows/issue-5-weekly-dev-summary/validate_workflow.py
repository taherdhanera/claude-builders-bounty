#!/usr/bin/env python3
"""Validate the issue #5 n8n workflow export without external services."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_PATH = ROOT / "weekly-github-claude-summary.workflow.json"
README_PATH = ROOT / "README.md"


def fail(message: str) -> None:
    print(f"workflow validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def node_by_name(workflow: dict, name: str) -> dict:
    for node in workflow.get("nodes", []):
        if node.get("name") == name:
            return node
    fail(f"missing node: {name}")


def main() -> None:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    readme = README_PATH.read_text(encoding="utf-8")
    workflow_text = json.dumps(workflow, sort_keys=True)

    require(workflow.get("name"), "workflow name is required")
    require(isinstance(workflow.get("nodes"), list), "nodes must be a list")
    require(isinstance(workflow.get("connections"), dict), "connections must be an object")

    required_nodes = {
        "Weekly Friday 5pm": "n8n-nodes-base.scheduleTrigger",
        "Prepare Config": "n8n-nodes-base.code",
        "Get Commits": "n8n-nodes-base.httpRequest",
        "Get Closed Issues": "n8n-nodes-base.httpRequest",
        "Get Closed Pulls": "n8n-nodes-base.httpRequest",
        "Build Claude Prompt": "n8n-nodes-base.code",
        "Generate Claude Summary": "n8n-nodes-base.httpRequest",
        "Prepare Discord Message": "n8n-nodes-base.code",
        "Send Discord Summary": "n8n-nodes-base.httpRequest",
    }

    for name, expected_type in required_nodes.items():
        node = node_by_name(workflow, name)
        require(node.get("type") == expected_type, f"{name} type should be {expected_type}")

    schedule = node_by_name(workflow, "Weekly Friday 5pm")["parameters"]["rule"]["interval"][0]
    require(schedule.get("field") == "weeks", "trigger must run weekly")
    require(schedule.get("triggerAtDay") == [5], "trigger must run on Friday")
    require(schedule.get("triggerAtHour") == 17, "trigger must run at 17:00")
    require(schedule.get("triggerAtMinute") == 0, "trigger minute must be 0")

    require("claude-sonnet-4-20250514" in workflow_text, "Claude Sonnet 4 model is missing")
    require("https://api.anthropic.com/v1/messages" in workflow_text, "Claude Messages API URL is missing")
    require("ANTHROPIC_API_KEY" in workflow_text, "Anthropic API key env var is missing")
    require("GITHUB_REPO_OWNER" in workflow_text, "GitHub owner env var is missing")
    require("GITHUB_REPO_NAME" in workflow_text, "GitHub repo env var is missing")
    require("SUMMARY_LANGUAGE" in workflow_text, "language env var is missing")
    require("WEEKLY_SUMMARY_DISCORD_WEBHOOK_URL" in workflow_text, "Discord webhook env var is missing")
    require("/commits?" in workflow_text, "commits API fetch is missing")
    require("/issues?state=closed" in workflow_text, "closed issues API fetch is missing")
    require("/pulls?state=closed" in workflow_text, "closed pulls API fetch is missing")
    require("mergedPulls" in workflow_text, "merged PR filtering/output is missing")

    connections = workflow["connections"]
    expected_edges = [
        ("Weekly Friday 5pm", "Prepare Config"),
        ("Prepare Config", "Get Commits"),
        ("Get Commits", "Get Closed Issues"),
        ("Get Closed Issues", "Get Closed Pulls"),
        ("Get Closed Pulls", "Build Claude Prompt"),
        ("Build Claude Prompt", "Generate Claude Summary"),
        ("Generate Claude Summary", "Prepare Discord Message"),
        ("Prepare Discord Message", "Send Discord Summary"),
    ]
    for source, target in expected_edges:
        serialized = json.dumps(connections.get(source, {}))
        require(f'"node": "{target}"' in serialized, f"missing connection {source} -> {target}")

    setup_steps = re.findall(r"(?m)^\d+\.\s+", readme)
    require(len(setup_steps) <= 5, "README setup instructions must be 5 steps or fewer")

    print("workflow validation passed")
    print(f"nodes={len(workflow['nodes'])}")
    print(f"connections={len(workflow['connections'])}")
    print("delivery=discord")
    print("model=claude-sonnet-4-20250514")


if __name__ == "__main__":
    main()
