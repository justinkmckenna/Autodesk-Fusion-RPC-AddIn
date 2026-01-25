import importlib
import os
import sys
import time

import adsk.core

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _selection_helpers as selection_helpers
import _view_helpers as view_helpers

importlib.reload(selection_helpers)
importlib.reload(view_helpers)

COMMAND = "capture_standard_views"
REQUIRES_DESIGN = True

_SEQ = 0


def _safe_float(value, default):
    try:
        return float(value)
    except Exception:
        return default


def _capture_dir():
    base_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    captures_dir = os.path.join(base_dir, "logs", "captures")
    os.makedirs(captures_dir, exist_ok=True)
    return captures_dir


def _capture_path(view_name, width_px, height_px):
    global _SEQ
    _SEQ += 1
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}_{view_name}_{width_px}x{height_px}_{_SEQ:03d}.png"
    return os.path.join(_capture_dir(), filename)


def _normalize(vec):
    length = (vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2) ** 0.5
    if length <= 0.0:
        return (0.0, 0.0, 1.0)
    return (vec[0] / length, vec[1] / length, vec[2] / length)


def _camera_payload(center, view_dir, up, mode, size_mm=None, fov_deg=None, distance_mm=None):
    view_dir = _normalize(view_dir)
    if distance_mm is None:
        distance_mm = (size_mm or 100.0) * 2.0
    eye = {
        "x": center["x"] + view_dir[0] * distance_mm,
        "y": center["y"] + view_dir[1] * distance_mm,
        "z": center["z"] + view_dir[2] * distance_mm,
    }
    payload = {
        "mode": mode,
        "eye_mm": eye,
        "target_mm": center,
        "up": {"x": up[0], "y": up[1], "z": up[2]},
    }
    if mode == "orthographic":
        payload["ortho_view_size_mm"] = size_mm
    else:
        payload["fov_deg"] = fov_deg
    return payload


def _capture(viewport, units_mgr, convert_mm, view_name, width_px, height_px, camera_payload):
    camera, error = view_helpers._apply_camera_payload(viewport, units_mgr, convert_mm, camera_payload)
    if error:
        return None, error

    image_path = _capture_path(view_name, width_px, height_px)
    try:
        success = viewport.saveAsImageFile(image_path, width_px, height_px)
    except Exception:
        success = False
    if not success:
        return None, "Viewport image capture failed"

    camera_data = view_helpers._normalize_camera(camera, units_mgr, convert_mm, viewport=viewport)
    return {"image_path": image_path, "camera": camera_data}, None


def _capture_home(viewport, units_mgr, convert_mm, view_name, width_px, height_px):
    try:
        viewport.goHome()
    except Exception:
        return None, "Failed to set home view"

    time.sleep(0.05)
    try:
        camera = viewport.camera
    except Exception:
        return None, "Failed to access viewport camera"

    image_path = _capture_path(view_name, width_px, height_px)
    try:
        success = viewport.saveAsImageFile(image_path, width_px, height_px)
    except Exception:
        success = False
    if not success:
        return None, "Viewport image capture failed"

    camera_data = view_helpers._normalize_camera(camera, units_mgr, convert_mm, viewport=viewport)
    return {"image_path": image_path, "camera": camera_data}, None


def handle(request, context):
    app = context["app"]
    root_comp = context["root_comp"]
    units_mgr = context["units_mgr"]
    convert_mm = context["convert_mm"]

    body_name = request.get("body_name")
    width_px = int(request.get("width_px", 1200))
    height_px = int(request.get("height_px", 800))
    padding = _safe_float(request.get("padding", 1.15), 1.15)
    views = request.get("views") or ["top", "front", "right", "isometric"]

    if width_px <= 0 or height_px <= 0:
        return {"ok": False, "error": "width_px and height_px must be positive integers"}

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
            return {"ok": False, "error": "No solid bodies found.", "candidates": []}
        return {
            "ok": False,
            "error": "Multiple bodies found; specify body_name.",
            "candidates": candidates,
        }

    bbox = selection_helpers._bbox_mm(body, units_mgr, convert_mm)
    if not bbox:
        return {"ok": False, "error": "Failed to read body bounding box."}

    size = bbox["size"]
    center = {
        "x": (bbox["min"]["x"] + bbox["max"]["x"]) * 0.5,
        "y": (bbox["min"]["y"] + bbox["max"]["y"]) * 0.5,
        "z": (bbox["min"]["z"] + bbox["max"]["z"]) * 0.5,
    }

    size_x = max(size["x"], 1e-6)
    size_y = max(size["y"], 1e-6)
    size_z = max(size["z"], 1e-6)

    top_size = max(size_x, size_y) * padding
    front_size = max(size_x, size_z) * padding
    right_size = max(size_y, size_z) * padding

    try:
        viewport = app.activeViewport
    except Exception:
        viewport = None
    if not viewport:
        return {"ok": False, "error": "No active viewport."}

    results = {}
    errors = {}

    for view in views:
        view_key = str(view).lower()
        payload = None
        if view_key == "top":
            payload = _camera_payload(center, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), "orthographic", size_mm=top_size)
        elif view_key == "front":
            # Front should look toward -Y so the min-Y face is visible.
            payload = _camera_payload(center, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), "orthographic", size_mm=front_size)
        elif view_key == "right":
            payload = _camera_payload(center, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "orthographic", size_mm=right_size)
        elif view_key in ("iso", "isometric", "home"):
            data, error = _capture_home(viewport, units_mgr, convert_mm, view_key, width_px, height_px)
            if error:
                errors[view_key] = error
            else:
                results[view_key] = data
            continue
        else:
            errors[view_key] = "Unsupported view"
            continue

        data, error = _capture(viewport, units_mgr, convert_mm, view_key, width_px, height_px, payload)
        if error:
            errors[view_key] = error
        else:
            results[view_key] = data

    return {
        "ok": len(errors) == 0,
        "error": None if not errors else "One or more captures failed",
        "data": {
            "body": {"name": body.name, "id": selection_helpers._entity_id(body)},
            "captures": results,
            "errors": errors,
            "views": views,
            "width_px": width_px,
            "height_px": height_px,
        },
    }
