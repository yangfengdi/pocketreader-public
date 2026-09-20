# PocketReader agent instructions

Read `README.md`, `docs/getting-started.md`, and `docs/ai-handoff.md` first.
This repository must work without the original author's chat history, home
directory, server, credentials, or sibling projects.

## Private information

- Keep hostnames, real server IPs, login credentials, tokens, SSH keys, raw
  conversations, databases, audio, backups, and personal deployment notes out
  of Git, patches, PRs, screenshots, and build contexts.
- Use `reader.example.com`, documentation IP ranges, and credential placeholders
  in public examples. Generate each installation's own credentials with
  `scripts/init_env.py`. Never use example values in production.
- For an explicitly requested maintenance task on an existing installation,
  locate the private runbook using `git config --get pocketreader.privateDir`.
  This setting exists only in the owner's local Git configuration. Read its
  `README.md` and `deployment.json` locally. Do not echo credential files.
- If no private runbook exists, configure a new independent installation;
  do not infer that the author's server is available to a fork.
- Read the actual target's local isolation rules before touching its server.
  Public deployment examples are not evidence of an existing server's state.

## Development

- Python 3.12 is the Docker baseline. Install `requirements.txt`, ffmpeg and
  ffprobe. Node is used for extension tests, with no npm build step.
- Run `.venv/bin/python -m unittest discover -s tests` and
  `node tests/browser_extension_capture.test.js`. Also run any other
  `tests/*extension*.test.js` files when changing extension configuration.
- Run `python3 scripts/check_public_content.py` before commit, and install
  local hooks with `sh scripts/install_hooks.sh` once per clone.
- Keep one application process / one worker; do not add Uvicorn workers or
  replicas without redesigning database job claiming.
- Preserve reader-mode identity, incremental turn creation, original snapshots,
  Markdown text, and audio HEAD/Range support. Read the focused design docs
  before changing capture or speech behavior; add regression tests for fixes.
- Use synthetic conversations in fixtures. Do not copy production snapshots.
- For schema changes, consider old databases and rollback compatibility; do
  not delete data to make a migration pass.

## Delivery

Explain changed behavior, tests, and limitations. Update affected docs in the
same change. Keep local maintenance facts in the private runbook. Confirm the
remote and inspect the outgoing commit history before pushing. Publishing a
fork does not authorize deployment to someone else's server.
