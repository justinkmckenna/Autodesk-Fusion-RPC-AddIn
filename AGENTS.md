# Repository Guidelines

## Project Structure & Module Organization
- `fusion_rpc_addin/FusionRPCAddIn/`: Fusion add-in source (runs inside Fusion).
- `fusion_rpc_addin/FusionRPCAddIn/commands/`: RPC command modules (one file per command; hot-reloaded).
- `scripts/`: CLI utilities such as `fusion_rpc_client.py`.
- `logs/`: runtime captures and observations (generated at runtime).
- `.env` / `.env-example`: local configuration (API keys, endpoints).

## Build, Test, and Development Commands
- `python3 -m pip install -r requirements.txt` — install dependencies.
- `python3 scripts/fusion_rpc_client.py ping` — smoke test Fusion RPC add-in.
- `python3 scripts/fusion_rpc_client.py reload_commands` — hot-reload RPC modules.

## Coding Style & Naming Conventions
- Python code uses 4-space indentation; keep functions small and deterministic.
- Prefer `snake_case` for modules/functions and `UpperCamelCase` for classes.
- Name new RPC command modules by their command (e.g., `measure_face_span.py`).
- Keep RPC outputs structured and explicit (include `ok`, `error`, and identifiers).

## Testing Guidelines
- There is no dedicated test framework in this repo yet.
- Use the CLI commands above for smoke testing; keep results deterministic across runs.
- When rebuilding from drawings (e.g., `draft.png`), agents must also perform **visual verification** by capturing the standard orthographic and isometric views and comparing them to the draft.
  - Command: `python3 scripts/fusion_rpc_client.py capture_standard_views --param body_name=Body1 --param width_px=1200 --param height_px=900`
  - Compare captures in `logs/captures/` against `draft.png` (top/front/right/isometric).
  - Do this after each major feature milestone and before final handoff.
- When rebuilding from drawings, validate after each major feature:
  - `list_bodies` to ensure no accidental new bodies.
  - `measure_bbox` to confirm overall dimensions remain within expected bounds.
  - Re-run `measure_bbox` after any `extrude_profile` with `join` to catch unintended growth.

## Commit & Pull Request Guidelines
- Commit messages follow short, imperative statements (e.g., “Add RPC command hot-reload and docs”).
- Include a concise summary, rationale, and the commands you ran.

## Security & Configuration Tips
- The add-in binds to `127.0.0.1` only; keep it local.
- Set `FUSION_RPC_PORT` if the default port is busy.
- For hot-reload to see local changes, symlink the deployed add-in to this repo:
  - `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionRPCAddIn/FusionRPCAddIn.py`
  - `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionRPCAddIn/commands`
