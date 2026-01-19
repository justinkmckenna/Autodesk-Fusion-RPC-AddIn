import math

COMMAND = "measure_face_span"
REQUIRES_DESIGN = True


def _list_visible_bodies(root_comp):
    bodies = []
    for body in root_comp.bRepBodies:
        try:
            if body.isVisible and body.isSolid:
                bodies.append(body)
        except Exception:
            continue
    return bodies


def _resolve_body(root_comp, body_name):
    bodies = _list_visible_bodies(root_comp)
    if body_name:
        for body in bodies:
            if body.name == body_name:
                return body, bodies
        return None, bodies
    if len(bodies) == 1:
        return bodies[0], bodies
    return None, bodies


def _entity_id(entity):
    for attr in ("tempId", "entityToken", "entityId"):
        try:
            value = getattr(entity, attr)
        except Exception:
            continue
        if value is not None:
            return str(value)
    return None


def _point_mm(convert_mm, units_mgr, point):
    return {
        "x": convert_mm(units_mgr, point.x),
        "y": convert_mm(units_mgr, point.y),
        "z": convert_mm(units_mgr, point.z),
    }


def _vector_tuple(vector):
    return (vector.x, vector.y, vector.z)


def _centroid_tuple_mm(convert_mm, units_mgr, point):
    return (
        convert_mm(units_mgr, point.x),
        convert_mm(units_mgr, point.y),
        convert_mm(units_mgr, point.z),
    )


def _face_area_mm2(face):
    try:
        # Fusion internal units are cm; area is cm^2 -> mm^2 = *100.
        return face.area * 100.0
    except Exception:
        return None


def _face_bbox(face):
    try:
        return face.boundingBox
    except Exception:
        return None


def _face_normal(face):
    try:
        geom = face.geometry
    except Exception:
        return None
    if not geom:
        return None
    if hasattr(geom, "normal"):
        try:
            return geom.normal
        except Exception:
            return None
    return None


def _parse_face_selector(selector):
    if selector == "max_centroid_x":
        return {"type": "max_centroid_x"}
    if selector == "max_bbox_x":
        return {"type": "max_bbox_x"}
    if selector == "largest_area":
        return {"type": "largest_area"}
    if selector.startswith("normal_closest:"):
        axis = selector.split(":", 1)[1].strip()
        if axis in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
            return {"type": "normal_closest", "axis": axis}
    return None


def _axis_vector(axis):
    if axis == "+X":
        return (1.0, 0.0, 0.0)
    if axis == "-X":
        return (-1.0, 0.0, 0.0)
    if axis == "+Y":
        return (0.0, 1.0, 0.0)
    if axis == "-Y":
        return (0.0, -1.0, 0.0)
    if axis == "+Z":
        return (0.0, 0.0, 1.0)
    if axis == "-Z":
        return (0.0, 0.0, -1.0)
    return (0.0, 0.0, 0.0)


def _normalized_vector(vector):
    try:
        length = math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)
    except Exception:
        return None
    if length <= 0.0:
        return None
    return (vector.x / length, vector.y / length, vector.z / length)


def _axis_for_projection(normal, points):
    # Prefer the in-plane axis (global) with the largest span, excluding the axis most aligned to the normal.
    if normal:
        normalized = _normalized_vector(normal)
    else:
        normalized = None
    axes = ["x", "y", "z"]
    if normalized:
        abs_dot = {
            "x": abs(normalized[0]),
            "y": abs(normalized[1]),
            "z": abs(normalized[2]),
        }
        exclude_axis = max(abs_dot, key=abs_dot.get)
        axes = [axis for axis in axes if axis != exclude_axis]

    ranges = {}
    for axis in axes:
        values = [pt[axis] for pt in points]
        ranges[axis] = max(values) - min(values) if values else 0.0
    if not ranges:
        return "x"
    return max(ranges, key=ranges.get)


