import importlib
import os
import sys

import adsk.core

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _parameter_helpers as parameter_helpers

importlib.reload(parameter_helpers)

COMMAND = "set_user_parameter"
REQUIRES_DESIGN = True


def _snapshot(param, units_mgr):
    if not param:
        return None
    entry = parameter_helpers._parameter_entry(param, units_mgr)
    return {
        "expression": entry.get("expression"),
        "value": entry.get("value"),
        "unit": entry.get("unit"),
    }


def _delete_param(param):
    try:
        param.deleteMe()
        return True
    except Exception:
        return False


def _compute_design(design):
    try:
        design.computeAll()
        return True
    except Exception:
        return False


def handle(request, context):
    design = context.get("design")
    units_mgr = context.get("units_mgr")

    if not design:
        return {"ok": False, "error": "No active design."}

    name = request.get("name")
    expression = request.get("expression")
    if not name:
        return {"ok": False, "error": "Missing required parameter: name"}
    if expression is None:
        return {"ok": False, "error": "Missing required parameter: expression"}

    compute = bool(request.get("compute", True))

    try:
        parameters = design.userParameters
    except Exception:
        parameters = None

    if parameters is None:
        return {"ok": False, "error": "User parameters unavailable."}

    param = parameter_helpers._find_user_parameter(parameters, name)
    previous = _snapshot(param, units_mgr)
    created = False

    try:
        if not param:
            value_input = adsk.core.ValueInput.createByString(expression)
            unit = units_mgr.defaultLengthUnits if units_mgr else ""
            param = parameters.add(name, value_input, unit, "")
            created = True
        else:
            param.expression = expression

        compute_ran = False
        if compute:
            compute_ran = _compute_design(design)
            if not compute_ran:
                raise RuntimeError("Design compute failed")

        current = _snapshot(param, units_mgr)
        return {
            "ok": True,
            "error": None,
            "data": {
                "previous": previous,
                "current": current,
                "compute": {"ran": compute_ran},
            },
        }
    except Exception as exc:
        if param:
            if previous is not None:
                try:
                    param.expression = previous.get("expression")
                    if compute:
                        _compute_design(design)
                except Exception:
                    pass
            elif created:
                _delete_param(param)

        return {
            "ok": False,
            "error": str(exc),
            "data": {
                "previous": previous,
                "attempted": {"expression": expression},
            },
        }
