import importlib
import os
import sys
import time

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _selection_helpers as selection_helpers

importlib.reload(selection_helpers)

COMMAND = "hole_feature"
REQUIRES_DESIGN = True

MAX_DISTANCE_MM = 100.0
MAX_APPLY_MS = 5000.0
MAX_FACE_DELTA = 200
MAX_EDGE_DELTA = 400
MAX_BODY_DELTA = 1


def _mm_to_internal(units_mgr, value_mm):
    if not units_mgr:
        return value_mm
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def _project_point_to_plane(point, plane):
    try:
        origin = plane.origin
        normal = plane.normal
    except Exception:
        return point
    try:
        vec = adsk.core.Vector3D.create(
            point.x - origin.x,
            point.y - origin.y,
            point.z - origin.z,
        )
        dist = vec.dotProduct(normal)
        return adsk.core.Point3D.create(
            point.x - normal.x * dist,
            point.y - normal.y * dist,
            point.z - normal.z * dist,
        )
    except Exception:
        return point


def _total_counts(bodies):
    totals = {"faces": 0, "edges": 0, "vertices": 0}
    for body in bodies:
        totals["faces"] += selection_helpers._collection_count(body.faces)
        totals["edges"] += selection_helpers._collection_count(body.edges)
        totals["vertices"] += selection_helpers._collection_count(body.vertices)
    return totals


def _find_face_by_id(root_comp, face_id):
    for body in selection_helpers._list_visible_bodies(root_comp):
        for face in body.faces:
            if selection_helpers._entity_id(face) == face_id:
                return face, body
    return None, None


def _find_face_by_token(root_comp, face_token):
    for body in selection_helpers._list_visible_bodies(root_comp):
        for face in body.faces:
            try:
                token = getattr(face, "entityToken")
            except Exception:
                token = None
            if token == face_token:
                return face, body
    return None, None


