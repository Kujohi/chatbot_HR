#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "deploy.sh must be run from inside a git repository."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required."
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree has local changes. Commit or stash them before deploying."
  git status --short
  exit 1
fi

echo "==> Fetching latest code from origin/${DEPLOY_BRANCH}"
git fetch origin "${DEPLOY_BRANCH}"

if git show-ref --verify --quiet "refs/heads/${DEPLOY_BRANCH}"; then
  git switch "${DEPLOY_BRANCH}"
elif git show-ref --verify --quiet "refs/remotes/origin/${DEPLOY_BRANCH}"; then
  git switch -c "${DEPLOY_BRANCH}" --track "origin/${DEPLOY_BRANCH}"
else
  echo "Branch '${DEPLOY_BRANCH}' not found locally or on origin."
  exit 1
fi

git pull --ff-only origin "${DEPLOY_BRANCH}"

echo "==> Building and restarting services"
docker compose up -d --build --remove-orphans

echo "==> Current service status"
docker compose ps
