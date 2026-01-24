# Milestone 1 Implementation Spec — Health + Introspection (`status`, `get_body_info`)

Last updated: 2026-01-24

Reference: See `PROJECT.md` for the overall roadmap and milestone definitions.

## Goal
Add RPC commands that allow external agents/tools to quickly answer:
- “Is Fusion in a valid state to run geometry commands?”
- “What bodies exist, what are their basic properties, and how do I target them deterministically?”

This milestone is intentionally **read-only** (no edits).

## Non-regression constraints
- No UI automation.
- All Fusion API calls must run on the main thread via the existing CustomEvent + queue model.
- RPC responses must be deterministic and structured (`ok`, `error`, `data`).

## Targeting scope decision (for this milestone)
Decision: implement the **simplest** targeting scope — **root component visible solid bodies only** (consistent with existing `list_bodies` behavior):
- Enumerate `root_comp.bRepBodies`
- Filter to `body.isVisible` and `body.isSolid`

Out of scope for Milestone 1:
- Bodies inside **occurrences** (assembly context) such as `root_comp.occurrences[i].component.bRepBodies` with transforms and disambiguated paths.

Note: if/when occurrence support is added later, introduce an explicit `occurrence_path` (or `scope=all_occurrences`) to avoid breaking existing callers.

## Files
- Add: `fusion_rpc_addin/FusionRPCAddIn/commands/status.py` (if not already present; otherwise extend)
- Add: `fusion_rpc_addin/FusionRPCAddIn/commands/get_body_info.py`
- Optional (if shared logic is useful): `fusion_rpc_addin/FusionRPCAddIn/commands/_body_resolve.py` (or similar)

## Command: `status`

### Purpose
Fast health-check: confirm active design context, units, and body availability before doing geometry work.

### Request
Command: `status`
Params: none

### Response (success)
Top-level:
- `ok: true`
- `error: null`
- `data: {...}`

`data` fields (recommended):
- `app`: `{ fusion_version?: string }` (optional if easy)
- `document`: `{ name?: string, is_saved?: bool, path?: string|null }` (do not error if path unavailable)
- `design`: `{ is_active: bool, name?: string }`
- `units`: `{ default_length_units: string }` (e.g., `"mm"`, `"cm"`, `"in"`)
- `root_component`: `{ name: string }`
- `bodies`: `{ visible_solid_count: int, names: [string] }`
- `rpc`: `{ port?: int }` (optional if available from configuration)

### Response (failure)
Return `ok=false` with a specific `error`, e.g.:
- “No active design”
- “No root component”

### Determinism requirements
- Body names list sorted lexicographically.
- No timestamps in output (or if present, put under a clearly optional `debug` field and keep out of DoD assertions).

## Command: `get_body_info`

### Purpose
Return a deterministic “body summary” for targeting and verification.

### Request
Command: `get_body_info`
Params:
- `body_name` (string, optional):
  - If provided: exact match among visible solid bodies.
  - If omitted and exactly one visible solid body exists: use it.
  - Otherwise: error listing candidates.
- `include_hidden` (bool, default `false`): if `true`, include non-visible solids as candidates (still root-only).
- `units` (string, default `"mm"`): output unit for lengths/coords (support `"mm"` at minimum; others optional).

### Response (success)
Top-level:
- `ok: true`
- `error: null`
- `data: {...}`

`data` fields:
- `body`: `{ name: string, id?: string|null }` (session-stable id if available)
- `counts`: `{ faces: int, edges: int, vertices: int }`
- `bbox_mm`:
  - `{ min: {x,y,z}, max: {x,y,z}, size: {x,y,z} }`
  - Use `body.worldBoundingBox` if available; else `body.boundingBox`.
- `physical_mm` (best-effort; omit or set nulls if not available):
  - `volume_mm3` (number|null)
  - `area_mm2` (number|null)
  - `density_kg_m3` (number|null) (optional)
  - `mass_kg` (number|null) (optional)
- `transform`:
  - For Milestone 1 root-only, set identity:
    - `{ is_identity: true }`
  - (Do not invent transforms; add later when occurrences are supported.)

### Response (failure)
Return `ok=false` with:
- `error` describing the issue
- `candidates: [string]` when ambiguous (sorted)

### Determinism requirements
- Counts must be integers (not collection objects).
- Use stable unit conversion in one helper (consistent with other commands).
- No floating noise amplification: return floats as-is, but avoid extra derived computations that introduce nondeterminism.

## Shared behavior / helpers (recommended)
- Body resolution helper consistent with:
  - `list_bodies`
  - `measure_bbox`
  - `measure_face_span`
- Entity id helper: try `tempId`, `entityToken`, etc., and return `null` if unavailable.
- Unit conversion helper:
  - Normalize outputs to mm by default.

## CLI examples
- `python3 scripts/fusion_rpc_client.py status`
- `python3 scripts/fusion_rpc_client.py get_body_info --param body_name=Body1`
- `python3 scripts/fusion_rpc_client.py get_body_info` (only valid if exactly one visible solid body exists)

## Acceptance criteria (Definition of Done)
- `status`:
  - Returns `ok=true` with expected fields when a design is open.
  - Returns `ok=false` with a clear error when no design is active.
- `get_body_info`:
  - Deterministically resolves `body_name` and returns stable counts + bbox.
  - Returns an explicit ambiguity error (with sorted candidates) when multiple bodies exist and no `body_name` is provided.
- Outputs are stable across repeated calls in the same session.

## Project tracking
After implementation + verification:
- Update `PROJECT.md`:
  - Mark Milestone 1 ✅ complete.
  - Add a dated progress log entry with any noteworthy behaviors (e.g., `include_hidden`, identity transform assumption).
