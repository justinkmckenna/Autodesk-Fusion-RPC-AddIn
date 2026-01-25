# Fusion RPC Add-In

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

### Runtime Commands (No Add-In Toggle Needed)
The add-in discovers command modules from `FusionRPCAddIn/commands/` (one file per command). After initial add-in load, you can add new command files and hot-reload:

```bash
python3 scripts/fusion_rpc_client.py help
python3 scripts/fusion_rpc_client.py reload_commands
```

## Files
- `fusion_rpc_addin/FusionRPCAddIn/`: Fusion RPC add-in (authoritative execution engine).
- `scripts/fusion_rpc_client.py`: CLI for sending RPC commands.
- `logs/`: Captures, snapshots, and observations (created at runtime).
