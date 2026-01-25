# Fusion RPC Add-In

## Pivot: From Vision/UI Automation to Fusion API RPC
UI/vision clicking is brittle for vertex-level selection. General navigation worked, but precise measurement and edit workflows based on vision clicks were unreliable. We pivoted to a native RPC add-in that runs inside Fusion, exposes geometry via the Fusion API, and can load new command modules at runtime (no manual add-in reloads required after initial setup).

Architecture:
Agent/CLI <-> localhost TCP <-> Fusion RPC Add-In <-> Fusion API (main thread)

### Setup and Install (Fusion RPC Add-In)
Fusion add-ins must live in Fusion’s AddIns folder. Copy or symlink the add-in folder from this repo:

- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
- Windows: `%APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns`

From this repo, copy:
`fusion_rpc_addin/FusionRPCAddIn` -> Fusion AddIns folder

Recommended (keeps hot-reload in sync with this repo):
```bash
ln -sfn "$(pwd)/fusion_rpc_addin/FusionRPCAddIn/FusionRPCAddIn.py" \
  "~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionRPCAddIn/FusionRPCAddIn.py"
ln -sfn "$(pwd)/fusion_rpc_addin/FusionRPCAddIn/commands" \
  "~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionRPCAddIn/commands"
```

### Run the Add-In
1) Fusion -> Utilities -> Add-Ins -> Scripts and Add-Ins
2) Add-Ins tab -> select `FusionRPCAddIn` -> Run
3) Optionally enable “Run on Startup”

### Test from Terminal
```bash
python3 scripts/fusion_rpc_client.py ping
python3 scripts/fusion_rpc_client.py list_bodies
python3 scripts/fusion_rpc_client.py measure_bbox
python3 scripts/fusion_rpc_client.py measure_bbox --body "Body1"
```

### Visual Diff (Pillow)
```bash
python3 scripts/image_diff.py --before logs/capture_before.png --after logs/capture_after.png
```

### Sample Verification Record (update for your model)
- Parameter: `Height`
- Baseline: `30 mm` → Expect `measure_bbox.z_mm ≈ 30`
- Edit: `35 mm` → Expect `measure_bbox.z_mm ≈ 35` (+5 mm)
- Camera: `get_camera` → reuse with `set_camera` for both captures at a fixed size (e.g., 1280x720)

### Runtime Commands (No Add-In Toggle Needed)
The add-in discovers command modules from `FusionRPCAddIn/commands/` (one file per command). After initial add-in load, you can add new command files and hot-reload:

```bash
python3 scripts/fusion_rpc_client.py help
python3 scripts/fusion_rpc_client.py reload_commands
```

### Utility Commands
Create a parameter-driven box for repeatable measurement and verification:
```bash
python3 scripts/fusion_rpc_client.py create_param_box --param width_mm=20 --param depth_mm=20 --param height_param=Height --param height_expression="20 mm" --param body_name=Body2
```

To pass custom parameters to new commands:
```bash
python3 scripts/fusion_rpc_client.py my_command --param foo=123 --param bar=true
```

### Security + Troubleshooting
- The add-in binds only to `127.0.0.1` (not exposed on the network).
- If the port is in use, set `FUSION_RPC_PORT` before starting Fusion.
- Add-in logs are written to a temp file; the path is shown on startup.

## Files
- `fusion_rpc_addin/FusionRPCAddIn/`: Fusion RPC add-in (authoritative execution engine).
- `scripts/fusion_rpc_client.py`: CLI for sending RPC commands.
- `logs/`: Captures, snapshots, and observations (created at runtime).

## Quick Start
1) Run the Fusion RPC add-in and smoke test from Terminal:
```bash
python3 scripts/fusion_rpc_client.py ping
python3 scripts/fusion_rpc_client.py list_bodies
python3 scripts/fusion_rpc_client.py measure_bbox
```

## Notes
- You can set RPC-related values in a `.env` file in the project root (or set `FUSION_ENV_PATH` to point elsewhere).
