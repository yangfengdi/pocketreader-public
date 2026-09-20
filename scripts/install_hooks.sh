#!/bin/sh
set -eu
cd "$(git rev-parse --show-toplevel)"
current=$(git config --get core.hooksPath || true)
if [ -n "$current" ] && [ "$current" != '.githooks' ]; then
  echo 'Existing core.hooksPath detected; integrate the checks into your hooks manually.' >&2
  exit 1
fi
for hook in .git/hooks/pre-commit .git/hooks/pre-push; do
  if [ -f "$hook" ]; then
    echo 'Existing local hooks detected; integrate the checks manually.' >&2
    exit 1
  fi
done
chmod +x .githooks/pre-commit .githooks/pre-push
git config --local core.hooksPath .githooks
echo 'Installed local pre-commit and pre-push guards for this clone.'
