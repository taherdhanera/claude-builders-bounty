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

Blocked attempts are logged to `~/.claude/hooks/blocked.log` with:

- timestamp
- attempted command
- project path
- block reason

Normal Bash commands and non-Bash tool calls exit successfully without logging.

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

The hook reads Claude Code's JSON payload from stdin. If a dangerous Bash command is detected, it writes a clear explanation to stderr and exits with code `2` so Claude Code blocks the tool call.

## Test

```bash
bash hooks/destructive-command-blocker/test_block_destructive_bash.sh
```
