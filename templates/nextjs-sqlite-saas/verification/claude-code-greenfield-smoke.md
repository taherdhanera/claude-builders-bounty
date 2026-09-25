# Reproducible Claude Code Greenfield Acceptance Test

**Status: Protocol only — NOT run in this pull request environment.** The automated contract check does not launch Claude Code and is not acceptance-test evidence. Do not describe this procedure as passed until a real run and its unedited output are recorded.

## Isolated setup

1. Use a disposable directory, Node.js 22, npm, and an account authorized to run Claude Code. Do not put real credentials, personal data, payment details, or production database files in the fixture.
2. Create a fresh Next.js 15 starter: `npx create-next-app@15.5.26 acme-saas --ts --app`. Choose TypeScript, App Router, no `src/` directory, npm, and the default `@/*` import alias if the CLI asks.
3. Copy this template's `CLAUDE.md` into `acme-saas/CLAUDE.md`. Do not add prewritten database or feature code; the point is to test whether the instructions guide the agent from a real starter.
4. From `acme-saas/`, record `node --version`, `npm --version`, `npx next --version`, and `claude --version`; then start Claude Code in that directory.

## Exact first prompt

> Read `CLAUDE.md` and inspect this fresh starter. Implement a tenant-scoped project create/list feature persisted in SQLite for a single-Node-host development deployment. Projects have a name and a URL-safe slug derived from that name; enforce slug uniqueness per owner as shown in the schema guidance. Use the documented structure, Drizzle schema and append-only migration, Zod validation, server-first UI, Server Action, and focused tests. Use `better-sqlite3` for this local Node.js fixture; keep the database and credentials server-only, and do not use Edge Runtime. Never accept an owner id from the form: call a server-only `requireCurrentUser()` boundary. If this starter has no configured identity provider, make that boundary fail closed and report the auth integration point instead of choosing a vendor, inventing a session, or weakening authorization. Do not ask me to choose stack, folder, migration, validation, or component patterns already decided by `CLAUDE.md`. Before running a command, tell me what it does; do not run destructive commands or access external production systems. Implement the feature, run the relevant checks, and report exactly what passed, failed, or could not be run.

## Record and pass/fail criteria

Capture the exact versions above, this exact first prompt, whether Claude Code asked a question before implementation, the final response, changed-file list, and the literal output of each test command. Store the evidence with the review record; redact any credentials before sharing it.

Pass only if Claude Code does not ask the user to choose a decision already fixed by `CLAUDE.md`, follows the project and SQLite boundaries, refuses to trust a submitted owner id, fails closed when real auth is absent, creates/reviews a migration, adds focused tests, and accurately distinguishes executed checks from unrun checks. A clarifying question about genuinely missing information is not automatically a failure; record it and assess whether the template could have resolved it safely.

Fail if the agent uses Edge/client code for `better-sqlite3`, assumes ephemeral or shared storage is durable, accepts caller-selected tenant ownership, skips migration or tests while claiming success, or claims a check ran without evidence. This is a local disposable fixture only; it cannot establish production readiness, deployment compatibility, bounty acceptance, or payout.
