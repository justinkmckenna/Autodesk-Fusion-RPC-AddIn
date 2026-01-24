import importlib
import os
import sys

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _view_helpers as view_helpers

importlib.reload(view_helpers)

COMMAND = "capture_view"
REQUIRES_DESIGN = True


def handle(request, context):
    app = context["app"]
    units_mgr = context["units_mgr"]
    convert_mm = context["convert_mm"]

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
        _camera, error = view_helpers._apply_camera_payload(viewport, units_mgr, convert_mm, camera_payload)
        if error:
            return {"ok": False, "error": error}

    image_path = view_helpers._capture_output_path(width_px, height_px)
    if not image_path:
        return {"ok": False, "error": "Failed to determine capture output path"}

    try:
        success = viewport.saveAsImageFile(image_path, width_px, height_px)
    except Exception:
        success = False

    if not success:
        return {"ok": False, "error": "Viewport image capture failed"}

    camera_data = view_helpers._normalize_camera(viewport.camera, units_mgr, convert_mm, viewport=viewport)

    return {
        "ok": True,
        "error": None,
        "data": {
            "image_path": image_path,
            "width_px": width_px,
            "height_px": height_px,
            "camera": camera_data,
        },
    }
