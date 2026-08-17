#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook_src="$script_dir/block_destructive_bash.sh"
hook_dst="$HOME/.claude/hooks/block_destructive_bash.sh"
settings_path="$HOME/.claude/settings.json"

mkdir -p "$(dirname "$hook_dst")" "$(dirname "$settings_path")"
cp "$hook_src" "$hook_dst"
chmod +x "$hook_dst"

if [[ -f "$settings_path" ]]; then
  cp "$settings_path" "$settings_path.bak"
fi

node -e '
  const fs = require("node:fs");
  const path = process.argv[1];
  const command = "bash ~/.claude/hooks/block_destructive_bash.sh";
  let settings = {};

  if (fs.existsSync(path)) {
    settings = JSON.parse(fs.readFileSync(path, "utf8"));
  }

  if (!settings.hooks || typeof settings.hooks !== "object" || Array.isArray(settings.hooks)) {
    settings.hooks = {};
  }
  if (!Array.isArray(settings.hooks.PreToolUse)) {
    settings.hooks.PreToolUse = [];
  }

  let bashMatcher = settings.hooks.PreToolUse.find(
    (entry) => entry && entry.matcher === "Bash" && Array.isArray(entry.hooks)
  );
  if (!bashMatcher) {
    bashMatcher = { matcher: "Bash", hooks: [] };
    settings.hooks.PreToolUse.push(bashMatcher);
  }

  if (!bashMatcher.hooks.some((hook) => hook?.type === "command" && hook.command === command)) {
    bashMatcher.hooks.push({ type: "command", command });
  }

  const temporaryPath = path + ".tmp";
  fs.writeFileSync(temporaryPath, JSON.stringify(settings, null, 2) + "\n", "utf8");
  fs.renameSync(temporaryPath, path);
' "$settings_path"

printf 'Installed destructive command blocker at %s and updated %s\n' "$hook_dst" "$settings_path"
