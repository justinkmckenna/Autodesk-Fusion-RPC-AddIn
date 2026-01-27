# Fusion RPC Add-In

Architecture:
Agent/CLI <-> localhost TCP <-> Fusion RPC Add-In <-> Fusion API (main thread)

### Setup and Install (Fusion RPC Add-In)
Fusion add-ins must live in Fusion’s AddIns folder.

From this repo, copy:
`FusionRPCAddIn.py` -> Fusion AddIns folder

Fusion AddIns folder:
- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
- Windows: `%APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns`

### Run the Add-In
1) Fusion -> Utilities -> Add-Ins -> Scripts and Add-Ins
2) Add-Ins tab -> select `FusionRPCAddIn` -> Run
3) Optionally enable “Run on Startup”

### Test from Terminal
```bash
python3 fusion_rpc_client.py run_python --code "result = {'ok': True}"
```

### Runtime Execution
The add-in exposes a single `run_python` command that executes trusted Python in the add-in process. The code runs on Fusion’s main thread via the existing custom event pipeline.

```bash
python3 fusion_rpc_client.py run_python --code "result = app.activeProduct is not None"
python3 fusion_rpc_client.py run_python --code "print('hello'); result = 123" --label hello
```

## Context7 MCP Recommendation
Use the Context7 MCP server when working with this add-in so the agent can quickly look up Fusion 360 API classes and usage without relying on ad-hoc web searches.

Recommended libraries:
- `/autodeskfusion360/autodeskfusion360.github.io` — primary index for Fusion 360 API surface.
- `/ipendle/autodesk-fusion-api-documentation` — secondary source for usage snippets.

## Files
- `FusionRPCAddIn.py`: Fusion RPC add-in (authoritative execution engine).
- `fusion_rpc_client.py`: CLI for sending RPC commands.
- `logs/`: Captures, snapshots, and observations (created at runtime).
