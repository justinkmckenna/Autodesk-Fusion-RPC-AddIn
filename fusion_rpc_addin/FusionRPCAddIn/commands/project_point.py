import importlib
import math
import os
import sys

import adsk.core

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _view_helpers as view_helpers

importlib.reload(view_helpers)

COMMAND = "project_point"
REQUIRES_DESIGN = True


def _depth_mm(units_mgr, point, camera):
    try:
        origin = camera.eye
        target = camera.target
    except Exception:
        return None

    view_dir = adsk.core.Vector3D.create(
        target.x - origin.x,
        target.y - origin.y,
        target.z - origin.z,
    )
    if view_dir.length == 0:
        return None
    view_dir.normalize()

    vec = adsk.core.Vector3D.create(
        point.x - origin.x,
        point.y - origin.y,
        point.z - origin.z,
    )
    depth_internal = view_dir.dotProduct(vec)
    try:
        return units_mgr.convert(depth_internal, units_mgr.internalUnits, "mm")
    except Exception:
        return depth_internal * 10.0


def handle(request, context):
    app = context["app"]
    units_mgr = context["units_mgr"]

    world_point = request.get("world_point_mm")
    if world_point is None:
        return {"ok": False, "error": "world_point_mm is required"}

    try:
        width_px = int(request.get("width_px"))
        height_px = int(request.get("height_px"))
    except Exception:
        return {"ok": False, "error": "width_px and height_px must be integers"}

    if width_px <= 0 or height_px <= 0:
        return {"ok": False, "error": "width_px and height_px must be positive"}

    try:
        viewport = app.activeViewport
    except Exception:
        viewport = None

    if not viewport:
        return {"ok": False, "error": "No active viewport."}

    camera_payload = request.get("camera")
    if camera_payload:
        _camera, error = view_helpers._apply_camera_payload(viewport, units_mgr, context["convert_mm"], camera_payload)
        if error:
            return {"ok": False, "error": error}

    try:
        point = adsk.core.Point3D.create(
            view_helpers._mm_to_internal(units_mgr, float(world_point.get("x", 0.0))),
            view_helpers._mm_to_internal(units_mgr, float(world_point.get("y", 0.0))),
            view_helpers._mm_to_internal(units_mgr, float(world_point.get("z", 0.0))),
        )
    except Exception:
        return {"ok": False, "error": "world_point_mm must contain numeric x, y, z"}

    try:
        view_point = viewport.modelToViewSpace(point)
    except Exception:
        return {"ok": False, "error": "Failed to project model to view space"}

    try:
        viewport_width = float(viewport.width)
        viewport_height = float(viewport.height)
    except Exception:
        return {"ok": False, "error": "Failed to read viewport size"}

    if viewport_width <= 0 or viewport_height <= 0:
        return {"ok": False, "error": "Invalid viewport size"}

    scale_x = float(width_px) / viewport_width
    scale_y = float(height_px) / viewport_height

    x_px = int(round(view_point.x * scale_x))
    y_px = int(round(view_point.y * scale_y))

    in_view = 0 <= x_px < width_px and 0 <= y_px < height_px

    depth_mm = _depth_mm(units_mgr, point, viewport.camera)
    if depth_mm is not None:
        depth_mm = round(depth_mm, 6)

    return {
        "ok": True,
        "error": None,
        "data": {
            "x_px": x_px,
            "y_px": y_px,
            "depth_mm": depth_mm,
            "in_view": in_view,
        },
    }
