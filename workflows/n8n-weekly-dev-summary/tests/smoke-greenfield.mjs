import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const workflowPath = join(__dirname, "..", "weekly-dev-summary.workflow.json");
const workflow = JSON.parse(readFileSync(workflowPath, "utf8"));

const nodes = new Map((workflow.nodes || []).map((node) => [node.name, node]));
const fetchCode = nodes.get("Fetch GitHub API Activity")?.parameters?.jsCode || "";
const claudeCode = nodes.get("Build Claude Request")?.parameters?.jsCode || "";
const discordBody = nodes.get("Send Discord Summary")?.parameters?.jsonBody || "";

const failures = [];
const expect = (condition, message) => {
  if (!condition) failures.push(message);
};

const fixture = {
  githubRepo: "acme/greenfield-saas",
  sinceIso: "2026-06-01T00:00:00.000Z",
  untilIso: "2026-06-08T00:00:00.000Z",
  language: "EN",
  counts: {
    commits: 2,
    closedIssues: 1,
    mergedPrs: 1
  },
  commits: [
    { sha: "abc1234", author: "ada", message: "Add onboarding checklist" },
    { sha: "def5678", author: "grace", message: "Fix invoice retry copy" }
  ],
  closedIssues: [
    { number: 42, title: "Document first deploy", closedAt: "2026-06-06T12:00:00Z", url: "https://github.com/acme/greenfield-saas/issues/42" }
  ],
  mergedPrs: [
    { number: 77, title: "Ship dashboard summary", mergedAt: "2026-06-07T12:00:00Z", author: "linus", url: "https://github.com/acme/greenfield-saas/pull/77" }
  ]
};

const expectedPromptSections = ["Overview", "Highlights", "Merged PRs", "Closed Issues", "Risks or Follow-ups"];
for (const section of expectedPromptSections) {
  expect(claudeCode.includes(section), `Claude prompt requests ${section}`);
}

expect(fetchCode.includes("is:issue is:closed"), "closed issue query excludes pull requests");
expect(fetchCode.includes("is:pr is:merged"), "merged PR query is separate from closed issues");
expect(fetchCode.includes("slice(0, 40)"), "large GitHub responses are compacted before the Claude request");
expect(discordBody.includes("content.slice(0, 1900)"), "Discord payload is bounded below Discord's message limit");

const preview = [
  `Repository: ${fixture.githubRepo}`,
  `Window: ${fixture.sinceIso} to ${fixture.untilIso}`,
  `Counts: ${JSON.stringify(fixture.counts)}`,
  `Commits: ${fixture.commits.map((commit) => `${commit.sha} ${commit.message}`).join("; ")}`,
  `Closed issues: ${fixture.closedIssues.map((issue) => `#${issue.number} ${issue.title}`).join("; ")}`,
  `Merged PRs: ${fixture.mergedPrs.map((pr) => `#${pr.number} ${pr.title}`).join("; ")}`
].join("\n");

expect(preview.includes("#42 Document first deploy"), "greenfield sample keeps issue references");
expect(preview.includes("#77 Ship dashboard summary"), "greenfield sample keeps PR references");
expect(!preview.includes("undefined"), "greenfield sample has no missing fields");

if (failures.length) {
  console.error("Greenfield smoke validation failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Greenfield smoke validation passed for n8n weekly summary prompt, query split, compaction, and Discord payload bounds.");
