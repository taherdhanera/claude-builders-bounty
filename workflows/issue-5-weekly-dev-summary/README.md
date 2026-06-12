# Weekly GitHub Activity Summary for n8n

This workflow generates a weekly narrative summary for a GitHub repository with Claude and posts it to Discord.

## Setup

1. Import `weekly-github-claude-summary.workflow.json` into n8n.
2. Set these environment variables on the n8n host: `GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME`, `ANTHROPIC_API_KEY`, `WEEKLY_SUMMARY_DISCORD_WEBHOOK_URL`, and optional `SUMMARY_LANGUAGE` (`EN` or `FR`) plus `GITHUB_TOKEN`.
3. Open the workflow, confirm the Friday 5pm schedule, and activate it.
4. Run the workflow manually once from the Schedule Trigger node.
5. Confirm Discord receives the summary, then leave the workflow active for weekly runs.

## Configuration

| Variable | Required | Example | Purpose |
| --- | --- | --- | --- |
| `GITHUB_REPO_OWNER` | Yes | `anthropics` | GitHub owner or organization. |
| `GITHUB_REPO_NAME` | Yes | `claude-code` | GitHub repository name. |
| `ANTHROPIC_API_KEY` | Yes | `sk-ant-...` | Claude API key used by the Anthropic Messages API. |
| `WEEKLY_SUMMARY_DISCORD_WEBHOOK_URL` | Yes | `https://discord.com/api/webhooks/...` | Discord webhook destination. |
| `SUMMARY_LANGUAGE` | No | `EN` or `FR` | Summary language. Defaults to `EN`. |
| `GITHUB_TOKEN` | No | `ghp_...` | Raises GitHub API rate limits and enables private repo access. |

## What it does

- Runs every Friday at 5pm.
- Fetches commits, recently closed issues, and recently merged PRs from the GitHub API for the last 7 days using n8n HTTP Request nodes.
- Sends those events to `claude-sonnet-4-20250514` with a narrative summary prompt.
- Posts the final summary to Discord.

## Validation

The workflow JSON was validated locally with:

```bash
python workflows/issue-5-weekly-dev-summary/validate_workflow.py
```

Expected output is documented in `VERIFICATION.md`. The GitHub API requests are implemented with HTTP Request nodes because n8n Code nodes are for data preparation/transformation, not external HTTP calls. A live n8n execution screenshot still requires real `ANTHROPIC_API_KEY` and Discord webhook values in the target n8n instance.
