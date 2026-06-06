# n8n Weekly GitHub Summary with Claude

Importable n8n workflow for issue #5. It runs every Friday at 17:00, fetches the last seven days of GitHub commits, closed issues, and merged PRs, asks Claude `claude-sonnet-4-20250514` for a narrative summary, and posts the result to Discord.

## Setup

1. Import `weekly-dev-summary.workflow.json` into n8n.
2. Set environment variables: `GITHUB_REPO=owner/repo`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `DISCORD_WEBHOOK_URL`, and optional `SUMMARY_LANGUAGE=EN` or `FR`.
3. Open the imported workflow and confirm the Friday 5pm schedule and UTC timezone.
4. Execute once manually in n8n to verify the GitHub, Claude, and Discord calls.
5. Activate the workflow.

## Configuration

- `GITHUB_REPO`: repository to summarize, for example `n8n-io/n8n`
- `GITHUB_TOKEN`: GitHub token with public repo read access, or private repo read access if needed
- `ANTHROPIC_API_KEY`: Claude API key used by the Anthropic Messages API node
- `DISCORD_WEBHOOK_URL`: destination webhook for the generated summary
- `SUMMARY_LANGUAGE`: `EN` or `FR`

## Validation

Local validation completed before PR:

- JSON parse validation
- Workflow shape validation for required n8n node types
- Code-node syntax validation
- Acceptance regression coverage with `node workflows/n8n-weekly-dev-summary/tests/validate-workflow.mjs`
- Live GitHub API dry run against `n8n-io/n8n`: 100 commits, 74 closed issues, and 260 merged PRs were fetched for the rolling seven-day window and converted into a Claude request

No secrets are included in this workflow. Tokens and destination URLs are read from n8n environment variables.

## Reviewer Checks

Run:

```bash
node workflows/n8n-weekly-dev-summary/tests/validate-workflow.mjs
git diff --check
```

The validator verifies the importable workflow JSON, Friday 5pm schedule, GitHub commits/issues/PR fetch logic, Claude `claude-sonnet-4-20250514` request, Discord delivery, EN/FR configuration, five-step README, node JavaScript syntax, connection order, and secret hygiene.
