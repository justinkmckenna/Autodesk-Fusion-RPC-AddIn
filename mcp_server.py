#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime

try:
    import pyautogui
except Exception as exc:  # pragma: no cover
    pyautogui = None

CALIBRATION_PATH = os.environ.get(
    "FUSION_MCP_CALIBRATION",
    os.path.join(os.path.dirname(__file__), "calibration.json"),
)
LOG_ROOT = os.environ.get(
    "FUSION_MCP_LOG_ROOT",
    os.path.join(os.path.dirname(__file__), "logs"),
)

FOCUS_REGION = None


def _now_stamp():
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _load_calibration():
    if not os.path.exists(CALIBRATION_PATH):
        return {}
    try:
        with open(CALIBRATION_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _log_action(payload):
    _ensure_dir(LOG_ROOT)
    path = os.path.join(LOG_ROOT, "mcp_actions.jsonl")
    payload = {"timestamp": datetime.utcnow().isoformat() + "Z", **payload}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _require_pyautogui():
    if pyautogui is None:
        raise RuntimeError(
            "pyautogui not available. Install requirements and grant Accessibility + Screen Recording permissions."
        )


def _capture_screen(region=None):
    _require_pyautogui()
    _ensure_dir(LOG_ROOT)
    capture_dir = os.path.join(LOG_ROOT, "captures")
    _ensure_dir(capture_dir)
    filename = f"capture-{_now_stamp()}.png"
    path = os.path.join(capture_dir, filename)

    if region:
        image = pyautogui.screenshot(region=(region["x"], region["y"], region["width"], region["height"]))
    else:
        image = pyautogui.screenshot()

    image.save(path)
    width, height = image.size
    return path, width, height


def _resolve_region(region, region_name):
    if region:
        return region
    if region_name:
        calibration = _load_calibration()
        return calibration.get(region_name)
    return None


def handle_capture_screen(params):
    region = _resolve_region(params.get("region"), params.get("region_name"))
    path, width, height = _capture_screen(region)
    return {"ok": True, "image_path": path, "width": width, "height": height}


def handle_mouse_click(params):
    _require_pyautogui()
    button = params.get("button", "left")
    pyautogui.click(params["x"], params["y"], button=button)
    return {"ok": True}


def handle_mouse_drag(params):
    _require_pyautogui()
    pyautogui.moveTo(params["from_x"], params["from_y"])
    pyautogui.dragTo(params["to_x"], params["to_y"], duration=0.2, button="left")
    return {"ok": True}


def handle_type_text(params):
    _require_pyautogui()
    pyautogui.write(params["text"], interval=0.01)
    return {"ok": True}


def _normalize_key(key):
    key = key.lower()
    mapping = {
        "cmd": "command",
        "command": "command",
        "ctrl": "ctrl",
        "control": "ctrl",
        "alt": "alt",
        "option": "alt",
        "escape": "esc",
        "return": "enter",
    }
    return mapping.get(key, key)


def handle_key_press(params):
    _require_pyautogui()
    keys = [_normalize_key(k) for k in params.get("keys", [])]
    if not keys:
        return {"ok": False}
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)
    return {"ok": True}


def handle_mouse_scroll(params):
    _require_pyautogui()
    delta = int(params.get("delta_y", 0))
    steps = int(params.get("steps", 1))
    for _ in range(max(1, steps)):
        pyautogui.scroll(delta)
        time.sleep(0.02)
    return {"ok": True}


def handle_wait(params):
    time.sleep(max(0, params.get("milliseconds", 0)) / 1000.0)
    return {"ok": True}


