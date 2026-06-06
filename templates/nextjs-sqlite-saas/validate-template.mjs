#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const templatePath = join(here, "CLAUDE.md");
const template = readFileSync(templatePath, "utf8");

const requiredHeadings = [
  "# CLAUDE.md - Next.js 15 + SQLite SaaS",
  "## Stack And Versions",
  "## Project Structure",
  "## Naming Conventions",
  "## Environment Rules",
  "## Database And Migration Rules",
  "## Data Access Pattern",
  "## Auth And Authorization",
  "## Server And Client Component Rules",
  "## Server Actions",
  "## Route Handlers And APIs",
  "## UI And Product Patterns",
  "## Error Handling",
  "## Testing Rules",
  "## Commands",
  "## Pull Request Rules",
  "## What We Do Not Do",
  "## Agent Workflow",
  "## Greenfield Smoke Test",
];

const requiredTerms = [
  "Next.js 15",
  "SQLite",
  "better-sqlite3",
  "Turso",
  "Drizzle",
  "Server Actions",
  "Route Handlers",
  "Zod",
  "migrations",
  "greenfield",
  "Claude Code",
];

const errors = [];

for (const heading of requiredHeadings) {
  if (!template.includes(heading)) {
    errors.push(`Missing heading: ${heading}`);
  }
}

for (const term of requiredTerms) {
  if (!new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i").test(template)) {
    errors.push(`Missing required term: ${term}`);
  }
}

const reasonCount = (template.match(/\bReason:/g) || []).length;
if (reasonCount < 40) {
  errors.push(`Expected at least 40 reasoned rules, found ${reasonCount}`);
}

const numberedSmokeSteps = (template.match(/^\d+\.\s+/gm) || []).length;
if (numberedSmokeSteps < 4) {
  errors.push(`Expected at least 4 numbered greenfield smoke-test steps, found ${numberedSmokeSteps}`);
}

const codeFenceCount = (template.match(/^```/gm) || []).length;
if (codeFenceCount % 2 !== 0) {
  errors.push(`Unbalanced Markdown code fences: ${codeFenceCount}`);
}

if (!/Expected behavior:[\s\S]*Claude Code[\s\S]*without asking/i.test(template)) {
  errors.push("Missing explicit expected Claude Code greenfield behavior");
}

if (errors.length > 0) {
  console.error("CLAUDE.md template validation failed:");
  for (const error of errors) {
    console.error(`- ${error}`);
  }
  process.exit(1);
}

console.log(`CLAUDE.md template validation passed: ${requiredHeadings.length} headings, ${reasonCount} reasoned rules, ${numberedSmokeSteps} smoke-test steps.`);
