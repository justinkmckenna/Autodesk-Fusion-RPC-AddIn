# Repository Guidelines

## Project Structure & Module Organization
- `FusionRPCAddIn.py`: Fusion add-in source (runs inside Fusion).
- `fusion_rpc_client.py`: CLI utility for RPC commands.
- `logs/`: runtime captures and observations (generated at runtime).

## Build, Test, and Development Commands
- `python3 -m pip install -r requirements.txt` — install dependencies.
- `python3 fusion_rpc_client.py --code-stdin` — run multiline Python via stdin.

## Context7 Guidance
- Use `/autodeskfusion360/autodeskfusion360.github.io` as the primary index to confirm Fusion 360 API surface.
- Use `/ipendle/autodesk-fusion-api-documentation` for more detailed snippets when needed.
