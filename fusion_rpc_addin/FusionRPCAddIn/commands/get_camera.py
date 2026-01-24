import importlib
import os
import sys

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _view_helpers as view_helpers

importlib.reload(view_helpers)

COMMAND = "get_camera"
REQUIRES_DESIGN = True


def handle(request, context):
    app = context["app"]
    units_mgr = context["units_mgr"]
    convert_mm = context["convert_mm"]

    try:
        viewport = app.activeViewport
    except Exception:
        viewport = None

    if not viewport:
        return {"ok": False, "error": "No active viewport."}

    try:
        camera = viewport.camera
    except Exception:
        return {"ok": False, "error": "Failed to access viewport camera."}

    camera_data = view_helpers._normalize_camera(camera, units_mgr, convert_mm, viewport=viewport)
    viewport_px = camera_data.get("viewport_px")

    return {
        "ok": True,
        "error": None,
        "data": {
            "camera": camera_data,
            "viewport_px": viewport_px,
        },
    }
