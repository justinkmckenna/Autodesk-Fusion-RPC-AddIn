import adsk.core, adsk.fusion, os

app = adsk.core.Application.get()
viewport = app.activeViewport

# Update output directory and resolution if needed.
# Use an absolute path because Fusion's working directory may be read-only.
out_dir = "/Users/justin/Projects/Autodesk Fusion Vison and MCP/logs/captures"
width_px = 1200
height_px = 900

if not viewport:
    result = {"ok": False, "error": "No active viewport"}
else:
    os.makedirs(out_dir, exist_ok=True)
    captures = {}

    cam = viewport.camera
    cam.viewOrientation = adsk.core.ViewOrientations.TopViewOrientation
    cam.isFitView = True
    viewport.camera = cam
    top_path = out_dir + "/top.png"
    captures["top"] = {"path": top_path, "ok": bool(viewport.saveAsImageFile(top_path, width_px, height_px))}

    cam = viewport.camera
    cam.viewOrientation = adsk.core.ViewOrientations.FrontViewOrientation
    cam.isFitView = True
    viewport.camera = cam
    front_path = out_dir + "/front.png"
    captures["front"] = {"path": front_path, "ok": bool(viewport.saveAsImageFile(front_path, width_px, height_px))}

    cam = viewport.camera
    cam.viewOrientation = adsk.core.ViewOrientations.RightViewOrientation
    cam.isFitView = True
    viewport.camera = cam
    right_path = out_dir + "/right.png"
    captures["right"] = {"path": right_path, "ok": bool(viewport.saveAsImageFile(right_path, width_px, height_px))}

    cam = viewport.camera
    cam.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
    cam.isFitView = True
    viewport.camera = cam
    iso_path = out_dir + "/iso.png"
    captures["iso"] = {"path": iso_path, "ok": bool(viewport.saveAsImageFile(iso_path, width_px, height_px))}

    result = {"ok": True, "captures": captures}
