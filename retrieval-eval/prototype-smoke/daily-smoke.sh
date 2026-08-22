#!/usr/bin/env bash
# Daily ADR-012 prototype smoke canary.
#
# Runs the frozen smoke gate against the current clean HEAD, appends one TSV
# summary line per attempt to results/daily/log.tsv, and classifies failures
# via tools/summarize-report.js. Never sends the results anywhere; forwarding
# or alerting is an operator decision.
#
# Install (WSL Ubuntu, cron must be running: sudo service cron start):
#   crontab -e
#   30 5 * * * /path/to/aptori_outreach/retrieval-eval/prototype-smoke/daily-smoke.sh >> /path/to/aptori_outreach/retrieval-eval/prototype-smoke/results/daily/cron.log 2>&1
#
# Environment overrides (defaults keep the reference WSL machine working):
#   OBSCURA_NODE_DIR  directory holding the pinned Node v20.18.0 toolchain
#   OBSCURA_BIN       path to the pinned Obscura binary (SHA-256 always verified)
#
# Exit codes: 0 passed, 2 gate failed, 3 skipped (dirty worktree), 1 crashed.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SMOKE_DIR="$REPO_ROOT/retrieval-eval/prototype-smoke"
PKG_DIR="$REPO_ROOT/packages/obscura-retrieval"
# verifyRuntime enforces the exact pinned Node version, so any directory used
# here must resolve to v20.18.0; otherwise fall back to PATH's node.
NODE_BIN_DIR="${OBSCURA_NODE_DIR:-/home/hari/.local/node-v20.18.0-linux-x64/bin}"
if [ -d "$NODE_BIN_DIR" ]; then
    export PATH="$NODE_BIN_DIR:$PATH"
fi

LOG_DIR="$SMOKE_DIR/results/daily"
mkdir -p "$LOG_DIR"

append_line() {
    printf '%s\n' "$1" >> "$LOG_DIR/log.tsv"
}

cd "$REPO_ROOT" || exit 1

if [ -n "$(git status --porcelain)" ]; then
    append_line "$(date -Is)	SKIPPED	dirty_worktree	commit or stash before running the frozen protocol"
    echo "daily-smoke: worktree is dirty; refusing to run the frozen protocol" >&2
    exit 3
fi

BEFORE=$(date +%s)
cd "$PKG_DIR" || exit 1
node bin/run-prototype-smoke.js >"$LOG_DIR/latest.out" 2>&1
SMOKE_RC=$?

REPORT=$(find "$SMOKE_DIR/results" -mindepth 2 -maxdepth 2 -name report.json -newermt "@$BEFORE" 2>/dev/null | sort | tail -n 1)

if [ -z "$REPORT" ]; then
    append_line "$(date -Is)	CRASHED	no_report	last 3 lines: $(tail -n 3 "$LOG_DIR/latest.out" | tr '\n' ' ' | tr '\t' ' ')"
    echo "daily-smoke: smoke crashed before writing a report; see $LOG_DIR/latest.out" >&2
    exit 1
fi

node "$SMOKE_DIR/tools/summarize-report.js" "$REPORT" >> "$LOG_DIR/log.tsv"

if [ "$SMOKE_RC" -eq 0 ]; then
    echo "daily-smoke: PASS ($REPORT)"
    exit 0
fi
echo "daily-smoke: FAIL rc=$SMOKE_RC ($REPORT)" >&2
exit 2
