COMMAND = "delete_body"
REQUIRES_DESIGN = True


def handle(request, context):
    root_comp = context["root_comp"]
    find_body = context["find_body"]

    body_name = request.get("body_name")
    if not body_name:
        return {"ok": False, "error": "Missing required parameter: body_name"}

    body = find_body(root_comp, body_name)
    if not body:
        return {"ok": False, "error": f"No visible solid body found: {body_name}"}

    try:
        body.deleteMe()
    except Exception:
        return {"ok": False, "error": f"Failed to delete body: {body_name}"}

    return {"ok": True, "error": None, "data": {"body_name": body_name}}
