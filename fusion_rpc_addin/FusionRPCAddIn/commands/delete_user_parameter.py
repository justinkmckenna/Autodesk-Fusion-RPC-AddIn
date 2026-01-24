import importlib
import os
import sys

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _parameter_helpers as parameter_helpers

importlib.reload(parameter_helpers)

COMMAND = "delete_user_parameter"
REQUIRES_DESIGN = True


def handle(request, context):
    design = context.get("design")

    if not design:
        return {"ok": False, "error": "No active design."}

    name = request.get("name")
    if not name:
        return {"ok": False, "error": "Missing required parameter: name"}

    try:
        parameters = design.userParameters
    except Exception:
        parameters = None

    if parameters is None:
        return {"ok": False, "error": "User parameters unavailable."}

    param = parameter_helpers._find_user_parameter(parameters, name)
    if not param:
        return {"ok": False, "error": "User parameter not found"}

    try:
        param.deleteMe()
    except Exception:
        return {"ok": False, "error": f"Failed to delete user parameter: {name}"}

    return {"ok": True, "error": None, "data": {"name": name}}
