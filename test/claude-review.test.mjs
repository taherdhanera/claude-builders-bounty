import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  analyzePullRequest,
  formatMarkdown,
  parseArgs,
  parsePullRequestUrl,
} from "../bin/claude-review.mjs";

const fixture = {
  ref: {
    owner: "example",
    repo: "app",
    number: 42,
    url: "https://github.com/example/app/pull/42",
  },
  pr: {
    number: 42,
    title: "Add billing webhook",
    user: { login: "octocat" },
  },
  files: [
    {
      filename: "app/api/billing/route.ts",
      additions: 80,
      deletions: 12,
      patch: "+const token = process.env.STRIPE_WEBHOOK_SECRET;\n+export async function POST() {}",
    },
    {
      filename: "tests/billing-webhook.test.ts",
      additions: 45,
      deletions: 0,
      patch: "+test('handles webhook', () => {})",
    },
    {
      filename: ".github/workflows/review.yml",
      additions: 22,
      deletions: 0,
      patch: "+permissions:\n+  pull-requests: write",
    },
  ],
};

test("parses GitHub PR URLs", () => {
  assert.deepEqual(
    parsePullRequestUrl("https://github.com/acme/project/pull/123"),
    {
      owner: "acme",
      repo: "project",
      number: 123,
      url: "https://github.com/acme/project/pull/123",
    }
  );
});

test("parses max-files option", () => {
  assert.deepEqual(
    parseArgs(["--pr", "https://github.com/acme/project/pull/123", "--max-files", "10"]),
    {
      pr: "https://github.com/acme/project/pull/123",
      format: "markdown",
      "max-files": 10,
    }
  );
});

test("analyzes diff metadata into required review sections", () => {
  const review = analyzePullRequest(fixture);

  assert.equal(review.pullRequest.title, "Add billing webhook");
  assert.equal(review.stats.changedFiles, 3);
  assert.equal(review.stats.testFiles, 1);
  assert.equal(review.confidence, "Medium");
  assert.match(review.risks.join("\n"), /workflow files changed/i);
  assert.match(review.risks.join("\n"), /credential-like terms/i);
});

test("detects shell code and shell test files", () => {
  const review = analyzePullRequest({
    ref: {
      owner: "example",
      repo: "hooks",
      number: 7,
      url: "https://github.com/example/hooks/pull/7",
    },
    pr: {
      number: 7,
      title: "Add command hook",
      user: { login: "hook-author" },
    },
    files: [
      {
        filename: "hooks/block_destructive_bash.sh",
        additions: 30,
        deletions: 0,
        patch: "+case \"$1\" in rm*) exit 2;; esac",
      },
      {
        filename: "hooks/test_block_destructive_bash.sh",
        additions: 20,
        deletions: 0,
        patch: "+bash hooks/block_destructive_bash.sh",
      },
    ],
  });

  assert.equal(review.stats.codeFiles, 2);
  assert.equal(review.stats.testFiles, 1);
});

test("formats structured markdown review", () => {
  const markdown = formatMarkdown(analyzePullRequest(fixture));

  assert.match(markdown, /^# Claude PR Review/);
  assert.match(markdown, /## Summary/);
  assert.match(markdown, /## Identified Risks/);
  assert.match(markdown, /## Improvement Suggestions/);
  assert.match(markdown, /## Confidence: Medium/);
});

test("bundled real PR samples include required review sections", async () => {
  const samplePaths = [
    "sample-outputs/claude-builders-2271.md",
    "sample-outputs/claude-builders-2277.md",
    "sample-outputs/claude-builders-2284.md",
  ];

  assert.equal(samplePaths.length, 3);

  for (const samplePath of samplePaths) {
    const markdown = await readFile(samplePath, "utf8");

    assert.match(markdown, /^# Claude PR Review/);
    assert.match(markdown, /## Summary/);
    assert.match(markdown, /## Identified Risks/);
    assert.match(markdown, /## Improvement Suggestions/);
    assert.match(markdown, /## Confidence: (Low|Medium|High)/);
  }
});

test("write-enabled workflow executes only trusted base code", async () => {
  const workflow = await readFile(".github/workflows/claude-review.yml", "utf8");

  assert.match(workflow, /^\s*pull_request_target:/m);
  assert.match(workflow, /ref:\s*\$\{\{\s*github\.event\.repository\.default_branch\s*\}\}/);
  assert.match(workflow, /persist-credentials:\s*false/);
  assert.doesNotMatch(workflow, /github\.event\.pull_request\.(head|merge_commit_sha)/);
  assert.doesNotMatch(workflow, /^\s*pull_request:\s*$/m);
});
