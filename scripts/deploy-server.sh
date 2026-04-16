#!/usr/bin/env bash
# Run on the crossroads production host (crossroadsadmin) after merging to GitHub.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/internal_crossroads_Candidate_Ranking_Application_v3.0.1}"
COMPOSE_DIR="${COMPOSE_DIR:-$HOME/crossroads-resume-grader}"
GIT_REF="${GIT_REF:-main}"

cd "$APP_DIR"
git fetch origin
git checkout "$GIT_REF"
git pull --ff-only "origin/$GIT_REF"

cd "$COMPOSE_DIR"
docker compose -f docker-compose.prod.yml -f docker-compose.yml build backend
docker compose -f docker-compose.prod.yml -f docker-compose.yml up -d --no-deps backend

curl -sf "http://127.0.0.1:9011/health" | grep -q '"status"' || {
  echo "Health check failed" >&2
  exit 1
}
echo "Deploy OK: backend updated and /health returned ok."
