# CLAUDE.md - Next.js 15 + SQLite SaaS

Use this file as the operating contract for a greenfield SaaS product built with Next.js 15 App Router, React 19, TypeScript, and SQLite through either `better-sqlite3` for a single-node deployment or Turso/libSQL for hosted edge SQLite.

The goal is a small production system that is easy to reason about: server-first UI, explicit data access, boring migrations, predictable auth, and no hidden client-side business logic.

## Stack And Versions

- Next.js 15 App Router with React 19 and TypeScript strict mode.
  Reason: App Router gives server components, route handlers, metadata, layouts, and streaming in one model; strict TypeScript catches data-contract drift before runtime.

- SQLite is the system of record. Use `better-sqlite3` for local VPS or single-region apps; use Turso/libSQL when the product needs hosted replicas.
  Reason: SQLite keeps the MVP simple, cheap, and reliable while still supporting real relational constraints.

- Use Drizzle ORM for schema, migrations, and typed queries.
  Reason: Drizzle keeps SQL visible and migration files reviewable; avoid ORMs that hide query shape or create opaque runtime behavior.

- Use Server Actions for trusted writes and Route Handlers only for external integrations or public APIs.
  Reason: Server Actions keep form mutations close to the UI, while Route Handlers are better for webhooks, API clients, and machine-to-machine calls.

- Use Zod at every boundary: forms, search params, route handler bodies, webhook payloads, and environment variables.
  Reason: external input is not typed even when TypeScript compiles.

- Use one UI system, preferably shadcn/ui plus Tailwind CSS.
  Reason: one component vocabulary prevents inconsistent SaaS screens and reduces design drift.

- Use Vitest or Node test for pure units, Playwright for user flows, and targeted integration tests for database writes.
  Reason: most regressions in this stack happen at boundaries: forms, auth, database, and redirects.

## Project Structure

Use this structure unless the task explicitly requires a better local pattern:

```text
app/
  (marketing)/
    page.tsx
  (app)/
    dashboard/
      page.tsx
    settings/
      page.tsx
  api/
    webhooks/
      stripe/
        route.ts
  layout.tsx
  globals.css
middleware.ts
components/
  ui/
  forms/
  layout/
db/
  client.ts
  schema.ts
  migrations/
features/
  auth/
    actions.ts
    queries.ts
    validators.ts
  billing/
    actions.ts
    queries.ts
    validators.ts
  projects/
    actions.ts
    queries.ts
    validators.ts
lib/
  env.ts
  auth.ts
  dates.ts
  ids.ts
  result.ts
tests/
  integration/
  e2e/
```

Rules:

- Keep route files thin. `page.tsx`, `layout.tsx`, and `route.ts` may orchestrate, but business rules live in `features/*`.
  Reason: thin routes make it possible to test product behavior without rendering the whole app.

- Put feature-specific reads in `features/<feature>/queries.ts` and writes in `features/<feature>/actions.ts`.
  Reason: separating reads and writes makes caching, authorization, and transaction boundaries easier to audit.

- Put reusable primitives in `lib/`, not product behavior.
  Reason: `lib/` should stay stable; product rules change with the feature.

- Keep `components/ui` generic and keep product-aware components under `features` or `components/forms`.
  Reason: generic UI should not import database, auth, billing, or feature-specific rules.

- Keep `middleware.ts` limited to request routing, auth redirects, and coarse guards.
  Reason: middleware runs before routes and should not contain product writes, database mutations, or billing logic.

## Naming Conventions

- Files use kebab-case except React components, which export PascalCase functions.
  Reason: kebab-case paths are URL-safe and readable across operating systems.

- Database tables use plural snake_case: `users`, `projects`, `billing_events`.
  Reason: snake_case matches SQL convention and avoids quoted identifiers.

- TypeScript variables use camelCase; database columns use snake_case and are mapped at the query edge if needed.
  Reason: each layer keeps its native convention without leaking into the other.

- Server Actions are named as commands: `createProject`, `archiveProject`, `updateBillingEmail`.
  Reason: command names make writes explicit in reviews.

- Read functions are named as queries: `getProjectById`, `listUserProjects`, `findActiveSubscription`.
  Reason: query names should reveal cardinality and filtering.

- Zod schemas end in `Schema`, inferred types end in `Input`.
  Reason: reviewers can see which type comes from untrusted input.

## Environment Rules

- All environment access goes through `lib/env.ts`.
  Reason: direct `process.env` reads scatter defaults and make deployments fragile.

- Validate env at startup with Zod and fail fast for missing production secrets.
  Reason: a broken deployment should fail before accepting traffic.

- Never default production secrets, webhook secrets, database URLs, or auth keys.
  Reason: silent defaults create real security incidents.

Example:

