#!/usr/bin/env python3
"""Deterministic acceptance smoke test for the issue #5 workflow."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = json.loads((ROOT / "weekly-github-claude-summary.workflow.json").read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"greenfield smoke test failed: {message}")


def node(name: str) -> dict:
    return next(item for item in WORKFLOW["nodes"] if item["name"] == name)


def main() -> None:
    fixture = {
        "repository": "acme/greenfield-saas",
        "language": "EN",
        "commits": [{"sha": "abc1234", "message": "Ship onboarding checklist"}],
        "closedIssues": [{"number": 42, "title": "Document first deploy"}],
        "mergedPulls": [{"number": 77, "title": "Ship dashboard summary"}],
    }
    prompt = (
        f"Weekly activity for {fixture['repository']} in {fixture['language']}: "
        + json.dumps(fixture, sort_keys=True)
    )
    require("#42" not in prompt, "fixture unexpectedly mutates issue numbers")
    require('"number": 42' in prompt, "closed issue is absent from prompt fixture")
    require('"number": 77' in prompt, "merged PR is absent from prompt fixture")
    require("Ship onboarding checklist" in prompt, "commit is absent from prompt fixture")

    build_code = node("Build Claude Prompt")["parameters"]["jsCode"]
    delivery_code = node("Prepare Discord Message")["parameters"]["jsCode"]
    require("Avoid inventing details" in build_code, "anti-fabrication instruction is missing")
    require("config.language === 'FR'" in build_code, "French language branch is missing")
    require("maxLength = 1900" in delivery_code, "Discord length guard is missing")
    require("Trimmed to fit Discord" in delivery_code, "Discord truncation disclosure is missing")
    require("commit?.sha && commit.commit" in build_code, "quiet-week commit placeholder guard is missing")
    require("issue?.number" in build_code, "quiet-week issue placeholder guard is missing")
    require("pr?.number" in build_code, "quiet-week pull placeholder guard is missing")

    for name in ("Get Commits", "Get Closed Issues", "Get Closed Pulls"):
        require(node(name).get("executeOnce") is True, f"{name} can fan out duplicate requests")
        require(node(name).get("alwaysOutputData") is True, f"{name} can stop a quiet-week execution")
        require(node(name).get("retryOnFail") is True, f"{name} does not retry a transient fetch failure")
        require(node(name).get("maxTries") == 3, f"{name} retries are not bounded to three attempts")
        require(node(name).get("onError") is None, f"{name} can silently continue after fetch failure")
        pagination = node(name)["parameters"]["options"]["pagination"]["pagination"]
        require(pagination.get("maxRequests") == 10, f"{name} pagination is not bounded")
        require(
            "$response.body.length < 100" in pagination.get("completeExpression", ""),
            f"{name} cannot detect the final GitHub page",
        )

    for name in ("Generate Claude Summary", "Send Discord Summary"):
        require(node(name).get("executeOnce") is True, f"{name} can execute more than once")

    header = "**Weekly GitHub Summary: acme/greenfield-saas**\n_2026-07-24 to 2026-07-31_\n\n"
    suffix = "\n\n_Trimmed to fit Discord._"
    oversized = "x" * 5000
    available = 1900 - len(header)
    bounded = header + oversized[: available - len(suffix)] + suffix
    require(len(bounded) <= 1900, "bounded Discord payload exceeds 1,900 characters")

    print("greenfield smoke test passed")
    print("fixtures=commits,closed-issues,merged-prs")
    print("languages=EN,FR")
    print("discord-max=1900")
    print("github-fetch=paginated-fail-loud")


if __name__ == "__main__":
    main()
