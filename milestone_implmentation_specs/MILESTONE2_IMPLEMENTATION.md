# Milestone 2 Implementation Spec — Face-Based Measurement (`measure_face_span`)

Last updated: 2026-01-19

Reference: See `PROJECT.md` for the overall roadmap and milestone definitions.

## Scope
Implement an RPC command `measure_face_span` that:
- deterministically selects a face on a target body (default: rightmost by centroid X),
- finds “bottom” edges on that face near **global** min-Z,
- returns the length (mm) of the **longest** qualifying bottom edge,
- returns traceability (which face/edge/vertices were used and why).

Constraints:
- No UI automation.
- All Fusion API calls run on the main thread (existing CustomEvent + queue model).
- External access only via localhost RPC.

## Defaults (locked)
- `face_selector = "max_centroid_x"`
- `require_planar = false`
- `eps_mm = 0.05`
- bottom reference = global min-Z from body world bounding box
- body targeting = **explicit** `body_name` per call (Option A), with fallback:
  - if `body_name` omitted and exactly one visible body exists, use it;
  - otherwise error listing candidates.
- Entity identifiers: **session-stable IDs + descriptors** (not guaranteed persistent across sessions).

## Files
- Add command module: `fusion_rpc_addin/FusionRPCAddIn/commands/measure_face_span.py`

## RPC Interface
Command: `measure_face_span`

Parameters:
- `body_name` (string, optional): see targeting rules above.
- `face_selector` (string, default `max_centroid_x`), required support:
  - `max_centroid_x`
  - Nice-to-have (if easy): `max_bbox_x`, `largest_area`, `normal_closest:+Z|-Z|+X|-X|+Y|-Y` (planar only)
- `require_planar` (bool, default `false`)
- `span_mode` (string, default `max_edge_length`): `max_edge_length` or `projected_extent`
- `eps_mm` (number, default `0.05`)
- `units` (string, default `"mm"`): output only

## Deterministic Algorithm
1) Resolve active `design` and `rootComp`; if missing, return `ok=false` with a clear error.
2) Resolve the target body:
   - If `body_name` provided: exact name match among visible BRep bodies in root component.
   - Else if exactly one visible body exists: use it.
   - Else error with list of candidate body names.
3) Gather face candidates:
   - If `require_planar`: restrict to planar faces.
4) Face scoring:
   - `max_centroid_x`: score = face centroid world X.
   - (If implemented) other selectors score accordingly.
5) Deterministic tie-breaks:
   - score desc → face area desc → centroid tuple → face session-id/index.
6) Compute bottom reference `z_ref`:
   - `z_ref = body.worldBoundingBox.minPoint.z` (convert to mm).
7) Find qualifying bottom edges on selected face:
   - Iterate `face.edges`.
   - For each edge: obtain its two endpoint vertices; compute each endpoint’s world Z.
   - Keep the edge if both endpoints satisfy `abs(z - z_ref) <= eps_mm`.
8) Choose span:
   - `max_edge_length`: select the longest qualifying edge (edge length).
   - `projected_extent`: compute the max extent of bottom-edge endpoints along the dominant in-plane axis.
9) Return response with full traceability (face + all qualifying edges + chosen edge + endpoints).

Notes:
- Do not rely on Fusion collection enumeration order; always sort where selection could be ambiguous.
- Ensure all world-coordinate reads use the same frame consistently.

## Units / Conversion
- Standardize conversion to mm in one place; apply to:
  - all lengths (edge length, eps)
  - all returned coordinates (centroids, endpoints, bbox)
- Return mm in the response regardless of `units` until other unit modes are explicitly added.

## Response Schema
Top-level:
- `ok` (bool)
- `error` (string|null)
- `data` (object|null)

On success, `data` contains:
- `body`: `{ name }`
- `face`: `{ selector, require_planar, id, area_mm2?, centroid_mm:{x,y,z}, normal:{x,y,z}?, bbox_mm:{min:{x,y,z}, max:{x,y,z}} }`
- `bottom`: `{ eps_mm, z_ref_mm, edges:[{ id, length_mm, v0_mm:{x,y,z}, v1_mm:{x,y,z} }] }`
- `span`: `{ mode:"max_edge_length"|"projected_extent", value_mm, edge_id?, axis?, endpoints_mm:[{x,y,z},{x,y,z}] }`
- `trace`: `{ candidates_considered:{faces:int, edges:int} }`

## Error Handling (explicit)
Return `ok=false` for:
- No active design / no root component.
- Body not found, or ambiguous (multiple visible bodies and no `body_name`).
- No faces match selector (or no planar faces when `require_planar=true`).
- No bottom edges found within `eps_mm`.

## CLI Examples
- `python3 scripts/fusion_rpc_client.py measure_face_span --param body_name=Body1`
- `python3 scripts/fusion_rpc_client.py measure_face_span --param body_name=Body1 --param face_selector=max_centroid_x --param eps_mm=0.05`

## Acceptance Criteria (Definition of Done)
- Re-run the same call 5x: same selected face/edge IDs; `span.value_mm` stable within tolerance.
- Manual spot-check in Fusion Measure: span matches intended bottom edge within ~0.1 mm.
- Negative test: `eps_mm=0.001` returns `ok=false` with a clear “no bottom edges within epsilon” style error.

## Project Tracking
After implementation + verification:
- Update `PROJECT.md`:
  - Mark Milestone 2 ✅ complete.
  - Append a dated progress-log entry noting defaults and any additional selectors supported.
