# Destructive Command Blocker Hook

Claude Code `PreToolUse` hook for Bash commands that blocks common destructive patterns before they run.

## Install

```bash
mkdir -p ~/.claude/hooks && cp hooks/destructive-command-blocker/block_destructive_bash.sh ~/.claude/hooks/block_destructive_bash.sh
bash hooks/destructive-command-blocker/install_settings.sh
```

## What It Blocks

- `rm -rf` and equivalent `rm -fr` flag combinations
- `DROP TABLE`
- `TRUNCATE`
- `git push --force` and `git push --force-with-lease`
- `DELETE FROM` statements that do not include a `WHERE` clause
- `git reset --hard`
- block-device destruction commands such as `dd of=/dev/*`, `mkfs`, and `wipefs`
- remote script execution through `curl | bash` or `wget | sh`

Blocked attempts are logged to `~/.claude/hooks/blocked.log` with:

- timestamp
- attempted command
- project path
- block reason

Normal Bash commands and non-Bash tool calls exit successfully without logging.
The SQL checks are scoped to SQL execution contexts or bare SQL statements so harmless commands such as `grep "DROP TABLE" docs` and Unix `truncate -s 0 file` are allowed.

## Claude Code Hook Format

The installer writes this hook into `~/.claude/settings.json`:

If that file already exists, the installer first creates `~/.claude/settings.json.bak`.

```json
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
```

The hook reads Claude Code's JSON payload from stdin. If a dangerous Bash command is detected, it logs the attempt and returns Claude Code's structured deny payload:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Blocked destructive Bash command: rm -rf recursive deletion. Review the command and rerun only if this destructive action is intentional and safe."
  }
}
```

## Test

```bash
bash hooks/destructive-command-blocker/test_block_destructive_bash.sh
```

The regression script covers required blocked patterns, expanded shell safety patterns, logging fields, the structured `hookSpecificOutput` deny schema, normal Bash passthrough, non-Bash tool passthrough, and SQL-text false-positive guards.
