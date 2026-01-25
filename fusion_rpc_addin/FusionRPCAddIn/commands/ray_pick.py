import importlib
import math
import os
import sys

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _view_helpers as view_helpers

importlib.reload(view_helpers)

COMMAND = "ray_pick"
REQUIRES_DESIGN = True


def _collect_hits(root_comp, origin, direction, entity_type):
    try:
        hit_points = adsk.core.ObjectCollection.create()
    except Exception:
        return []

    try:
        hits = root_comp.findBRepUsingRay(origin, direction, entity_type, -1.0, True, hit_points)
    except Exception:
        return []

    if not hits:
        return []

    results = []
    try:
        count = hits.count
    except Exception:
        return results

    for idx in range(count):
        try:
            entity = hits.item(idx)
        except Exception:
            continue
        try:
            hit_point = hit_points.item(idx)
        except Exception:
            hit_point = None
        results.append((entity, hit_point))

    return results


def _distance_mm(units_mgr, convert_mm, origin, point):
    try:
        distance_internal = origin.distanceTo(point)
    except Exception:
        return None
    try:
        return round(float(convert_mm(units_mgr, distance_internal)), 6)
    except Exception:
        return None


def _normal_for_hit(entity, hit_point, units_mgr, convert_mm):
    try:
        if entity.objectType != adsk.fusion.BRepFace.classType():
            return None
    except Exception:
        return None
    try:
        success, normal = entity.evaluator.getNormalAtPoint(hit_point)
    except Exception:
        return None
    if not success:
        return None
    return view_helpers._vector_mm(convert_mm, units_mgr, normal)


def handle(request, context):
    app = context["app"]
    units_mgr = context["units_mgr"]
    convert_mm = context["convert_mm"]
    root_comp = context["root_comp"]

    try:
        x_px = int(request.get("x_px"))
        y_px = int(request.get("y_px"))
        width_px = int(request.get("width_px"))
        height_px = int(request.get("height_px"))
    except Exception:
        return {"ok": False, "error": "x_px, y_px, width_px, height_px must be integers"}

    if width_px <= 0 or height_px <= 0:
        return {"ok": False, "error": "width_px and height_px must be positive"}

    if x_px < 0 or y_px < 0 or x_px >= width_px or y_px >= height_px:
        return {"ok": False, "error": "x_px and y_px must be within the image bounds"}

    try:
        viewport = app.activeViewport
    except Exception:
        viewport = None

    if not viewport:
        return {"ok": False, "error": "No active viewport."}

    camera_payload = request.get("camera")
    if camera_payload:
        _camera, error = view_helpers._apply_camera_payload(viewport, units_mgr, convert_mm, camera_payload)
        if error:
            return {"ok": False, "error": error}

    try:
        viewport_width = float(viewport.width)
        viewport_height = float(viewport.height)
    except Exception:
        return {"ok": False, "error": "Failed to read viewport size"}

    if viewport_width <= 0 or viewport_height <= 0:
        return {"ok": False, "error": "Invalid viewport size"}

    scale_x = viewport_width / float(width_px)
    scale_y = viewport_height / float(height_px)

    view_x = float(x_px) * scale_x
    view_y = float(y_px) * scale_y

    try:
        view_point = adsk.core.Point2D.create(view_x, view_y)
    except Exception:
        return {"ok": False, "error": "Failed to create view point"}

    try:
        model_point = viewport.viewToModelSpace(view_point)
    except Exception:
        return {"ok": False, "error": "Failed to map view to model space"}

    try:
        camera = viewport.camera
        eye = camera.eye
        target = camera.target
    except Exception:
        return {"ok": False, "error": "Failed to read camera eye/target"}

    view_direction = adsk.core.Vector3D.create(
        target.x - eye.x,
        target.y - eye.y,
        target.z - eye.z,
    )
    if view_direction.length == 0:
        return {"ok": False, "error": "Invalid camera view direction"}
    view_direction.normalize()

    if view_helpers._camera_mode(camera) == "orthographic":
        origin = model_point
        direction = view_direction
    else:
        origin = eye
        direction = adsk.core.Vector3D.create(
            model_point.x - eye.x,
            model_point.y - eye.y,
            model_point.z - eye.z,
        )

    if direction.length == 0:
        return {"ok": False, "error": "Invalid ray direction"}
    direction.normalize()

    hits = []
    entity_types = [
        adsk.fusion.BRepEntityTypes.BRepFaceEntityType,
        adsk.fusion.BRepEntityTypes.BRepEdgeEntityType,
        adsk.fusion.BRepEntityTypes.BRepVertexEntityType,
    ]

    for entity_type in entity_types:
        hits.extend(_collect_hits(root_comp, origin, direction, entity_type))

    if not hits:
        return {"ok": False, "error": "No hit"}

    scored_hits = []
    for entity, hit_point in hits:
        if hit_point is None:
            continue
        entity_type = view_helpers._entity_type(entity)
        if entity_type is None:
            continue
        entity_id = view_helpers._entity_id(entity)
        try:
            entity_token = getattr(entity, "entityToken")
        except Exception:
            entity_token = None
        try:
            entity_temp_id = getattr(entity, "tempId")
        except Exception:
            entity_temp_id = None
        distance_mm = _distance_mm(units_mgr, convert_mm, origin, hit_point)
        if distance_mm is None:
            continue
        scored_hits.append((distance_mm, entity_id or "", entity, hit_point, entity_type, entity_token, entity_temp_id))

    if not scored_hits:
        return {"ok": False, "error": "No hit"}

    scored_hits.sort(key=lambda item: (item[0], item[1]))
    distance_mm, entity_id, entity, hit_point, entity_type, entity_token, entity_temp_id = scored_hits[0]

    hit_mm = view_helpers._point_mm(convert_mm, units_mgr, hit_point)
    normal = _normal_for_hit(entity, hit_point, units_mgr, convert_mm)

    body_name = view_helpers._entity_body_name(entity)

    return {
        "ok": True,
        "error": None,
        "data": {
            "entity": {
                "type": entity_type,
                "id": entity_id,
                "token": entity_token,
                "temp_id": entity_temp_id,
                "body_name": body_name,
            },
            "hit_mm": hit_mm,
            "normal": normal,
            "distance_mm": distance_mm,
            "viewport_px": {"width": width_px, "height": height_px},
        },
    }