def handle(request, context):
    root_comp = context["root_comp"]
    units_mgr = context["units_mgr"]
    convert_mm = context["convert_mm"]

    body_name = request.get("body_name")
    face_selector = request.get("face_selector", "max_centroid_x")
    require_planar = request.get("require_planar", False)
    span_mode = request.get("span_mode", "max_edge_length")
    eps_mm = request.get("eps_mm", 0.05)

    selector = _parse_face_selector(face_selector)
    if not selector:
        return {"ok": False, "error": f"Unsupported face_selector: {face_selector}"}

    try:
        eps_mm = float(eps_mm)
    except Exception:
        return {"ok": False, "error": "eps_mm must be a number"}

    body, bodies = _resolve_body(root_comp, body_name)
    if not body:
        if body_name:
            names = [b.name for b in bodies]
            return {
                "ok": False,
                "error": f"Body not found: {body_name}. Candidates: {names}",
            }
        names = [b.name for b in bodies]
        if not names:
            return {"ok": False, "error": "No visible solid body found."}
        return {
            "ok": False,
            "error": "Multiple visible bodies; specify body_name.",
            "candidates": names,
        }

    try:
        faces = list(body.faces)
    except Exception:
        return {"ok": False, "error": "Failed to enumerate faces."}

    candidates = []
    for face in faces:
        try:
            if require_planar and not face.geometry.isPlane:
                continue
        except Exception:
            if require_planar:
                continue
        centroid = None
        try:
            centroid = face.centroid
        except Exception:
            centroid = None
        if not centroid:
            continue

        area_mm2 = _face_area_mm2(face)
        face_id = _entity_id(face)
        centroid_mm_tuple = _centroid_tuple_mm(convert_mm, units_mgr, centroid)
        score = None

        if selector["type"] == "max_centroid_x":
            score = centroid_mm_tuple[0]
        elif selector["type"] == "max_bbox_x":
            bbox = _face_bbox(face)
            if not bbox:
                continue
            score = convert_mm(units_mgr, bbox.maxPoint.x)
        elif selector["type"] == "largest_area":
            if area_mm2 is None:
                continue
            score = area_mm2
        elif selector["type"] == "normal_closest":
            normal = _face_normal(face)
            if not normal:
                continue
            axis = _axis_vector(selector["axis"])
            score = (
                normal.x * axis[0]
                + normal.y * axis[1]
                + normal.z * axis[2]
            )
        else:
            continue

        candidates.append(
            {
                "face": face,
                "score": score,
                "area_mm2": area_mm2,
                "centroid": centroid,
                "centroid_mm_tuple": centroid_mm_tuple,
                "face_id": face_id,
            }
        )

    if not candidates:
        return {"ok": False, "error": "No faces matched selector."}

    def _tie_key(item):
        area = item["area_mm2"] if item["area_mm2"] is not None else -1.0
        face_id = item["face_id"] if item["face_id"] is not None else ""
        return (
            -item["score"],
            -area,
            item["centroid_mm_tuple"],
            face_id,
        )

    candidates.sort(key=_tie_key)
    selected = candidates[0]["face"]
    selected_id = candidates[0]["face_id"]
    selected_centroid = candidates[0]["centroid"]

    bbox = None
    try:
        bbox = getattr(body, "worldBoundingBox", None) or body.boundingBox
    except Exception:
        bbox = None
    if not bbox:
        return {"ok": False, "error": "Failed to read body bounding box."}

    z_ref_mm = convert_mm(units_mgr, bbox.minPoint.z)

    qualifying_edges = []
    total_edges = 0
    for edge in selected.edges:
        total_edges += 1
        try:
            v0 = edge.startVertex
            v1 = edge.endVertex
            if not v0 or not v1:
                continue
            p0 = v0.geometry
            p1 = v1.geometry
        except Exception:
            continue
        z0_mm = convert_mm(units_mgr, p0.z)
        z1_mm = convert_mm(units_mgr, p1.z)
        if math.fabs(z0_mm - z_ref_mm) > eps_mm or math.fabs(z1_mm - z_ref_mm) > eps_mm:
            continue
        length_mm = convert_mm(units_mgr, edge.length)
        edge_id = _entity_id(edge)
        qualifying_edges.append(
            {
                "edge": edge,
                "id": edge_id,
                "length_mm": length_mm,
                "v0_mm": _point_mm(convert_mm, units_mgr, p0),
                "v1_mm": _point_mm(convert_mm, units_mgr, p1),
            }
        )

    if not qualifying_edges:
        return {
            "ok": False,
            "error": "No bottom edges found within epsilon.",
            "eps_mm": eps_mm,
            "z_ref_mm": z_ref_mm,
        }

    bottom_points = []
    for item in qualifying_edges:
        bottom_points.append(item["v0_mm"])
        bottom_points.append(item["v1_mm"])

    face_normal = _face_normal(selected)
    projection_axis = _axis_for_projection(face_normal, bottom_points) if bottom_points else "x"
    extent_min = min(pt[projection_axis] for pt in bottom_points)
    extent_max = max(pt[projection_axis] for pt in bottom_points)
    projected_extent_mm = extent_max - extent_min

    qualifying_edges.sort(
        key=lambda item: (
            -item["length_mm"],
            item["id"] if item["id"] is not None else "",
        )
    )
    selected_edge = qualifying_edges[0]

    face_bbox = _face_bbox(selected)
    face_bbox_mm = None
    if face_bbox:
        face_bbox_mm = {
            "min": _point_mm(convert_mm, units_mgr, face_bbox.minPoint),
            "max": _point_mm(convert_mm, units_mgr, face_bbox.maxPoint),
        }

    face_normal_out = None
    if face_normal:
        face_normal_out = {
            "x": face_normal.x,
            "y": face_normal.y,
            "z": face_normal.z,
        }

    span = {
        "mode": "max_edge_length",
        "value_mm": selected_edge["length_mm"],
        "edge_id": selected_edge["id"],
        "endpoints_mm": [selected_edge["v0_mm"], selected_edge["v1_mm"]],
    }
    if span_mode == "projected_extent":
        span = {
            "mode": "projected_extent",
            "value_mm": projected_extent_mm,
            "axis": projection_axis,
            "endpoints_mm": [
                {projection_axis: extent_min},
                {projection_axis: extent_max},
            ],
        }

    data = {
        "body": {"name": body.name},
        "face": {
            "selector": face_selector,
            "require_planar": bool(require_planar),
            "id": selected_id,
            "area_mm2": candidates[0]["area_mm2"],
            "centroid_mm": _point_mm(convert_mm, units_mgr, selected_centroid),
            "normal": face_normal_out,
            "bbox_mm": face_bbox_mm,
        },
        "bottom": {
            "eps_mm": eps_mm,
            "z_ref_mm": z_ref_mm,
            "edges": [
                {
                    "id": item["id"],
                    "length_mm": item["length_mm"],
                    "v0_mm": item["v0_mm"],
                    "v1_mm": item["v1_mm"],
                }
                for item in qualifying_edges
            ],
        },
        "span": span,
        "trace": {
            "candidates_considered": {
                "faces": len(candidates),
                "edges": total_edges,
            }
        },
    }

    return {"ok": True, "error": None, "data": data}
