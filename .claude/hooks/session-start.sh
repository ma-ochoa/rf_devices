#!/bin/bash
# Prepares the test environment in Claude Code on the web (cloud sessions only).
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}"
command -v uv >/dev/null 2>&1 || pip install -q uv
[ -x .venv/bin/python ] || uv venv -q -p 3.14 .venv
uv pip install -q -p .venv/bin/python pytest-homeassistant-custom-component broadlink==0.19.0 ruff
