# Generate Changelog From Git

Use this skill when a user asks to generate or refresh a project changelog from git history.

Run the bundled Bash command from the repository root:

```bash
bash changelog.sh
```

The command writes `CHANGELOG.md`, using commits since the latest git tag when one exists, or the full repository history when no tag exists. It groups entries into `Added`, `Fixed`, `Changed`, and `Removed`.
