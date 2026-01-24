# Milestone 4 Implementation Spec — First Edit Primitive + Closed-Loop Verification

Last updated: 2026-01-24

Reference: See `PROJECT.md` for the overall roadmap and milestone definitions.

## Goal
Introduce one safe edit primitive (parameter-based) and prove closed-loop verification:
query → edit → re-measure → re-render → verify → rollback on failure.

Milestone 4 is the first **write** milestone.

## Non-regression constraints
- No UI automation for geometry work.
- All Fusion API calls must run on the main thread via the existing CustomEvent + queue model.
- RPC responses must be deterministic and structured (`ok`, `error`, `data`).
- Prefer API-derived measurements and deterministic renders over OS-level screenshots.

## Scope decisions
- **Edit primitive:** User-parameter edits only (safest, deterministic, minimal topology risk).
- **Verification:** Numeric measurements + deterministic render diff.
- **Sample model:** Use the **currently open design in Fusion** that includes at least one user parameter driving visible geometry.
  - The milestone must document which parameter to edit and expected measurable changes.
- **Parameter creation:** If the target user parameter does not exist, `set_user_parameter` **creates it** before applying the expression.

## Files
- Add: `fusion_rpc_addin/FusionRPCAddIn/commands/list_user_parameters.py`
- Add: `fusion_rpc_addin/FusionRPCAddIn/commands/get_user_parameter.py`
- Add: `fusion_rpc_addin/FusionRPCAddIn/commands/set_user_parameter.py`
- Optional: `fusion_rpc_addin/FusionRPCAddIn/commands/_parameter_helpers.py`

## Commands

### Command: `list_user_parameters`
Purpose: Enumerate all user parameters for deterministic targeting.

Request: none

Response (success):
- `ok: true`
- `error: null`
- `data: { parameters: [...] }`
- Each parameter entry:
  - `name` (string)
  - `expression` (string)
  - `value` (number)
  - `unit` (string)
  - `comment` (string|null, optional)
  - `is_favorite` (bool, optional)

Determinism requirements:
- Parameters sorted lexicographically by `name`.

Failure modes:
- `ok=false` with explicit `error` if no active design or parameter table unavailable.

---

### Command: `get_user_parameter`
Purpose: Fetch one user parameter for precise edits and rollback.

Request:
- `name` (string, required)

Response (success):
- `ok: true`
- `error: null`
- `data: { parameter: { name, expression, value, unit, comment?, is_favorite? } }`

Failure modes:
- `ok=false` with `error: "User parameter not found"`.

---

### Command: `set_user_parameter`
Purpose: Apply a parameter edit with safe rollback data.

Request:
- `name` (string, required)
- `expression` (string, required), e.g. `"12 mm"`, `"25 in"`, `"2.5"`
- `compute` (bool, default `true`) — force recompute

Response (success):
- `ok: true`
- `error: null`
- `data: {
    previous: { expression, value, unit },
    current: { expression, value, unit },
    compute: { ran: bool }
  }`

Failure modes:
- If expression invalid or compute fails, **revert** to `previous.expression` and return:
  - `ok=false`
  - `error` explaining the failure
  - `data` including `previous` and attempted `expression`
- If the parameter does not exist, **create it** and set `previous` to `null`.

Determinism requirements:
- Always return `previous` and `current` data.
- Return stable values in a consistent unit set (use Fusion units manager output).

## Closed-loop verification workflow (documented, agent-run)

### Pre-state capture
1) `status`
2) `list_user_parameters` → choose target parameter
3) `measure_bbox` or `measure_face_span` on the target body
4) `get_camera` + `capture_view` (fixed size)

### Edit
5) `set_user_parameter` with new expression

### Post-state capture
6) Repeat the same measurement command(s)
7) Reapply the same camera with `set_camera` + `capture_view`

### Verify
- **Numeric:** verify measured delta or target value within a tolerance (e.g., ±0.1 mm)
- **Visual:** compare pre/post captures and compute diff threshold

