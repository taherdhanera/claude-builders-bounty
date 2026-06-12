# Verification

This submission is designed to be importable into n8n and independently checkable without external credentials.

## Local validation

Run from the repository root:

```bash
python workflows/issue-5-weekly-dev-summary/validate_workflow.py
```

Expected output:

```text
workflow validation passed
nodes=9
connections=8
delivery=discord
model=claude-sonnet-4-20250514
```

The validator checks the exported workflow shape, Friday 5pm schedule, GitHub commits/issues/pulls fetches, Claude Messages API model, Discord webhook delivery, EN/FR language configuration, and five-step README constraint.

## Live execution boundary

The workflow needs real `ANTHROPIC_API_KEY` and `WEEKLY_SUMMARY_DISCORD_WEBHOOK_URL` values to produce a live n8n execution screenshot. I did not fabricate that artifact from this environment.
