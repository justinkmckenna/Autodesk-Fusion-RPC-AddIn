#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
CAPTURES_DIR="$LOG_DIR/captures"

if [ -d "$CAPTURES_DIR" ]; then
  rm -f "$CAPTURES_DIR"/*.png
fi

if [ -d "$LOG_DIR" ]; then
  rm -rf "$LOG_DIR"/agent-run-*
fi

if [ -f "$LOG_DIR/mcp_actions.jsonl" ]; then
  : > "$LOG_DIR/mcp_actions.jsonl"
fi

echo "Cleared logs: captures, agent-run folders, and mcp_actions.jsonl"
