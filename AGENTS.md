# Repository Guidelines

## Project Structure & Module Organization
- `fusion_rpc_addin/FusionRPCAddIn/`: Fusion add-in source (runs inside Fusion).
- `fusion_rpc_addin/FusionRPCAddIn/commands/`: RPC command modules (one file per command; hot-reloaded).
- `scripts/`: CLI utilities such as `fusion_rpc_client.py`.
- `agent_runner.py` / `mcp_server.py`: **Legacy/deprecated** UI/vision automation scaffolding (do not use for deterministic geometry ops).
- `logs/`: runtime captures and observations (generated at runtime).
- `calibration.json`: example screen region presets; customize per machine.
- `.env` / `.env-example`: local configuration (API keys, endpoints).

## Build, Test, and Development Commands
- `python3 -m pip install -r requirements.txt` — install dependencies.
- `python3 scripts/fusion_rpc_client.py ping` — smoke test Fusion RPC add-in.
- `python3 scripts/fusion_rpc_client.py reload_commands` — hot-reload RPC modules.
- (Legacy/deprecated) `python3 agent_runner.py` — UI/vision scaffolding (not for deterministic geometry ops).
- (Legacy/deprecated) `python3 mcp_server.py --tcp-host 127.0.0.1 --tcp-port 8765` — legacy MCP server.

## Coding Style & Naming Conventions
- Python code uses 4-space indentation; keep functions small and deterministic.
- Prefer `snake_case` for modules/functions and `UpperCamelCase` for classes.
- Name new RPC command modules by their command (e.g., `measure_face_span.py`).
- Keep RPC outputs structured and explicit (include `ok`, `error`, and identifiers).
- Do not introduce new UI automation for geometry work; keep UI/vision tooling (if used) limited to optional/experimental **visual verification** only.

## Testing Guidelines
- There is no dedicated test framework in this repo yet.
- Use the CLI commands above for smoke testing; keep results deterministic across runs.
- For Fusion add-in changes, verify with `ping`, `list_bodies`, and `measure_bbox`.
  - Prefer API-derived measurements and deterministic renders over OS-level screenshots.

## Commit & Pull Request Guidelines
- Commit messages follow short, imperative statements (e.g., “Add RPC command hot-reload and docs”).
- Include a concise summary, rationale, and the commands you ran.
- For changes affecting Fusion UI behavior or measurements, add a brief verification note (and screenshots if relevant).

## Security & Configuration Tips
- The add-in binds to `127.0.0.1` only; keep it local.
- Set `FUSION_RPC_PORT` if the default port is busy.
- For hot-reload to see local changes, symlink the deployed add-in to this repo:
  - `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionRPCAddIn/FusionRPCAddIn.py`
  - `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionRPCAddIn/commands`
- macOS **Screen Recording** and **Accessibility** permissions are only needed for the **legacy** MCP UI/vision tooling.
