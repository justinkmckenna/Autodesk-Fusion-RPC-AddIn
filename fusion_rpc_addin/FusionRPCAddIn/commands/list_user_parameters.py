import importlib
import os
import sys

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.append(_MODULE_DIR)

import _parameter_helpers as parameter_helpers

importlib.reload(parameter_helpers)

COMMAND = "list_user_parameters"
REQUIRES_DESIGN = True


def handle(_request, context):
    design = context.get("design")
    units_mgr = context.get("units_mgr")

    if not design:
        return {"ok": False, "error": "No active design."}

    try:
        parameters = design.userParameters
    except Exception:
        parameters = None

    if parameters is None:
        return {"ok": False, "error": "User parameters unavailable."}

    entries = []
    for param in parameter_helpers._iter_user_parameters(parameters):
        try:
            entries.append(parameter_helpers._parameter_entry(param, units_mgr))
        except Exception:
            continue

    entries.sort(key=lambda item: (item.get("name") or ""))

    return {"ok": True, "error": None, "data": {"parameters": entries}}