def handle_save_snapshot(params):
    label = params.get("label", "snapshot")
    snapshot_id = f"{label}-{_now_stamp()}"
    snapshot_dir = os.path.join(LOG_ROOT, "snapshots", snapshot_id)
    _ensure_dir(snapshot_dir)
    metadata = {
        "snapshot_id": snapshot_id,
        "label": label,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "focus_region": FOCUS_REGION,
    }
    with open(os.path.join(snapshot_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
    return {"ok": True, "snapshot_id": snapshot_id, "path": snapshot_dir}


def handle_set_focus_region(params):
    global FOCUS_REGION
    FOCUS_REGION = params.get("region_name")
    return {"ok": True}


def handle_get_screen_info(_params):
    _require_pyautogui()
    width, height = pyautogui.size()
    scale = 1.0
    origin_x = 0
    origin_y = 0
    try:  # best-effort scale detection
        import Quartz

        main_display = Quartz.CGMainDisplayID()
        mode = Quartz.CGDisplayCopyDisplayMode(main_display)
        pixel_width = Quartz.CGDisplayModeGetPixelWidth(mode)
        scale = pixel_width / float(width)
    except Exception:
        pass
    return {
        "ok": True,
        "width": int(width),
        "height": int(height),
        "scale": float(scale),
        "origin_x": int(origin_x),
        "origin_y": int(origin_y),
    }


TOOLS = {
    "capture_screen": handle_capture_screen,
    "mouse_click": handle_mouse_click,
    "mouse_drag": handle_mouse_drag,
    "type_text": handle_type_text,
    "key_press": handle_key_press,
    "mouse_scroll": handle_mouse_scroll,
    "wait": handle_wait,
    "save_snapshot": handle_save_snapshot,
    "set_focus_region": handle_set_focus_region,
    "get_screen_info": handle_get_screen_info,
}


TOOL_SCHEMAS = [
    {
        "name": "capture_screen",
        "description": "Capture a PNG screenshot of the full screen or a region.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                    "required": ["x", "y", "width", "height"],
                },
                "region_name": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mouse_click",
        "description": "Click at screen coordinates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mouse_drag",
        "description": "Drag from one coordinate to another.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_x": {"type": "integer"},
                "from_y": {"type": "integer"},
                "to_x": {"type": "integer"},
                "to_y": {"type": "integer"},
            },
            "required": ["from_x", "from_y", "to_x", "to_y"],
            "additionalProperties": False,
        },
    },
    {
        "name": "type_text",
        "description": "Type literal text.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "key_press",
        "description": "Press one or more keys (supports hotkey combos).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["keys"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mouse_scroll",
        "description": "Scroll vertically by delta_y for a number of steps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "delta_y": {"type": "integer"},
                "steps": {"type": "integer"},
            },
            "required": ["delta_y"],
            "additionalProperties": False,
        },
    },
    {
        "name": "wait",
        "description": "Sleep for the specified milliseconds.",
        "inputSchema": {
            "type": "object",
            "properties": {"milliseconds": {"type": "integer"}},
            "required": ["milliseconds"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_snapshot",
        "description": "Create a snapshot folder with metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_focus_region",
        "description": "Store a focus region hint for logging.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region_name": {
                    "type": "string",
                    "enum": ["canvas", "timeline", "browser", "measure_panel", "sketch_dimension"],
                }
            },
            "required": ["region_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_screen_info",
        "description": "Return current display resolution and scaling.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _write_response(message_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _handle_initialize(_params):
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "fusion-vision-mcp", "version": "0.1.0"},
    }


def _handle_list_tools():
    return {"tools": TOOL_SCHEMAS}


def _handle_call_tool(params):
    name = params.get("name")
    arguments = params.get("arguments", {})
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    try:
        result = TOOLS[name](arguments)
        _log_action({"tool": name, "arguments": arguments, "result": result})
        return {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False}
    except Exception as exc:
        _log_action({"tool": name, "arguments": arguments, "error": str(exc)})
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}


def _process_message(message):
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})

    if method == "initialize":
        return {"id": message_id, "result": _handle_initialize(params)}
    if method in ("tools/list", "list_tools"):
        return {"id": message_id, "result": _handle_list_tools()}
    if method in ("tools/call", "call_tool"):
        return {"id": message_id, "result": _handle_call_tool(params)}
    return {
        "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve_stdio():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _process_message(message)
        _write_response(response["id"], response.get("result"), response.get("error"))


def serve_tcp(host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    while True:
        conn, _addr = server.accept()
        with conn:
            buffer = ""
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    response = _process_message(message)
                    payload = {
                        "jsonrpc": "2.0",
                        "id": response["id"],
                    }
                    if "error" in response:
                        payload["error"] = response["error"]
                    else:
                        payload["result"] = response.get("result")
                    conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fusion MCP server")
    parser.add_argument("--tcp-host", type=str, default=None)
    parser.add_argument("--tcp-port", type=int, default=8765)
    args = parser.parse_args()

    if args.tcp_host:
        serve_tcp(args.tcp_host, args.tcp_port)
    else:
        serve_stdio()
