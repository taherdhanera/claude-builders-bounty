# Bounty #1 verification map

Maps each acceptance criterion to the exact command or artifact in this PR.

| Criterion | Evidence |
|-----------|----------|
| `/generate-changelog` or `bash changelog.sh` | `SKILL.md` (`name: generate-changelog`) + repo-root `changelog.sh` |
| Fetches commits since last git tag | Default range `${SINCE_TAG}..HEAD` in `changelog.sh` |
| Auto-categorizes Added / Fixed / Changed / Removed | `commit_type()` + section builders in `changelog.sh` |
| Breaking changes surfaced | `feat!:` / `BREAKING CHANGE` subjects get a **Breaking** section |
| Append to existing changelog | `--append` prepends a release while preserving prior entries |
| Outputs formatted `CHANGELOG.md` | Keep a Changelog-style headers and bullet lists |
| Tested on a real repo (sample in PR) | `samples/CHANGELOG.sample.md` generated from this repo |
| README with setup in ≤3 steps | `README.md` Quick start (3 steps) |

## Commands

```bash
# Regression tests (57 checks)
bash skills/generate-changelog/tests/test_changelog.sh

# Verify PR sample matches repo history through the last sample refresh commit
preview="$(mktemp)"
bash changelog.sh --preview 2>/dev/null >"$preview"
grep -v '^## \[.*\] - ' "$preview" >"${preview}.body"
last_sample_commit="$(git log -1 --format=%H -- skills/generate-changelog/samples/CHANGELOG.sample.md || true)"
if [[ -n "$last_sample_commit" ]]; then
  while IFS= read -r hash; do
    short_hash="$(git rev-parse --short "$hash")"
    grep -v "(${short_hash})" "${preview}.body" >"${preview}.trim"
    mv "${preview}.trim" "${preview}.body"
  done < <(git rev-list "${last_sample_commit}^..HEAD")
fi
diff -u <(grep -v '^## \[.*\] - ' skills/generate-changelog/samples/CHANGELOG.sample.md) "${preview}.body"

# Generate changelog for current repo (repo-root entrypoint)
bash changelog.sh

# Preview without writing a file
bash changelog.sh --preview

# Prepend a release to an existing changelog
bash changelog.sh --since v1.0.0 --version 1.1.0 --append
```

Expected test output ends with `Tests: 57 passed, 0 failed`.

Additional regression coverage: unknown commit categories require manual review, literal backslashes survive output, and shallow history is rejected without overwriting release notes. Sample source: 2fad474f5c999bd7188dfcc2c30745dd22dbcf28 (six non-merge commits); generated on 2026-09-08 with the updated classifier.
