#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$script_dir/block_destructive_bash.sh"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

run_hook() {
  local command="$1"
  local tool_name="${2:-Bash}"
  local payload
  payload="$(printf '{"tool_name":"%s","tool_input":{"command":"%s"},"cwd":"/tmp/project"}' "$tool_name" "$command")"
  CLAUDE_HOOKS_LOG_PATH="$tmpdir/blocked.log" bash "$hook" <<< "$payload" >"$tmpdir/stdout" 2>"$tmpdir/stderr"
}

expect_blocked() {
  local command="$1"
  local reason="$2"
  rm -f "$tmpdir/blocked.log" "$tmpdir/stdout" "$tmpdir/stderr"
  set +e
  run_hook "$command"
  status=$?
  set -e
  [[ "$status" -eq 0 ]] || { echo "Expected structured deny status for: $command"; exit 1; }
  grep -F '"hookSpecificOutput"' "$tmpdir/stdout" >/dev/null || { echo "Missing hookSpecificOutput"; exit 1; }
  grep -F '"hookEventName":"PreToolUse"' "$tmpdir/stdout" >/dev/null || { echo "Missing PreToolUse hook event"; exit 1; }
  grep -F '"permissionDecision":"deny"' "$tmpdir/stdout" >/dev/null || { echo "Missing deny decision"; exit 1; }
  grep -F "$reason" "$tmpdir/stdout" >/dev/null || { echo "Missing structured reason: $reason"; exit 1; }
  grep -F "\"reason\":\"$reason\"" "$tmpdir/blocked.log" >/dev/null || { echo "Missing log reason: $reason"; exit 1; }
  grep -F "\"project_path\":\"/tmp/project\"" "$tmpdir/blocked.log" >/dev/null || { echo "Missing project path"; exit 1; }
}

expect_allowed() {
  local command="$1"
  local tool_name="${2:-Bash}"
  rm -f "$tmpdir/blocked.log" "$tmpdir/stdout" "$tmpdir/stderr"
  run_hook "$command" "$tool_name"
  [[ ! -f "$tmpdir/blocked.log" ]] || { echo "Unexpected log for allowed command: $command"; exit 1; }
}

expect_blocked "rm -rf /tmp/demo" "rm -rf recursive deletion"
expect_blocked "git status && rm -fr build" "rm -rf recursive deletion"
expect_blocked "psql -c DROP TABLE users" "DROP TABLE statement"
expect_blocked "mysql -e TRUNCATE audit_log" "TRUNCATE statement"
expect_blocked "psql -c DELETE FROM users" "DELETE FROM without WHERE clause"
expect_blocked "DELETE FROM users" "DELETE FROM without WHERE clause"
expect_blocked "git push --force origin main" "force push"
expect_blocked "git push --force-with-lease origin main" "force push"

expect_allowed "psql -c DELETE FROM users WHERE id = 1"
expect_allowed "git status && echo DELETE FROM audit_log"
expect_allowed "truncate -s 0 notes.txt"
expect_allowed "grep -R \"DROP TABLE\" docs"
expect_allowed "git status && npm test"
expect_allowed "rm -rf /tmp/demo" "Read"

echo "All destructive command blocker tests passed."
