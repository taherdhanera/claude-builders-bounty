#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
template_dir="$repo_root/templates/nextjs-sqlite-saas"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "$tmp_dir/acme-saas/app" \
  "$tmp_dir/acme-saas/components" \
  "$tmp_dir/acme-saas/db/migrations" \
  "$tmp_dir/acme-saas/features/projects" \
  "$tmp_dir/acme-saas/lib" \
  "$tmp_dir/acme-saas/tests/integration"

cp "$template_dir/CLAUDE.md" "$tmp_dir/acme-saas/CLAUDE.md"

assert_contains() {
  local pattern="$1"
  local message="$2"

  if ! grep -Eq "$pattern" "$tmp_dir/acme-saas/CLAUDE.md"; then
    echo "Smoke check failed: $message" >&2
    exit 1
  fi
}

assert_contains '^# CLAUDE\.md - Next\.js 15 \+ SQLite SaaS$' "title missing"
assert_contains '^## Project Structure$' "project structure section missing"
assert_contains '^## Database And Migration Rules$' "database rules section missing"
assert_contains '^## Route Handlers And APIs$' "route handler section missing"
assert_contains '^## Auth And Authorization$' "auth section missing"
assert_contains '^## Testing Rules$' "testing section missing"
assert_contains 'middleware\.ts' "middleware placement missing"
assert_contains 'better-sqlite3|Turso|libSQL' "SQLite runtime choices missing"
assert_contains 'Server Actions' "Server Actions guidance missing"
assert_contains 'without asking which stack, folder layout, migration style, or component pattern to use' "no-clarifying-questions behavior missing"

reason_count="$(grep -Ec '\bReason:' "$tmp_dir/acme-saas/CLAUDE.md")"
if [ "$reason_count" -lt 41 ]; then
  echo "Smoke check failed: expected at least 41 reasoned rules, found $reason_count" >&2
  exit 1
fi

anti_pattern_count="$(awk '/^## What We Do Not Do/{flag=1; next} /^## Agent Workflow/{flag=0} flag && /^- Do not /{count++} END{print count+0}' "$tmp_dir/acme-saas/CLAUDE.md")"
if [ "$anti_pattern_count" -lt 9 ]; then
  echo "Smoke check failed: expected at least 9 anti-patterns, found $anti_pattern_count" >&2
  exit 1
fi

echo "Greenfield smoke check passed: copied CLAUDE.md into a blank Next.js-style tree; ${reason_count} reasoned rules and ${anti_pattern_count} anti-patterns verified."