```ts
import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  DATABASE_URL: z.string().min(1),
  AUTH_SECRET: z.string().min(32),
  STRIPE_WEBHOOK_SECRET: z.string().optional(),
});

export const env = envSchema.parse(process.env);
```

## Database And Migration Rules

- Schema changes require a migration file in `db/migrations/`.
  Reason: production data must move through reviewed, repeatable steps.

- Migrations are append-only after they have been merged.
  Reason: rewriting applied migrations breaks other developers and deployments.

- Use explicit `created_at` and `updated_at` columns on mutable business tables.
  Reason: SaaS support, billing, and audits need timelines.

- Use foreign keys and unique indexes for product invariants.
  Reason: application checks can race; database constraints cannot be skipped by another code path.

- Use transactions for multi-table writes.
  Reason: partial writes create support tickets and inconsistent billing state.

- Do not use `db.run` or raw SQL inline in React components.
  Reason: database access belongs in query/action modules where auth and transactions can be enforced.

- For Turso/libSQL, design for network latency and avoid chatty query loops.
  Reason: edge-hosted SQLite is fast when calls are batched and predictable.

Migration example:

```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(owner_id, slug)
);
```

## Data Access Pattern

- Every query accepts the current actor or a verified account id when authorization matters.
  Reason: authorization must be part of the data access contract, not a caller memory test.

- Return plain objects from query modules.
  Reason: server components, actions, and tests should not depend on ORM-specific result wrappers.

- Use explicit column lists instead of `select *`.
  Reason: adding sensitive columns later should not leak into old API responses.

- Convert database `null` into product-level state intentionally.
  Reason: nullable data causes most SaaS edge-case bugs when it is passed through blindly.

## Auth And Authorization

- Authentication proves who the user is; authorization decides what they may do. Implement them as separate helpers.
  Reason: mixing them makes admin and account-boundary bugs easier to introduce.

- Every organization-scoped query checks membership in the same transaction or query path.
  Reason: dashboard data must not leak across accounts.

- Admin routes require both a valid session and an explicit role or permission check.
  Reason: "logged in" is not the same as "platform operator".

- Webhooks never trust client-submitted ids without verifying provider signatures.
  Reason: billing and provisioning flows are high-impact and easy to spoof.

- Prefer capability checks such as `canManageProject(user, project)` over scattered role comparisons.
  Reason: SaaS permissions become more complex as teams, billing, and invited users are added.

## Server And Client Component Rules

- Default to Server Components.
  Reason: server-first pages reduce JavaScript shipped to users and keep secrets off the client.

- Mark a component with `"use client"` only for local interactivity, browser APIs, controlled inputs, or client-side state.
  Reason: client components expand bundle size and cannot safely access server-only modules.

- Never import `db`, `env`, payment SDKs, or server auth helpers from a client component.
  Reason: these imports either fail at build time or risk exposing implementation details.

- Keep forms progressive: render server data first, submit through a Server Action, and show optimistic UI only after the server path exists.
  Reason: optimistic-only flows hide validation, authorization, and persistence bugs.

## Server Actions

- Server Actions validate input with Zod before touching the database.
  Reason: browser forms and malicious requests can submit anything.

- Server Actions return a typed result object for expected validation failures and throw only for unexpected system errors.
  Reason: predictable failures should produce user-facing messages, not error boundaries.

- Redirect only after the write succeeds.
  Reason: redirecting before commit creates confusing false-success states.

- Revalidate the smallest useful path or tag after writes.
  Reason: broad invalidation hides stale-data bugs and wastes server work.

Example:

```ts
"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createProjectRecord } from "./queries";

const createProjectSchema = z.object({
  name: z.string().min(2).max(80),
});

export async function createProject(formData: FormData) {
  const input = createProjectSchema.safeParse({
    name: formData.get("name"),
  });

  if (!input.success) {
    return { ok: false as const, message: "Enter a project name." };
  }

  const project = await createProjectRecord(input.data);
  revalidatePath("/dashboard");
  return { ok: true as const, projectId: project.id };
}
```

## Route Handlers And APIs

- Route Handlers are for webhooks, public API clients, file uploads, and integrations.
  Reason: normal app form writes are clearer as Server Actions.

- Validate method, auth, input, and response shape in every route.
  Reason: API consumers depend on stable contracts.

- Use idempotency keys for billing, provisioning, and webhook handlers.
  Reason: providers retry requests and users double-submit forms.

- Never return internal errors, stack traces, SQL text, or provider secrets.
  Reason: public APIs are a common information-disclosure surface.

## UI And Product Patterns

- Dashboards should show real next actions, not marketing copy.
  Reason: SaaS users return to operate the product, not to reread value propositions.

- Empty states include one primary action.
  Reason: empty SaaS screens are onboarding moments.

- Tables need loading, empty, error, and filtered states.
  Reason: operational tools are used repeatedly and must stay predictable.

