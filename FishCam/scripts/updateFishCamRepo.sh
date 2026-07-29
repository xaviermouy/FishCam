#!/bin/bash
# Navigate to repo root (two levels up from scripts/)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"
git fetch origin
git reset --hard origin/main
git clean -fd -e data -e logs
