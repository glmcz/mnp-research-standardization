#!/usr/bin/env bash
# Rebuild every published artefact from the vendored corpus and diff it against what is
# committed. No network, no model: the corpus is the archive in data/raw/epmc/, and the
# extraction records are the ones in the repository.
#
#   ./tool/reproduce.sh            # verify, rebuild, diff
#   ./tool/reproduce.sh --restore  # unpack the corpus archive first
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --all-groups --quiet

if [[ "${1:-}" == "--restore" ]]; then
    uv run python -m mnp.corpus restore
fi

uv run python -m mnp.report reproduce