### Rollback
If any verification fails:
- `set_user_parameter` with `previous.expression`
- Re-run the measurement + capture to confirm rollback

## Visual diff tooling decision (locked)
Use **Pillow** (cross-platform).
- Pros: portable, accurate diffs, simple code.
- Cons: requires adding `requirements.txt` and installing dependencies.

## Sample model requirement (must document)
- Use the currently open Fusion design in the verification steps.
- The milestone must document:
  - parameter name to edit
  - expected measurable change (e.g., bbox X increases by +5 mm)
  - camera settings for deterministic view capture

## Acceptance criteria (Definition of Done)
- `list_user_parameters`, `get_user_parameter`, and `set_user_parameter` behave deterministically.
- Full loop can be run on the sample model with documented commands.
- Numeric verification passes for a known parameter edit.
- Visual diff artifacts are produced and stored under `logs/`.
- On failure, rollback restores measurements within tolerance.

## CLI verification commands (to include in README or this spec)
Example commands (adjust per sample model):
- `python3 scripts/fusion_rpc_client.py list_user_parameters`
- `python3 scripts/fusion_rpc_client.py get_user_parameter --param name=Height`
- `python3 scripts/fusion_rpc_client.py set_user_parameter --param name=Height --param expression="35 mm"`
- `python3 scripts/fusion_rpc_client.py measure_bbox --param body_name=Body1`
- `python3 scripts/fusion_rpc_client.py capture_view --param width_px=1280 --param height_px=720`

## Verification example (Height parameter)
Assume an axis-aligned box where the Z dimension is driven by a user parameter named `Height`.

Baseline:
- `Height = 30 mm`
- `measure_bbox.z_mm` = 30 (±0.1 mm)

Edit:
- Set `Height` to `35 mm` via `set_user_parameter`
- Expect `measure_bbox.z_mm` to increase by **+5 mm** (±0.1 mm)

Rollback:
- If verification fails, restore `Height = 30 mm` and re-measure.

## Verification record (2026-01-24)
Sample model: active design in Fusion with a param-driven box named `Body2`.

Commands executed:
- `python3 scripts/fusion_rpc_client.py create_param_box --param width_mm=20 --param depth_mm=20 --param height_param=Height --param height_expression="20 mm" --param body_name=Body2`
- `python3 scripts/fusion_rpc_client.py measure_bbox --param body_name=Body2`
- `python3 scripts/fusion_rpc_client.py get_camera`
- `python3 scripts/fusion_rpc_client.py capture_view --payload '{"width_px":1280,"height_px":720,"camera":{...}}'`
- `python3 scripts/fusion_rpc_client.py set_user_parameter --param name=Height --param expression="40 mm"`
- `python3 scripts/fusion_rpc_client.py measure_bbox --param body_name=Body2`
- `python3 scripts/fusion_rpc_client.py capture_view --payload '{"width_px":1280,"height_px":720,"camera":{...}}'`
- `python3 scripts/image_diff.py --before logs/captures/capture_20260124_171221_1280x720_001.png --after logs/captures/capture_20260124_171233_1280x720_002.png`
- `python3 scripts/fusion_rpc_client.py set_user_parameter --param name=Height --param expression="20 mm"`
- `python3 scripts/fusion_rpc_client.py measure_bbox --param body_name=Body2`

Observed values:
- Baseline bbox: `x_mm=20.0`, `y_mm=20.0`, `z_mm=20.0`
- After edit (`Height=40 mm`): `x_mm=20.0`, `y_mm=20.0`, `z_mm=40.0`
- Rollback (`Height=20 mm`): `x_mm=20.0`, `y_mm=20.0`, `z_mm=20.0`

Visual diff artifacts:
- Before: `logs/captures/capture_20260124_171221_1280x720_001.png`
- After: `logs/captures/capture_20260124_171233_1280x720_002.png`
- Diff: `logs/diff_20260124_171239.png`

## Project tracking
After implementation + verification:
- Update `PROJECT.md`:
  - Mark Milestone 4 ✅ complete.
  - Add a dated progress-log entry noting parameter-based edit + verification workflow.
