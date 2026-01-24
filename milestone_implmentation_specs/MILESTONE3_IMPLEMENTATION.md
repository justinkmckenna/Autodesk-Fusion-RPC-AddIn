# Milestone 3 Implementation Spec — View Capture + Image-to-Entity Mapping

Last updated: 2026-01-24

Reference: See `PROJECT.md` for overall roadmap and milestone definitions.

## Goal
Enable deterministic, repeatable camera capture and pixel-based entity mapping to support annotated-image workflows.

This milestone is still **read-only**: no geometry edits.

## Non-regression constraints
- No UI automation.
- All Fusion API calls run on the main thread (CustomEvent + queue model).
- RPC responses are deterministic and structured (`ok`, `error`, `data`).
- Pixel mapping must explicitly declare image size and coordinate origin.

## Scope breakdown
Milestone 3 can be implemented in order as:
- **Phase 3A**: camera schema + capture contract + shared helpers
- **Phase 3B**: `get_camera`, `set_camera`, `capture_view`, `ray_pick`
- **Optional**: `project_point` for round-trip debug overlays

This is still one milestone; the phases are sequencing guidance for implementation.

## Phase 3A — Contracts and helpers (required)

### Camera schema (shared across commands)
Use a single JSON camera schema for all commands.

Required fields:
- `mode`: `"perspective"` or `"orthographic"`
- `eye_mm`: `{x, y, z}`
- `target_mm`: `{x, y, z}`
- `up`: `{x, y, z}` (unit vector)

Perspective-only:
- `fov_deg` (float)

Orthographic-only:
- `ortho_view_size_mm` (float)

Optional fields:
- `aspect_ratio` (float)
- `viewport_px`: `{width, height}` (returned by capture/get; not required in set)

Determinism rules:
- Round floats to a fixed precision (**6 decimals**) in outputs.
- Normalize `up` to unit length on output.
- Always include `mode`.
- Include `aspect_ratio` in outputs when available (derive from viewport size if needed).

### Pixel coordinate system
- Origin at **top-left** pixel of captured image.
- `x` increases to the right.
- `y` increases downward.
- `x` and `y` are integer pixel coordinates.

### Capture contract
`capture_view` must:
- Require `width_px` and `height_px`.
- Produce a deterministic image from the active viewport (no UI overlays).
- Return `image_path`, `width_px`, `height_px`, and the **actual** camera used.

File output rules:
- Write images to a deterministic directory: `logs/captures/`
- Naming format (example): `capture_<YYYYMMDD_HHMMSS>_<width>x<height>_<seq>.png`
- If timestamps are used, include a **monotonic counter** per session to avoid collisions.

### Shared helper requirements
Add a shared helper module (name TBD) to centralize:
- `_entity_id(entity)`:
  - Prefer `entityToken`, else `tempId`, else `entityId`.
  - Always return string or `null`.
- `_point_mm` / `_vector_mm` using existing `convert_mm`.
- `_normalize_camera()` to apply unit normalization and fixed precision.
- `_capture_output_path()` to enforce directory and naming format.

## Phase 3B — Commands

### Command: `get_camera`
Purpose: Return the active viewport camera.

Response (success):
- `ok: true`
- `error: null`
- `data: { camera: <camera_schema>, viewport_px: {width, height} }`

Failure modes:
- `ok=false` with a clear error if no active viewport.

### Command: `set_camera`
Purpose: Apply a camera to the active viewport.

Request:
- `camera`: full camera schema

Validation:
- `mode` must be `perspective` or `orthographic`.
- `up` vector must be non-zero.
- If perspective, require `fov_deg`.
- If orthographic, require `ortho_view_size_mm`.

Response:
- `ok: true`
- `data: { camera: <normalized camera schema> }`

### Command: `capture_view`
Purpose: Capture a deterministic image of the viewport.

Request:
- `width_px` (int)
- `height_px` (int)
- `camera` (optional override; if present, apply before capture)

Response:
- `ok: true`
- `data: { image_path, width_px, height_px, camera }`

### Command: `ray_pick`
Purpose: Map a pixel coordinate to a scene entity.

Note (2026-01-24): The initial ray-pick implementation was removed and will be re-implemented from scratch.

Request:
- `x_px`, `y_px`
- `width_px`, `height_px` (required; must match the capture size used for the pixel)
- `camera` (optional; if omitted, use current viewport camera)

Response (success):
- `ok: true`
- `data: {
    entity: { type: "face|edge|vertex", id, body_name },
    hit_mm: {x, y, z},
    normal: {x, y, z}?,
    distance_mm,
    viewport_px: {width, height}
  }`

Determinism requirements:
- If multiple hits, choose by smallest distance, then entity id.
- Always include the entity ID via the shared helper.

Failure modes:
- `ok=false` with explicit error if no hit, invalid coordinates, missing viewport, or size mismatch.

### Command: `project_point`
Purpose: Map a world point to a pixel coordinate for debug overlays.

Request:
- `world_point_mm`: `{x, y, z}`
- `camera`
- `width_px`, `height_px`

Response:
- `ok: true`
- `data: { x_px, y_px, depth_mm, in_view }`

## Definition of Done
- `capture_view` returns deterministic image + camera + size.
- A pixel from `capture_view` round-trips through `ray_pick` to the same entity reliably.
- `get_camera` + `set_camera` reproduce a view in the same session.
- `project_point` supports overlay/debug round-trips.

## CLI examples (placeholder)
- `python3 scripts/fusion_rpc_client.py get_camera`
- `python3 scripts/fusion_rpc_client.py set_camera --payload '{"camera": {...}}'`
- `python3 scripts/fusion_rpc_client.py capture_view --param width_px=1920 --param height_px=1080`
- `python3 scripts/fusion_rpc_client.py ray_pick --param x_px=320 --param y_px=240 --param width_px=1920 --param height_px=1080`

## Project tracking
After implementation + verification:
- Update `PROJECT.md`:
  - Mark Milestone 3 ✅ complete.
  - Append a dated progress-log entry noting camera schema and capture contract.
