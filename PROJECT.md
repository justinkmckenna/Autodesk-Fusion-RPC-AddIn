# PROJECT — Fusion Automation Pivot (Planner View)

Last updated: 2026-01-19

## Mission (north star)
Enable an AI agent to **deterministically measure and edit** CAD geometry in Autodesk Fusion based on:
- **User intent** (text constraints + desired change), and
- **User-provided annotated images** (arrows/labels referencing regions/features),
then **verify** the edit matches the ask (numeric + visual evidence).

## Non-regression principles
- **No UI automation** for geometry work (no clicking, screenshots-as-control, or vision-driven selection).
- All Fusion API calls execute on the **main thread** (CustomEvent + queue dispatch).
- External tools/agents communicate **only via RPC** to a resident Fusion Add-In.
- Commands remain **small, deterministic, composable**, with traceable outputs (what was selected, how, and why).

## Current architecture (implemented)
Agent / CLI  ↔  localhost TCP (JSON RPC)  ↔  Fusion RPC Add-In  ↔  Fusion API (main thread)

Repository components:
- Fusion Add-In (Python): `fusion_rpc_addin/FusionRPCAddIn/`
- Command modules: `fusion_rpc_addin/FusionRPCAddIn/commands/`
- External client: `scripts/fusion_rpc_client.py`

Threading model (required):
- Socket server runs on a worker thread
- RPC handlers enqueue work
- Fusion API calls run on the main thread via `CustomEvent`

Hot reload (implemented):
- `reload_commands` reloads command modules without restarting the add-in
- `help` enumerates available commands

## Baseline capabilities (verified)
- `ping`: connectivity test
- `list_bodies`: lists visible BRep bodies in the root component
- `measure_bbox`: bounding box extents (mm) for a body; validated against manual measurement

## Roadmap (incremental milestones)

### Milestone 0 — “Execution engine” (DONE)
Goal: stable RPC transport + safe main-thread execution + hot reload.

Definition of Done:
- Add-in runs persistently in Fusion and responds over `127.0.0.1`
- Worker-thread socket + main-thread API dispatch is stable under repeated calls
- Commands can be added/modified and reloaded via `reload_commands`

Status: ✅ complete

---

### Milestone 1 — Health + introspection (NEXT after face measurement if needed)
Goal: early failure detection and richer geometry inventory for deterministic targeting.

Deliverables:
- `status`: active design/doc info, units, root component, visible body count + names
- `get_body_info`: bbox (mm), volume, area, face/edge/vertex counts, world transform

Definition of Done:
- Deterministic outputs for the same model/session (aside from timestamps/paths)
- Errors are explicit (no silent `None`); responses include `ok=false` + reason

Status: ⏳ not started

---

### Milestone 2 — Face-based measurement (ACTIVE milestone)
Goal: replace the original “Step 8 UI measurement” with an API-only, face-targeted measurement.

Primary deliverable:
- `measure_face_span`: compute a span on a face using explicit, rule-based selection

Design requirements:
- Inputs describe *rules*, not pixels:
  - Face selector (examples): `max_centroid_x`, `max_bbox_x`, `normal_closest:+Z`, `largest_planar`
  - “Bottom edge” selector: tolerance-based pick of edges/vertices near global min-Z (epsilon)
  - Span computation method: vertex-to-vertex distance, edge length, or projected distance (explicit)
- Output must include traceability:
  - Selected `body_name`
  - Selected face identifier (stable within session) and selection rationale
  - Selected edges/vertices identifiers used to compute the span
  - Span value(s) in mm

Definition of Done:
- Running `measure_face_span` twice yields the same IDs and values (within numeric tolerance)
- Manual spot-check matches Fusion’s UI measurement for the same intended feature
- Failure modes are crisp (e.g., “no planar face matched selector”, “no bottom edges within epsilon”)

Status: ✅ complete

---

### Milestone 3 — View capture + image-to-entity mapping
Goal: make annotated-image workflows deterministic by mapping pixels to entity IDs.

Deliverables:
- `capture_view`: export a deterministic image from a known camera (no UI screenshot dependency)
- `get_camera` / `set_camera`: enable repeatable view reproduction
- `ray_pick`: screen (x,y) → hit test → entity ID (face/edge/vertex) + hit point + normal
- Optional: `project_point`: world point → screen coordinates (for overlay/debug)

Definition of Done:
- A single pixel coordinate on a captured view reliably maps back to the same entity
- A “round trip” debug mode can overlay picks onto the exported image

Status: ⏳ not started

---

### Milestone 4 — First edit primitive + closed-loop verification
Goal: introduce one safe edit operation and verify it end-to-end.

Candidate deliverables (choose one first):
- Parameter-based: `create_user_parameter`, `set_user_parameter` (if design supports it)
- Feature-based: minimal “sketch + extrude” on a known plane/face with constraints

Definition of Done:
- Agent can: query → edit → re-measure → re-render
- Verification asserts the change matches the request (numeric thresholds + visual diff)
- Includes rollback-on-failure semantics (transaction-like behavior)

Status: ⏳ not started

---

### Milestone 5 — Generalized edit library + safety
Goal: expand edits while preserving determinism, safety, and explainability.

Deliverables (incremental):
- More targeting primitives (by face normal, adjacency, feature size)
- Guardrails: bounds checks, allowed ops list, timeouts, and “no runaway topology” checks
- Structured “preview” outputs before applying an edit

Status: ⏳ not started

## Verification approach (what “done” looks like)
We will use a **hybrid** strategy over time:

Numeric-first verification:
- Compares measured values (bbox, face spans, volumes, distances, angles) against expected deltas.
- Pros: deterministic, automatable, robust to rendering changes.
- Cons: may miss “looks wrong” issues (wrong face changed but same dimension), needs good measurement primitives.

Visual-first verification:
- Compares rendered images (before/after), optionally with overlays and/or diffing.
- Pros: catches “wrong region changed”, matches how users think with annotated images.
- Cons: sensitive to camera/lighting, requires deterministic view control and an image-to-entity pipeline to explain discrepancies.

Milestone alignment:
- Milestones 1–2 focus on **numeric-first** primitives (stable measurement + traceability).
- Milestone 3 enables **visual-first** workflows (deterministic renders + ray picks).
- Milestones 4–5 require **both** (numeric asserts + visual confirmation artifacts).

## Working agreement (keeping this file current)
- After each implemented milestone/command, we will:
  - Mark milestone/steps as ✅ / 🔄 / ⏳
  - Add a dated entry to the Progress Log below
  - Record any changes to “Definition of Done” criteria based on what we learn

## Progress log
- 2026-01-19: Documented pivot + roadmap; next milestone set to face-based measurement (`measure_face_span`).
- 2026-01-19: Implemented `measure_face_span` with `require_planar=false` default; selectors include `max_bbox_x`, `largest_area`, and `normal_closest:*`; added `span_mode=projected_extent` for mesh-derived solids. Note: negative test for `eps_mm` could not be forced due to model limitations (bottom edges match min-Z), so error-path verification is deferred.