def handle(request, context):
    design = context.get("design")
    root_comp = context.get("root_comp")
    units_mgr = context.get("units_mgr")
    convert_mm = context.get("convert_mm")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    body_name = request.get("body_name")
    face_selector = request.get("face_selector")
    face_id = request.get("face_id")
    face_token = request.get("face_token")
    center_mm = request.get("center_mm")
    diameter_mm = request.get("diameter_mm")
    depth_mm = request.get("depth_mm")
    through_all = bool(request.get("through_all", False))
    preview = bool(request.get("preview", False))

    if not face_id and not face_token and not face_selector:
        return {"ok": False, "error": "face_selector, face_id, or face_token is required"}

    if not isinstance(center_mm, dict):
        return {"ok": False, "error": "center_mm must be an object with x,y,z"}

    try:
        center = {
            "x": float(center_mm.get("x", 0.0)),
            "y": float(center_mm.get("y", 0.0)),
            "z": float(center_mm.get("z", 0.0)),
        }
        diameter_mm = float(diameter_mm)
    except Exception:
        return {"ok": False, "error": "center_mm and diameter_mm must be numeric"}

    if diameter_mm <= 0:
        return {"ok": False, "error": "diameter_mm must be > 0"}

    if not through_all:
        try:
            depth_mm = float(depth_mm)
        except Exception:
            return {"ok": False, "error": "depth_mm must be numeric when through_all is false"}
        if depth_mm <= 0:
            return {"ok": False, "error": "depth_mm must be > 0"}
        if depth_mm > MAX_DISTANCE_MM:
            return {"ok": False, "error": f"depth_mm exceeds MAX_DISTANCE_MM ({MAX_DISTANCE_MM})"}

    face = None
    body = None
    candidates = []
    if face_token:
        face, body = _find_face_by_token(root_comp, face_token)
        if not face:
            return {"ok": False, "error": f"face_token not found: {face_token}"}
    elif face_id:
        face, body = _find_face_by_id(root_comp, face_id)
        if not face:
            return {"ok": False, "error": f"face_id not found: {face_id}"}
    else:
        selector = selection_helpers._parse_face_selector(face_selector)
        if not selector:
            return {"ok": False, "error": f"Unsupported face_selector: {face_selector}"}
        body, bodies = selection_helpers._resolve_body(root_comp, body_name)
        if not body:
            candidates = sorted([b.name for b in bodies])
            if body_name:
                return {
                    "ok": False,
                    "error": f"Body not found: {body_name}. Candidates: {candidates}",
                    "candidates": candidates,
                }
            if not candidates:
                return {"ok": False, "error": "No visible solid body found.", "candidates": []}
            return {
                "ok": False,
                "error": "Multiple visible bodies; specify body_name.",
                "candidates": candidates,
            }
        selected, candidate_count = selection_helpers._select_face(body, selector, units_mgr, convert_mm)
        if not selected:
            return {"ok": False, "error": "No faces matched selector."}
        face = selected["face"]

    plan = {
        "body_name": getattr(body, "name", None),
        "face": {
            "id": selection_helpers._entity_id(face),
            "token": getattr(face, "entityToken", None),
            "selector": face_selector,
        },
        "center_mm": center,
        "diameter_mm": diameter_mm,
        "depth_mm": depth_mm if not through_all else None,
        "through_all": through_all,
    }

    if preview:
        return {
            "ok": True,
            "error": None,
            "data": {
                "preview": {"is_preview": True, "plan": plan},
                "apply": None,
            },
        }

    before_visible = selection_helpers._list_visible_bodies(root_comp)
    before_counts = _total_counts(before_visible)
    before_body_count = len(before_visible)

    feature = None
    compute_ran = False
    start_time = time.time()
    try:
        sketch = root_comp.sketches.add(face)
        center_internal = adsk.core.Point3D.create(
            _mm_to_internal(units_mgr, center["x"]),
            _mm_to_internal(units_mgr, center["y"]),
            _mm_to_internal(units_mgr, center["z"]),
        )
        try:
            geom = face.geometry
        except Exception:
            geom = None
        if geom:
            try:
                if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                    center_internal = _project_point_to_plane(center_internal, geom)
            except Exception:
                try:
                    if geom.isPlane:
                        center_internal = _project_point_to_plane(center_internal, geom)
                except Exception:
                    pass
        try:
            center_internal = sketch.modelToSketchSpace(center_internal)
        except Exception:
            pass
        radius_internal = _mm_to_internal(units_mgr, diameter_mm * 0.5)
        sketch.sketchCurves.sketchCircles.addByCenterRadius(center_internal, radius_internal)
        profile = sketch.profiles.item(0)

        extrudes = root_comp.features.extrudeFeatures
        ext_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
        if body:
            body_collection = adsk.core.ObjectCollection.create()
            body_collection.add(body)
            try:
                ext_input.participantBodies = body_collection
            except Exception:
                try:
                    ext_input.setParticipantBodies(body_collection)
                except Exception:
                    pass
        if through_all:
            try:
                ext_input.setThroughAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
            except Exception:
                try:
                    ext_input.setThroughAllExtent(adsk.fusion.ExtentDirections.PositiveExtentDirection)
                except Exception:
                    pass
        else:
            distance_internal = _mm_to_internal(units_mgr, depth_mm)
            try:
                ext_input.setDistanceExtent(True, adsk.core.ValueInput.createByReal(distance_internal))
            except Exception:
                ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(distance_internal))
        ext_input.isSolid = True
        feature = extrudes.add(ext_input)
        try:
            design.computeAll()
            compute_ran = True
        except Exception:
            pass
        timing_ms = (time.time() - start_time) * 1000.0
    except Exception as exc:
        if feature:
            try:
                feature.deleteMe()
            except Exception:
                pass
        return {"ok": False, "error": f"Hole feature failed: {exc}", "data": {"preview": {"plan": plan}}}

    after_visible = selection_helpers._list_visible_bodies(root_comp)
    after_counts = _total_counts(after_visible)
    after_body_count = len(after_visible)

    guardrail_error = None
    if (time.time() - start_time) * 1000.0 > MAX_APPLY_MS:
        guardrail_error = f"Apply exceeded MAX_APPLY_MS ({MAX_APPLY_MS} ms)"
    elif after_counts["faces"] - before_counts["faces"] > MAX_FACE_DELTA:
        guardrail_error = f"face_count_delta exceeded MAX_FACE_DELTA ({MAX_FACE_DELTA})"
    elif after_counts["edges"] - before_counts["edges"] > MAX_EDGE_DELTA:
        guardrail_error = f"edge_count_delta exceeded MAX_EDGE_DELTA ({MAX_EDGE_DELTA})"
    elif after_body_count - before_body_count > MAX_BODY_DELTA:
        guardrail_error = f"body_count_delta exceeded MAX_BODY_DELTA ({MAX_BODY_DELTA})"

    if guardrail_error:
        try:
            feature.deleteMe()
            design.computeAll()
        except Exception:
            pass
        return {"ok": False, "error": guardrail_error, "data": {"preview": {"plan": plan}}}

    return {
        "ok": True,
        "error": None,
        "data": {
            "preview": {"is_preview": False, "plan": plan},
            "apply": {
                "feature": {"id": selection_helpers._entity_id(feature), "name": getattr(feature, "name", None)},
                "compute": {"ran": compute_ran},
                "timing_ms": timing_ms,
            },
        },
    }
