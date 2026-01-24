import math
import os
import time

import adsk.core
import adsk.fusion

_CAPTURE_SEQ = 0


def _entity_id(entity):
    for attr in ("entityToken", "tempId", "entityId"):
        try:
            value = getattr(entity, attr)
        except Exception:
            continue
        if value is not None:
            return str(value)
    return None


def _round_value(value, precision=6):
    if value is None:
        return None
    rounded = round(float(value), precision)
    if rounded == -0.0:
        return 0.0
    return rounded


def _mm_to_internal(units_mgr, value_mm):
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def _point_mm(convert_mm, units_mgr, point):
    return {
        "x": _round_value(convert_mm(units_mgr, point.x)),
        "y": _round_value(convert_mm(units_mgr, point.y)),
        "z": _round_value(convert_mm(units_mgr, point.z)),
    }


def _vector_mm(convert_mm, units_mgr, vector):
    if vector is None:
        return None
    try:
        x = convert_mm(units_mgr, vector.x)
        y = convert_mm(units_mgr, vector.y)
        z = convert_mm(units_mgr, vector.z)
    except Exception:
        return None
    length = math.sqrt(x * x + y * y + z * z)
    if length > 0.0:
        x /= length
        y /= length
        z /= length
    return {
        "x": _round_value(x),
        "y": _round_value(y),
        "z": _round_value(z),
    }


def _normalize_vector(vector):
    try:
        length = math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)
    except Exception:
        return None
    if length <= 0.0:
        return None
    return adsk.core.Vector3D.create(vector.x / length, vector.y / length, vector.z / length)


def _camera_mode(camera):
    try:
        cam_type = camera.cameraType
    except Exception:
        return "perspective"
    try:
        if cam_type == adsk.core.CameraTypes.OrthographicCameraType:
            return "orthographic"
    except Exception:
        pass
    return "perspective"


def _normalize_camera(camera, units_mgr, convert_mm, viewport=None):
    up_vector = None
    try:
        up_vector = _normalize_vector(camera.upVector)
    except Exception:
        up_vector = None

    eye = camera.eye
    target = camera.target
    if up_vector is None:
        up_vector = camera.upVector

    camera_data = {
        "mode": _camera_mode(camera),
        "eye_mm": _point_mm(convert_mm, units_mgr, eye),
        "target_mm": _point_mm(convert_mm, units_mgr, target),
        "up": _vector_mm(convert_mm, units_mgr, up_vector),
    }

    if camera_data["mode"] == "perspective":
        try:
            camera_data["fov_deg"] = _round_value(math.degrees(camera.perspectiveAngle))
        except Exception:
            camera_data["fov_deg"] = None
    else:
        try:
            ok, width_cm, height_cm = camera.getExtents()
        except Exception:
            ok = False
        if ok:
            width_mm = width_cm * 10.0
            height_mm = height_cm * 10.0
            camera_data["ortho_view_size_mm"] = _round_value(max(width_mm, height_mm))

    if viewport is not None:
        try:
            width = int(viewport.width)
            height = int(viewport.height)
        except Exception:
            width = None
            height = None
        if width and height:
            camera_data["aspect_ratio"] = _round_value(width / height)
            camera_data["viewport_px"] = {"width": width, "height": height}

    return camera_data


def _capture_output_path(width_px, height_px):
    global _CAPTURE_SEQ
    _CAPTURE_SEQ += 1
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}_{width_px}x{height_px}_{_CAPTURE_SEQ:03d}.png"

    base_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    captures_dir = os.path.join(base_dir, "logs", "captures")
    try:
        os.makedirs(captures_dir, exist_ok=True)
        return os.path.join(captures_dir, filename)
    except Exception:
        pass

    fallback_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    fallback_captures = os.path.join(fallback_dir, "logs", "captures")
    try:
        os.makedirs(fallback_captures, exist_ok=True)
        return os.path.join(fallback_captures, filename)
    except Exception:
        return None


