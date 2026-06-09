#!/usr/bin/env bash
set -uo pipefail

payload="$(cat)"

if [[ -z "${payload//[[:space:]]/}" ]]; then
  exit 0
fi

compact_payload="$(printf '%s' "$payload" | tr '\n' ' ')"

extract_json_string() {
  local key="$1"
  printf '%s' "$compact_payload" |
    sed -nE "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"((\\\\.|[^\"\\\\])*)\".*/\\1/p" |
    sed -E 's/\\"/"/g; s/\\\\/\\/g'
}

tool_name="$(extract_json_string tool_name)"
if [[ -n "$tool_name" && "$tool_name" != "Bash" ]]; then
  exit 0
fi

command="$(extract_json_string command)"
if [[ -z "$command" ]]; then
  exit 0
fi

project_path="$(extract_json_string cwd)"
if [[ -z "$project_path" ]]; then
  project_path="$(extract_json_string project_path)"
fi
if [[ -z "$project_path" ]]; then
  project_path="${CLAUDE_PROJECT_DIR:-$(pwd)}"
fi

lower_command="$(printf '%s' "$command" | tr '[:upper:]' '[:lower:]')"
reason=""
sql_runner_pattern='(^|[[:space:];&|])(psql|mysql|sqlite3|sqlcmd)[[:space:]]'
bare_sql_pattern='(^|[;&|])[[:space:]]*(drop[[:space:]]+table|delete[[:space:]]+from|truncate[[:space:]]+[^-[:space:]])'
force_config_pattern='git[[:space:]][^;&|]*-c[[:space:]]+push[.]force=[^;&|]*push'
force_plus_ref_pattern='git[[:space:]]+push[[:space:]][^;&|]*[[:space:]][+][^[:space:];&|]+'
reset_hard_pattern='(^|[[:space:];&|])git[[:space:]]+reset[[:space:]]+--hard($|[[:space:];&|])'
dd_device_pattern='(^|[[:space:];&|])dd[[:space:]][^;&|]*of=/dev/'
block_device_pattern='(^|[[:space:];&|])(mkfs|wipefs)([.]|[[:space:]])'
sql_execution_context=false
if [[ "$lower_command" =~ $sql_runner_pattern ]] || [[ "$lower_command" =~ $bare_sql_pattern ]]; then
  sql_execution_context=true
fi

if [[ "$lower_command" =~ (^|[[:space:]\;\&\|])rm[[:space:]]+-[[:alnum:]_-]*r[[:alnum:]_-]*f[[:alnum:]_-]*($|[[:space:]]) ]] ||
   [[ "$lower_command" =~ (^|[[:space:]\;\&\|])rm[[:space:]]+-[[:alnum:]_-]*f[[:alnum:]_-]*r[[:alnum:]_-]*($|[[:space:]]) ]] ||
   [[ "$lower_command" =~ (^|[[:space:]\;\&\|])rm[[:space:]]+-[[:alnum:]_-]*r[[:alnum:]_-]*[[:space:]]+-[[:alnum:]_-]*f[[:alnum:]_-]*($|[[:space:]]) ]] ||
   [[ "$lower_command" =~ (^|[[:space:]\;\&\|])rm[[:space:]]+-[[:alnum:]_-]*f[[:alnum:]_-]*[[:space:]]+-[[:alnum:]_-]*r[[:alnum:]_-]*($|[[:space:]]) ]] ||
   [[ "$lower_command" =~ (^|[[:space:]\;\&\|])rm[[:space:]][^\;\&\|]*(--recursive|-[[:alnum:]_-]*r)[^\;\&\|]*(--force|-[[:alnum:]_-]*f) ]] ||
   [[ "$lower_command" =~ (^|[[:space:]\;\&\|])rm[[:space:]][^\;\&\|]*(--force|-[[:alnum:]_-]*f)[^\;\&\|]*(--recursive|-[[:alnum:]_-]*r) ]]; then
  reason="rm -rf recursive deletion"
elif [[ "$sql_execution_context" == true && "$lower_command" =~ drop[[:space:]]+table ]]; then
  reason="DROP TABLE statement"
elif [[ "$sql_execution_context" == true && "$lower_command" =~ (^|[[:space:]\;\&\|])truncate($|[[:space:]\;\&\|]) ]]; then
  reason="TRUNCATE statement"
elif [[ "$lower_command" =~ git[[:space:]]+push([^;\&\|])*--force([^[:alnum:]_-]|$) ]] ||
     [[ "$lower_command" =~ git[[:space:]]+push([^;\&\|])*--force-with-lease([^[:alnum:]_-]|$) ]] ||
     [[ "$lower_command" =~ git[[:space:]]+push([^;\&\|])*-f($|[[:space:]]) ]] ||
     [[ "$lower_command" =~ $force_config_pattern ]] ||
     [[ "$lower_command" =~ $force_plus_ref_pattern ]]; then
  reason="force push"
elif [[ "$sql_execution_context" == true && "$lower_command" =~ delete[[:space:]]+from ]] && [[ ! "$lower_command" =~ where ]]; then
  reason="DELETE FROM without WHERE clause"
elif [[ "$lower_command" =~ $reset_hard_pattern ]]; then
  reason="git reset --hard"
elif [[ "$lower_command" =~ $dd_device_pattern ]] ||
     [[ "$lower_command" =~ $block_device_pattern ]]; then
  reason="block device destruction"
elif { [[ "$lower_command" == *curl* ]] || [[ "$lower_command" == *wget* ]]; } &&
     [[ "$lower_command" == *"|"* ]] &&
     { [[ "$lower_command" == *bash* ]] || [[ "$lower_command" == *" sh"* ]] || [[ "$lower_command" == *"|sh"* ]]; }; then
  reason="remote script execution"
fi

if [[ -z "$reason" ]]; then
  exit 0
fi

json_escape() {
  sed -E 's/\\/\\\\/g; s/"/\\"/g' <<< "$1" | tr -d '\n'
}

log_path="${CLAUDE_HOOKS_LOG_PATH:-$HOME/.claude/hooks/blocked.log}"
mkdir -p "$(dirname "$log_path")"
timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
printf '{"timestamp":"%s","command":"%s","project_path":"%s","reason":"%s"}\n' \
  "$(json_escape "$timestamp")" \
  "$(json_escape "$command")" \
  "$(json_escape "$project_path")" \
  "$(json_escape "$reason")" >> "$log_path"

message="Blocked destructive Bash command: $reason. Review the command and rerun only if this destructive action is intentional and safe."
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' \
  "$(json_escape "$message")"
exit 0