- Use cards for repeated entities, dialogs, and framed tools; do not nest cards.
  Reason: nested cards make dashboards visually noisy and harder to scan.

- Keep text and controls compact in app screens.
  Reason: SaaS dashboards should optimize for scanning, comparison, and repeated actions.

## Error Handling

- Expected validation failures return typed results.
  Reason: users need actionable feedback without crashing the route.

- Unexpected failures are logged server-side with a request id.
  Reason: support needs traceability without exposing internals to the client.

- Add a route-level error boundary for app sections that call external providers.
  Reason: billing, email, and AI integrations fail independently from the core app.

## Testing Rules

- Add a test for every bug fix.
  Reason: the bug already proved the old behavior was possible.

- Test authorization boundaries with at least two users or organizations.
  Reason: single-user tests miss account leakage.

- Test database migrations on an empty database and on a seeded database when the migration touches existing data.
  Reason: migrations fail in production when they only work on clean schemas.

- For Server Actions, test invalid input, unauthorized access, and the successful write.
  Reason: those are the three production paths that matter.

- For Playwright flows, cover signup/login, main dashboard action, settings update, and billing handoff once those features exist.
  Reason: these flows determine whether the SaaS can onboard and retain users.

## Commands

Use these scripts in `package.json`:

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit",
    "lint": "next lint",
    "test": "vitest run",
    "test:e2e": "playwright test",
    "db:generate": "drizzle-kit generate",
    "db:migrate": "drizzle-kit migrate",
    "db:studio": "drizzle-kit studio",
    "check": "npm run typecheck && npm run lint && npm run test && npm run build"
  }
}
```

Rules:

- Run `npm run check` before opening a PR.
  Reason: type, lint, test, and build failures are cheaper locally than in review.

- Run `npm run db:generate` after editing schema and commit the migration.
  Reason: schema and migrations must stay in sync.

- Do not add a new package manager unless the repo already uses it.
  Reason: mixed lockfiles create nondeterministic installs.

## Pull Request Rules

- PRs include summary, validation commands, migration notes, and screenshots for UI changes.
  Reason: reviewers need evidence, not intent.

- Keep PRs scoped to one product behavior or infrastructure change.
  Reason: small PRs are easier to merge and revert.

- Include rollback notes for migrations and billing changes.
  Reason: production SaaS work must be reversible or at least recoverable.

## What We Do Not Do

- Do not put business logic in React components.
  Reason: product rules need tests and should not depend on rendering.

- Do not use client-side checks as the only authorization layer.
  Reason: users can bypass the browser.

- Do not use `any` to silence type errors.
  Reason: `any` hides exactly the contract problems TypeScript is meant to catch.

- Do not create global mutable state for request-specific data.
  Reason: server runtimes can reuse modules across users.

- Do not expose database ids in logs when a public correlation id is enough.
  Reason: logs often reach third-party systems.

- Do not add background jobs without an idempotency strategy.
  Reason: retries and duplicate delivery are normal in production.

- Do not build custom auth, crypto, billing ledgers, or migration runners unless explicitly required.
  Reason: these domains are expensive to get right and have proven tools.

- Do not optimize for multi-region writes before there is real traffic pressure.
  Reason: SQLite is strongest when the write path stays simple.

- Do not create generic abstractions before two real features need them.
  Reason: premature abstraction slows MVP development and hides product intent.

## Agent Workflow

When changing this project:

1. Identify the user-facing behavior or production risk first.
2. Locate the route, feature module, schema, and tests that own it.
3. Make the smallest coherent change.
4. Add or update validation at the closest boundary.
5. Run the relevant test first, then `npm run check` when the change is broad.
6. In the final response, report files changed, validation run, and any residual risk.

If requirements are ambiguous, choose the safer production behavior and document the assumption in the PR. Do not pause for clarification unless the wrong assumption could cause data loss, payment errors, or a security issue.

## Greenfield Smoke Test

This template was reviewed against a blank Next.js 15 + SQLite SaaS setup path:

1. `npx create-next-app@latest acme-saas --ts --app`
2. Add SQLite/Drizzle files using the structure above.
3. Place this file at the project root as `CLAUDE.md`.
4. Ask Claude Code to add a project creation form backed by SQLite.

Expected behavior: Claude Code should infer the folder structure, create a migration, validate form input with Zod, keep the page server-first, implement a Server Action, add a focused test, and report validation commands without asking which stack, folder layout, migration style, or component pattern to use.

Executable verifier: run `bash templates/nextjs-sqlite-saas/tests/smoke-greenfield.sh` from the repository root to copy this template into a temporary greenfield tree and verify that the required sections, SQLite conventions, Route Handler guidance, auth boundary rules, testing rules, and no-clarifying-questions instruction are present after copy.
