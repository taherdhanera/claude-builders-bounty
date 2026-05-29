#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$script_dir/changelog.sh"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

cd "$tmpdir"
git init -q
git config user.email test@example.com
git config user.name "Changelog Test"
git config core.autocrlf false

printf 'one\n' > demo.txt
git add demo.txt
git commit -q -m "feat: add demo file"

printf 'two\n' >> demo.txt
git add demo.txt
git commit -q -m "fix: repair demo output"

printf 'three\n' >> demo.txt
git add demo.txt
git commit -q -m "refactor: change demo layout"

rm demo.txt
git add demo.txt
git commit -q -m "remove: drop demo file"

CHANGELOG_DATE=2026-05-29 bash "$hook" CHANGELOG.md >/tmp/changelog-test-output.txt

grep -F "### Added" CHANGELOG.md >/dev/null
grep -F "feat: add demo file" CHANGELOG.md >/dev/null
grep -F "### Fixed" CHANGELOG.md >/dev/null
grep -F "fix: repair demo output" CHANGELOG.md >/dev/null
grep -F "### Changed" CHANGELOG.md >/dev/null
grep -F "refactor: change demo layout" CHANGELOG.md >/dev/null
grep -F "### Removed" CHANGELOG.md >/dev/null
grep -F "remove: drop demo file" CHANGELOG.md >/dev/null

git tag v0.1.0 HEAD~2
CHANGELOG_DATE=2026-05-29 bash "$hook" CHANGELOG-tagged.md >/tmp/changelog-test-output-tagged.txt
grep -F "since v0.1.0" CHANGELOG-tagged.md >/dev/null
grep -F "refactor: change demo layout" CHANGELOG-tagged.md >/dev/null
grep -F "remove: drop demo file" CHANGELOG-tagged.md >/dev/null
if grep -F "feat: add demo file" CHANGELOG-tagged.md >/dev/null; then
  echo "Tagged changelog included commits before the latest tag" >&2
  exit 1
fi

echo "All changelog generator tests passed."
