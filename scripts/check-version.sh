#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version="$(tr -d '[:space:]' < VERSION)"
backend_version="$(sed -n 's/^APP_VERSION = "\([^"]*\)"$/\1/p' backend/app/version.py)"
frontend_version="$(node -p "require('./frontend/package.json').version")"
lock_version="$(node -p "require('./frontend/package-lock.json').packages[''].version")"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid semantic version in VERSION: $version" >&2
  exit 1
fi

for entry in \
  "backend/app/version.py:$backend_version" \
  "frontend/package.json:$frontend_version" \
  "frontend/package-lock.json:$lock_version"; do
  file="${entry%%:*}"
  value="${entry#*:}"
  if [[ "$value" != "$version" ]]; then
    echo "Version mismatch: $file has $value, expected $version" >&2
    exit 1
  fi
done

if ! grep -Fq "## [$version]" CHANGELOG.md; then
  echo "CHANGELOG.md has no entry for $version" >&2
  exit 1
fi

if [[ "${GITHUB_REF_TYPE:-}" == "tag" && "${GITHUB_REF_NAME:-}" != "v$version" ]]; then
  echo "Tag ${GITHUB_REF_NAME:-<missing>} does not match v$version" >&2
  exit 1
fi

echo "Version $version is consistent."
