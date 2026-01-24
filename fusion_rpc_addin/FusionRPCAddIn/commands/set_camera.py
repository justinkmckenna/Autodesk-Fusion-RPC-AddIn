import importlib
import os
import sys

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _view_helpers as view_helpers

importlib.reload(view_helpers)

COMMAND = "set_camera"
REQUIRES_DESIGN = True


def handle(request, context):
    app = context["app"]
    units_mgr = context["units_mgr"]
    convert_mm = context["convert_mm"]

    camera_payload = request.get("camera")
    if camera_payload is None:
        return {"ok": False, "error": "camera is required"}

    try:
        viewport = app.activeViewport
    except Exception:
        viewport = None

    if not viewport:
        return {"ok": False, "error": "No active viewport."}

    camera, error = view_helpers._apply_camera_payload(viewport, units_mgr, convert_mm, camera_payload)
    if error:
        return {"ok": False, "error": error}

    camera_data = view_helpers._normalize_camera(camera, units_mgr, convert_mm, viewport=viewport)

    return {
        "ok": True,
        "error": None,
        "data": {"camera": camera_data},
    }