def _validate_camera_payload(camera_payload):
    if not isinstance(camera_payload, dict):
        return "camera must be an object"

    mode = camera_payload.get("mode")
    if mode not in ("perspective", "orthographic"):
        return "camera.mode must be 'perspective' or 'orthographic'"

    for field in ("eye_mm", "target_mm", "up"):
        if field not in camera_payload:
            return f"camera.{field} is required"

    if mode == "perspective" and "fov_deg" not in camera_payload:
        return "camera.fov_deg is required for perspective"
    if mode == "orthographic" and "ortho_view_size_mm" not in camera_payload:
        return "camera.ortho_view_size_mm is required for orthographic"

    up = camera_payload.get("up")
    if not isinstance(up, dict):
        return "camera.up must be an object"
    try:
        length = math.sqrt(up.get("x", 0.0) ** 2 + up.get("y", 0.0) ** 2 + up.get("z", 0.0) ** 2)
    except Exception:
        return "camera.up must contain numeric x, y, z"
    if length <= 0.0:
        return "camera.up must be non-zero"

    return None


def _apply_camera_payload(viewport, units_mgr, convert_mm, camera_payload):
    error = _validate_camera_payload(camera_payload)
    if error:
        return None, error

    try:
        camera = viewport.camera
    except Exception:
        return None, "Failed to access viewport camera"

    try:
        camera.isSmoothTransition = False
    except Exception:
        pass
    try:
        camera.isFitView = False
    except Exception:
        pass

    eye = camera_payload.get("eye_mm", {})
    target = camera_payload.get("target_mm", {})
    up = camera_payload.get("up", {})

    try:
        eye_point = adsk.core.Point3D.create(
            _mm_to_internal(units_mgr, float(eye.get("x", 0.0))),
            _mm_to_internal(units_mgr, float(eye.get("y", 0.0))),
            _mm_to_internal(units_mgr, float(eye.get("z", 0.0))),
        )
        target_point = adsk.core.Point3D.create(
            _mm_to_internal(units_mgr, float(target.get("x", 0.0))),
            _mm_to_internal(units_mgr, float(target.get("y", 0.0))),
            _mm_to_internal(units_mgr, float(target.get("z", 0.0))),
        )
        up_vector = adsk.core.Vector3D.create(
            float(up.get("x", 0.0)),
            float(up.get("y", 0.0)),
            float(up.get("z", 0.0)),
        )
    except Exception:
        return None, "camera vectors must be numeric"

    normalized_up = _normalize_vector(up_vector)
    if normalized_up is None:
        return None, "camera.up must be non-zero"

    camera.eye = eye_point
    camera.target = target_point
    camera.upVector = normalized_up

    mode = camera_payload.get("mode")
    if mode == "orthographic":
        try:
            camera.cameraType = adsk.core.CameraTypes.OrthographicCameraType
        except Exception:
            pass
        try:
            size_mm = float(camera_payload.get("ortho_view_size_mm"))
        except Exception:
            return None, "camera.ortho_view_size_mm must be numeric"
        size_cm = _mm_to_internal(units_mgr, size_mm)
        try:
            camera.setExtents(size_cm, size_cm)
        except Exception:
            pass
    else:
        try:
            camera.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
        except Exception:
            pass
        try:
            fov_deg = float(camera_payload.get("fov_deg"))
            camera.perspectiveAngle = math.radians(fov_deg)
        except Exception:
            return None, "camera.fov_deg must be numeric"

    try:
        viewport.camera = camera
    except Exception:
        return None, "Failed to set viewport camera"

    return viewport.camera, None


def _entity_type(entity):
    try:
        obj_type = entity.objectType
    except Exception:
        return None
    if obj_type == adsk.fusion.BRepFace.classType():
        return "face"
    if obj_type == adsk.fusion.BRepEdge.classType():
        return "edge"
    if obj_type == adsk.fusion.BRepVertex.classType():
        return "vertex"
    return None


def _entity_body_name(entity):
    try:
        body = entity.body
        if body:
            return body.name
    except Exception:
        pass
    try:
        faces = entity.faces
        if faces and faces.count > 0:
            return faces.item(0).body.name
    except Exception:
        pass
    return None
