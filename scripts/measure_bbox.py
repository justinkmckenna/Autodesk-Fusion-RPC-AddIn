import adsk.core, adsk.fusion

app = adsk.core.Application.get()

design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent if design else None

body_name = locals().get("body_name")

if not root:
    result = {"ok": False, "error": "No active design"}
elif not body_name:
    result = {"ok": False, "error": "Missing body_name input"}
else:
    body = None
    for b in root.bRepBodies:
        if b.isVisible and b.isSolid and b.name == body_name:
            body = b
            break
    if not body:
        result = {"ok": False, "error": f"Body not found: {body_name}"}
    else:
        bbox = body.boundingBox
        dx = (bbox.maxPoint.x - bbox.minPoint.x) * 10.0
        dy = (bbox.maxPoint.y - bbox.minPoint.y) * 10.0
        dz = (bbox.maxPoint.z - bbox.minPoint.z) * 10.0
        result = {"ok": True, "bbox_mm": {"x": dx, "y": dy, "z": dz}}
