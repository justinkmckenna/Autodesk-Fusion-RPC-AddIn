def _iter_user_parameters(parameters):
    try:
        for param in parameters:
            yield param
        return
    except Exception:
        pass
    try:
        count = int(parameters.count)
    except Exception:
        count = 0
    for idx in range(count):
        try:
            param = parameters.item(idx)
        except Exception:
            continue
        if param:
            yield param


def _find_user_parameter(parameters, name):
    if not parameters or not name:
        return None
    try:
        param = parameters.itemByName(name)
        if param:
            return param
    except Exception:
        pass
    for param in _iter_user_parameters(parameters):
        try:
            if param.name == name:
                return param
        except Exception:
            continue
    return None


def _safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _parameter_unit(param):
    unit = _safe_get(param, "unit")
    if unit is None:
        unit = ""
    return unit


def _parameter_value(param, units_mgr):
    raw = _safe_get(param, "value")
    if raw is None:
        return None
    unit = _parameter_unit(param)
    if units_mgr and unit:
        try:
            return units_mgr.convert(raw, units_mgr.internalUnits, unit)
        except Exception:
            pass
    try:
        return float(raw)
    except Exception:
        return raw


def _parameter_entry(param, units_mgr):
    data = {
        "name": _safe_get(param, "name"),
        "expression": _safe_get(param, "expression"),
        "value": _parameter_value(param, units_mgr),
        "unit": _parameter_unit(param),
    }
    comment = _safe_get(param, "comment")
    if comment is not None:
        data["comment"] = comment
    is_favorite = _safe_get(param, "isFavorite")
    if is_favorite is not None:
        data["is_favorite"] = bool(is_favorite)
    return data
