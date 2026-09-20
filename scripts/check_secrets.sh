#!/bin/sh
set -eu
cd "$(git rev-parse --show-toplevel)"
pr_gitleaks=$(git config --get pocketreader.gitleaksPath || true)
if [ -z "$pr_gitleaks" ]; then
  pr_gitleaks=gitleaks
fi
if ! command -v "$pr_gitleaks" >/dev/null 2>&1; then
  echo 'Install Gitleaks v8 before pushing (see CONTRIBUTING.md). Push blocked.' >&2
  exit 1
fi
exec "$pr_gitleaks" git . --log-opts=--all --redact=100 --no-banner
