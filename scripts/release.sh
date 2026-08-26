#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version="$(tr -d '[:space:]' < VERSION)"
tag="v$version"

if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Releases must be created from the main branch." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to release from a dirty worktree." >&2
  exit 1
fi

./scripts/check-version.sh

if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
  echo "Tag already exists: $tag" >&2
  exit 1
fi

(cd backend && python3 -m pytest -q)
(cd frontend && npm ci && npm run test && npm run build)

git tag --annotate "$tag" --message "Wololo Converter $tag"
git push origin main "$tag"

echo "Pushed $tag. The release workflow will publish the GitHub Release."
