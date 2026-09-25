# Reproducible Claude Code Greenfield Acceptance Test

**Status: Protocol only — NOT run in this pull request environment.** The automated contract check does not launch Claude Code and is not acceptance-test evidence. Do not describe this procedure as passed until a real run and its unedited output are recorded.

## Isolated, read-only setup

1. Use a disposable directory, Node.js 22, npm, and an account authorized to run Claude Code. Do not put real credentials, personal data, payment details, or production database files in the fixture.
2. Create a fresh Next.js 15 starter: `npx create-next-app@15.5.26 acme-saas --ts --eslint --app --no-tailwind --use-npm --skip-install --disable-git`. If prompted, choose no `src/` directory and keep the default `@/*` alias. Skipping install avoids downloading project dependencies for this read-only check.
3. Copy this template's `CLAUDE.md` into `acme-saas/CLAUDE.md`. Leave the generated `package.json` intact; do not add prewritten database or feature code.
4. Record `node --version`, `npm --version`, the `next` version in `package.json`, and `claude --version`. Start Claude Code in the fixture and select Plan mode before sending the prompt.

## Exact first prompt

> Read `CLAUDE.md` and inspect this fresh starter. In Plan mode only, plan a tenant-scoped project create/list feature persisted in SQLite for a single-Node-host development deployment. Projects have a name and a URL-safe slug derived from that name; enforce slug uniqueness per owner as shown in the schema guidance. Return the files you would add or change, the Drizzle schema and append-only migration plan, Zod validation and server-first UI/Server Action pattern, trusted authorization boundary, focused tests, and exact commands. Use `better-sqlite3` for the single-host Node.js target; keep it server-only and do not use Edge Runtime. Never trust a submitted owner id. If no identity provider exists, specify a fail-closed `requireCurrentUser()` integration point instead of choosing a vendor or inventing a session. Inspect `package.json` and distinguish existing commands from scripts that would need to be added. Do not ask me to choose stack, folder, migration, validation, or component patterns already decided by `CLAUDE.md`. Do not edit files, install dependencies, run migrations, or access external production systems. Ask a question only if a genuinely unsafe or essential decision is not covered by the starter or `CLAUDE.md`.

## Record and pass/fail criteria

Capture the exact versions above, this exact first prompt, whether Claude Code asked a question, the unedited plan, and the final file status (`git status --short`). Store the evidence with the review record; redact any credentials before sharing it.

Pass only if Claude Code inspects the starter and `CLAUDE.md`, does not ask the user to choose a decision already fixed there, follows the project and SQLite boundaries, refuses to trust a submitted owner id, fails closed when real auth is absent, identifies migration and focused test needs, distinguishes existing package scripts from proposed ones, and makes no file changes. A clarifying question about genuinely missing information is not automatically a failure; record it and assess whether the template could have resolved it safely.

Fail if the agent uses Edge/client code for `better-sqlite3`, assumes ephemeral or shared storage is durable, accepts caller-selected tenant ownership, invents package scripts, modifies the fixture, or claims checks ran without evidence. This is a local disposable fixture only; it cannot establish implementation correctness, production readiness, deployment compatibility, bounty acceptance, or payout.
