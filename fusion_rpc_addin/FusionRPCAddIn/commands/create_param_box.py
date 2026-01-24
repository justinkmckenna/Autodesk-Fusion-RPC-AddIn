import importlib
import os
import sys

import adsk.core
import adsk.fusion

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _parameter_helpers as parameter_helpers

importlib.reload(parameter_helpers)

COMMAND = "create_param_box"
REQUIRES_DESIGN = True


def _mm_to_internal(units_mgr, value_mm):
    if not units_mgr:
        return value_mm
    try:
        return units_mgr.convert(value_mm, "mm", units_mgr.internalUnits)
    except Exception:
        return value_mm / 10.0


def handle(request, context):
    design = context.get("design")
    units_mgr = context.get("units_mgr")
    root_comp = context.get("root_comp")

    if not design or not root_comp:
        return {"ok": False, "error": "No active design."}

    try:
        width_mm = float(request.get("width_mm", 20.0))
        depth_mm = float(request.get("depth_mm", 20.0))
    except Exception:
        return {"ok": False, "error": "width_mm and depth_mm must be numbers"}

    height_param = request.get("height_param", "Height")
    height_expression = request.get("height_expression")
    body_name = request.get("body_name")

    if width_mm <= 0 or depth_mm <= 0:
        return {"ok": False, "error": "width_mm and depth_mm must be positive"}
    if not height_param:
        return {"ok": False, "error": "height_param must be a non-empty string"}

    try:
        parameters = design.userParameters
    except Exception:
        parameters = None

    if parameters is None:
        return {"ok": False, "error": "User parameters unavailable."}

    param = parameter_helpers._find_user_parameter(parameters, height_param)
    created = False
    try:
        if not param:
            expr = height_expression or "30 mm"
            value_input = adsk.core.ValueInput.createByString(expr)
            unit = units_mgr.defaultLengthUnits if units_mgr else ""
            param = parameters.add(height_param, value_input, unit, "")
            created = True
        elif height_expression:
            param.expression = height_expression
    except Exception as exc:
        return {"ok": False, "error": f"Failed to prepare parameter: {exc}"}

    sketch = root_comp.sketches.add(root_comp.xYConstructionPlane)
    width_internal = _mm_to_internal(units_mgr, width_mm)
    depth_internal = _mm_to_internal(units_mgr, depth_mm)
    p1 = adsk.core.Point3D.create(0, 0, 0)
    p2 = adsk.core.Point3D.create(width_internal, depth_internal, 0)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1, p2)

    try:
        profile = sketch.profiles.item(0)
    except Exception:
        profile = None

    if not profile:
        return {"ok": False, "error": "Failed to create sketch profile."}

    extrudes = root_comp.features.extrudeFeatures
    ext_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByString(height_param))
    ext_input.isSolid = True
    try:
        ext = extrudes.add(ext_input)
    except Exception as exc:
        return {"ok": False, "error": f"Extrude failed: {exc}"}

    body = None
    try:
        if ext.bodies.count > 0:
            body = ext.bodies.item(0)
    except Exception:
        body = None

    if body and body_name:
        try:
            body.name = body_name
        except Exception:
            pass

    param_entry = parameter_helpers._parameter_entry(param, units_mgr) if param else None

    return {
        "ok": True,
        "error": None,
        "data": {
            "body_name": getattr(body, "name", None),
            "width_mm": width_mm,
            "depth_mm": depth_mm,
            "height_param": height_param,
            "height_expression": param_entry.get("expression") if param_entry else None,
            "created_parameter": created,
        },
    }
