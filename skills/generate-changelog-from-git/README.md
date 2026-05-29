# Generate Changelog From Git

Dependency-free Bash tool for generating a structured `CHANGELOG.md` from git history since the latest tag.

## Setup

```bash
# 1. Run it from the repository root.
bash changelog.sh

# 2. Review the generated CHANGELOG.md.
```

## Categories

Commits are grouped into the required changelog sections:

- `Added`: `feat:`, `add:`, `feature:`, initial commits, and add/create keywords
- `Fixed`: `fix:`, `bug:`, `hotfix:`, and fix/bug keywords
- `Changed`: `change:`, `refactor:`, `docs:`, `chore:`, `perf:`, `test:`, `build:`, `ci:`, and uncategorized commits
- `Removed`: `remove:`, `delete:`, `drop:`, `deprecate:`, and matching keywords

If a repository has tags, the script uses commits in `last-tag..HEAD`. If no tag exists, it uses the full repository history.

## Usage

```bash
bash changelog.sh
bash changelog.sh docs/CHANGELOG.md
CHANGELOG_VERSION=1.2.0 bash changelog.sh
```

The command overwrites the target changelog file with deterministic Markdown output.

## Claude Code Slash Command

This repository also includes `.claude/commands/generate-changelog.md`, so Claude Code users can run:

```text
/generate-changelog
```

The command delegates to this Bash script and writes `CHANGELOG.md`.
