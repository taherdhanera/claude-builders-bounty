# Workflows

This directory contains importable automation workflows submitted for Claude Builders bounties.

## n8n Weekly GitHub Summary

- Bounty: #5
- Workflow: `n8n-weekly-dev-summary/weekly-dev-summary.workflow.json`
- Setup guide: `n8n-weekly-dev-summary/README.md`
- Local validation: `npm run test:n8n-weekly-summary`

The workflow is intentionally self-contained: secrets are read from n8n environment variables, and the repository includes validators for workflow shape, schedule, GitHub fetch coverage, Claude request generation, Discord delivery, README setup instructions, and a deterministic greenfield smoke sample.
