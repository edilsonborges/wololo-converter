#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Refusing to update: tracked files have local changes." >&2
  echo "Commit or restore them before updating." >&2
  exit 1
fi

requested_version="${1:-latest}"
previous_ref="$(git describe --tags --always --dirty)"
previous_commit="$(git rev-parse HEAD)"

if [[ "$previous_ref" == v[0-9]* ]]; then
  rollback_command="./scripts/update.sh $previous_ref"
else
  rollback_command="git checkout --detach $previous_commit && docker compose up -d --build --remove-orphans"
fi

git fetch --tags --prune origin

if [[ "$requested_version" == "latest" ]]; then
  target_tag="$(git tag --list 'v[0-9]*' --sort=-version:refname | head -n 1)"
else
  target_tag="${requested_version#v}"
  target_tag="v$target_tag"
fi

if [[ -z "$target_tag" ]] || ! git rev-parse --verify --quiet "$target_tag^{commit}" >/dev/null; then
  echo "Release tag not found: ${target_tag:-<none>}" >&2
  exit 1
fi

echo "Updating from $previous_ref to $target_tag..."
git checkout --detach "$target_tag"
./scripts/check-version.sh

if ! docker compose config --quiet; then
  echo "Invalid Docker Compose configuration." >&2
  echo "Return to the previous version with: $rollback_command" >&2
  exit 1
fi

if ! docker compose up -d --build --pull always --remove-orphans; then
  echo "Deployment failed." >&2
  echo "Return to the previous version with: $rollback_command" >&2
  exit 1
fi

health_url="${WOLOLO_HEALTH_URL:-http://127.0.0.1:47652/api/health}"
health_response=""
for _attempt in {1..30}; do
  if health_response="$(curl --fail --silent --show-error "$health_url" 2>/dev/null)"; then
    break
  fi
  sleep 2
done

if [[ -z "$health_response" ]]; then
  echo "Containers started, but the health check failed: $health_url" >&2
  echo "Inspect logs with: docker compose logs --tail=200" >&2
  echo "Return to the previous version with: $rollback_command" >&2
  exit 1
fi

echo "Deployment complete: $target_tag"
echo "$health_response"
