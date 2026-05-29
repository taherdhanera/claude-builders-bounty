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

cat > "$settings_path" <<'JSON'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/block_destructive_bash.sh"
          }
        ]
      }
    ]
  }
}
JSON

printf 'Installed destructive command blocker at %s and updated %s\n' "$hook_dst" "$settings_path"
