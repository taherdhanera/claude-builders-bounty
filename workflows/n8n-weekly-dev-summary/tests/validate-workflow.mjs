import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const workflowPath = join(__dirname, "..", "weekly-dev-summary.workflow.json");
const readmePath = join(__dirname, "..", "README.md");

const workflow = JSON.parse(readFileSync(workflowPath, "utf8"));
const readme = readFileSync(readmePath, "utf8");

const failures = [];
const expect = (condition, message) => {
  if (!condition) failures.push(message);
};

const nodes = new Map((workflow.nodes || []).map((node) => [node.name, node]));
const nodeNames = [...nodes.keys()];

expect(workflow.name === "Weekly GitHub Activity Summary with Claude", "workflow has a stable descriptive name");
expect(Array.isArray(workflow.nodes) && workflow.nodes.length === 7, "workflow contains the expected seven nodes");
expect(nodes.has("Friday 5pm Schedule"), "schedule trigger node exists");
expect(nodes.has("Build Weekly Config"), "configuration node exists");
expect(nodes.has("Fetch GitHub API Activity"), "GitHub activity node exists");
expect(nodes.has("Build Claude Request"), "Claude request builder node exists");
expect(nodes.has("Generate Claude Summary"), "Claude HTTP node exists");
expect(nodes.has("Prepare Discord Message"), "Discord message node exists");
expect(nodes.has("Send Discord Summary"), "Discord delivery node exists");

const schedule = nodes.get("Friday 5pm Schedule");
const scheduleExpression = schedule?.parameters?.rule?.interval?.[0]?.expression;
expect(schedule?.type === "n8n-nodes-base.scheduleTrigger", "schedule node uses n8n scheduleTrigger");
expect(scheduleExpression === "0 17 * * 5", "schedule runs every Friday at 17:00");

const configCode = nodes.get("Build Weekly Config")?.parameters?.jsCode || "";
expect(configCode.includes("$env.GITHUB_REPO"), "GITHUB_REPO is configurable");
expect(configCode.includes("$env.GITHUB_TOKEN"), "GITHUB_TOKEN is configurable");
expect(configCode.includes("$env.ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY is configurable");
expect(configCode.includes("$env.DISCORD_WEBHOOK_URL"), "DISCORD_WEBHOOK_URL is configurable");
expect(configCode.includes("$env.SUMMARY_LANGUAGE"), "SUMMARY_LANGUAGE is configurable");
expect(configCode.includes("'FR'") && configCode.includes("'EN'"), "language supports EN and FR");

const githubCode = nodes.get("Fetch GitHub API Activity")?.parameters?.jsCode || "";
expect(githubCode.includes("https://api.github.com"), "GitHub API base URL is used");
expect(githubCode.includes("/commits?"), "commits are fetched");
expect(githubCode.includes("is:issue is:closed"), "closed issues are fetched");
expect(githubCode.includes("is:pr is:merged"), "merged PRs are fetched");
expect(githubCode.includes("per_page=100"), "GitHub fetches request a useful page size");

const claudeCode = nodes.get("Build Claude Request")?.parameters?.jsCode || "";
expect(claudeCode.includes("claude-sonnet-4-20250514"), "Claude Sonnet 4 model is configured");
expect(claudeCode.includes("Overview") && claudeCode.includes("Merged PRs"), "Claude prompt requests a narrative engineering summary");

const claudeHttp = nodes.get("Generate Claude Summary");
expect(claudeHttp?.type === "n8n-nodes-base.httpRequest", "Claude call uses an HTTP request node");
expect(claudeHttp?.parameters?.url === "https://api.anthropic.com/v1/messages", "Claude Messages API endpoint is configured");

const discordHttp = nodes.get("Send Discord Summary");
expect(discordHttp?.type === "n8n-nodes-base.httpRequest", "Discord delivery uses an HTTP request node");
expect(discordHttp?.parameters?.method === "POST", "Discord delivery uses POST");
expect(String(discordHttp?.parameters?.url || "").includes("discordWebhookUrl"), "Discord webhook URL is read from workflow data");

const connectionOrder = [
  "Friday 5pm Schedule",
  "Build Weekly Config",
  "Fetch GitHub API Activity",
  "Build Claude Request",
  "Generate Claude Summary",
  "Prepare Discord Message",
  "Send Discord Summary",
];

for (let i = 0; i < connectionOrder.length - 1; i += 1) {
  const from = connectionOrder[i];
  const to = connectionOrder[i + 1];
  const targets = workflow.connections?.[from]?.main?.flat().map((entry) => entry.node) || [];
  expect(targets.includes(to), `${from} connects to ${to}`);
}

for (const node of workflow.nodes || []) {
  const code = node.parameters?.jsCode;
  if (code) {
    try {
      new vm.Script(`(async () => {\n${code}\n})`);
    } catch (error) {
      failures.push(`${node.name} contains invalid JavaScript: ${error.message}`);
    }
  }
}

const setupSteps = [...readme.matchAll(/^\d+\.\s+/gm)];
expect(setupSteps.length > 0 && setupSteps.length <= 5, "README setup instructions use five steps or fewer");
expect(readme.includes("weekly-dev-summary.workflow.json"), "README points to the importable workflow JSON");
expect(readme.includes("No secrets are included"), "README documents secret handling");

const serialized = JSON.stringify(workflow);
for (const forbidden of ["sk-ant-", "ghp_", "gho_", "discord.com/api/webhooks/"]) {
  expect(!serialized.includes(forbidden), `workflow does not include ${forbidden} secrets`);
}

if (failures.length) {
  console.error("Workflow validation failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Validated ${nodeNames.length} n8n nodes: ${nodeNames.join(" -> ")}`);
console.log("Acceptance checks passed: importable JSON, Friday 5pm trigger, GitHub fetch, Claude model, Discord delivery, EN/FR config, README step count, secret hygiene.");
