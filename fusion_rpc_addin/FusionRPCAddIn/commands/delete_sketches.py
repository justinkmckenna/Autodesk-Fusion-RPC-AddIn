COMMAND = "delete_sketches"
REQUIRES_DESIGN = True


def _iter_sketches(root_comp):
    try:
        sketches = root_comp.sketches
    except Exception:
        return []
    try:
        count = int(sketches.count)
    except Exception:
        count = 0
    items = []
    for idx in range(count):
        try:
            sketch = sketches.item(idx)
        except Exception:
            continue
        if sketch:
            items.append(sketch)
    return items


def handle(request, context):
    root_comp = context.get("root_comp")
    if not root_comp:
        return {"ok": False, "error": "No active design."}

    preview = bool(request.get("preview", False))
    sketches = _iter_sketches(root_comp)
    names = []
    for sketch in sketches:
        try:
            names.append(sketch.name)
        except Exception:
            names.append(None)

    if preview:
        return {"ok": True, "error": None, "data": {"count": len(sketches), "names": names}}

    deleted = 0
    failed = 0
    for sketch in sketches:
        try:
            sketch.deleteMe()
            deleted += 1
        except Exception:
            failed += 1

    return {"ok": True, "error": None, "data": {"deleted": deleted, "failed": failed}}
