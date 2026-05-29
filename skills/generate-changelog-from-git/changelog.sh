#!/usr/bin/env bash
set -euo pipefail

output_path="${1:-CHANGELOG.md}"
today="${CHANGELOG_DATE:-$(date -u +%Y-%m-%d)}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "changelog.sh must be run inside a git repository" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
repo_name="$(basename "$repo_root")"
latest_tag="$(git describe --tags --abbrev=0 2>/dev/null || true)"

if [[ -n "$latest_tag" ]]; then
  range="$latest_tag..HEAD"
  range_label="since $latest_tag"
else
  range="HEAD"
  range_label="repository history"
fi

commit_count="$(git rev-list --count "$range" 2>/dev/null || echo 0)"

added_file="$(mktemp)"
fixed_file="$(mktemp)"
changed_file="$(mktemp)"
removed_file="$(mktemp)"
trap 'rm -f "$added_file" "$fixed_file" "$changed_file" "$removed_file"' EXIT

append_entry() {
  local file="$1"
  local hash="$2"
  local subject="$3"
  printf -- '- %s (`%s`)\n' "$subject" "$(printf '%s' "$hash" | cut -c1-7)" >> "$file"
}

categorize_subject() {
  local subject="$1"
  local lower
  lower="$(printf '%s' "$subject" | tr '[:upper:]' '[:lower:]')"

  case "$lower" in
    feat:*|feat\(*|feature:*|add:*|added:*|initial\ commit*|initial:*)
      printf '%s' "Added"
      ;;
    fix:*|fix\(*|bug:*|bugfix:*|repair:*|hotfix:*)
      printf '%s' "Fixed"
      ;;
    remove:*|removed:*|delete:*|deleted:*|drop:*|dropped:*|deprecate:*|deprecated:*)
      printf '%s' "Removed"
      ;;
    change:*|changed:*|refactor:*|refactor\(*|docs:*|doc:*|style:*|perf:*|test:*|tests:*|build:*|ci:*|chore:*|revert:*)
      printf '%s' "Changed"
      ;;
    *)
      if [[ "$lower" =~ (^|[[:space:]])(fix|fixed|bug|repair|patch)([[:space:]]|$) ]]; then
        printf '%s' "Fixed"
      elif [[ "$lower" =~ (^|[[:space:]])(remove|removed|delete|deleted|drop|dropped)([[:space:]]|$) ]]; then
        printf '%s' "Removed"
      elif [[ "$lower" =~ (^|[[:space:]])(add|added|create|created|new|introduce|introduced)([[:space:]]|$) ]]; then
        printf '%s' "Added"
      else
        printf '%s' "Changed"
      fi
      ;;
  esac
}

while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  hash="${line%% *}"
  subject="${line#* }"
  category="$(categorize_subject "$subject")"
  case "$category" in
    Added) append_entry "$added_file" "$hash" "$subject" ;;
    Fixed) append_entry "$fixed_file" "$hash" "$subject" ;;
    Removed) append_entry "$removed_file" "$hash" "$subject" ;;
    *) append_entry "$changed_file" "$hash" "$subject" ;;
  esac
done < <(git log "$range" --reverse --format='%H %s')

write_section() {
  local title="$1"
  local file="$2"
  if [[ -s "$file" ]]; then
    printf '\n### %s\n\n' "$title"
    cat "$file"
  fi
}

{
  printf '# Changelog\n\n'
  printf '## [%s] - %s\n\n' "${CHANGELOG_VERSION:-Unreleased}" "$today"
  printf '_Generated for `%s` from %s._\n' "$repo_name" "$range_label"

  if [[ "$commit_count" -eq 0 ]]; then
    printf '\nNo commits found for this range.\n'
  else
    write_section "Added" "$added_file"
    write_section "Fixed" "$fixed_file"
    write_section "Changed" "$changed_file"
    write_section "Removed" "$removed_file"
  fi
} > "$output_path"

printf 'Wrote %s from %s commits in %s\n' "$output_path" "$commit_count" "$range_label"
