import contextlib
import io
import json
import os
import queue
import socket
import tempfile
import threading
import time
import traceback

_EARLY_LOG_PATH = None


def _write_early_log(message):
    global _EARLY_LOG_PATH
    if not _EARLY_LOG_PATH:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            _EARLY_LOG_PATH = os.path.join(base_dir, "FusionRPCAddIn_debug.log")
        except Exception:
            return
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(_EARLY_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


_write_early_log("FusionRPCAddIn: module import start")
try:
    import adsk.core
    import adsk.fusion
    _write_early_log("FusionRPCAddIn: adsk imports complete")
except Exception:
    _write_early_log("FusionRPCAddIn: adsk import failed:\n" + traceback.format_exc())
    raise

CUSTOM_EVENT_ID = "com.justin.fusion_rpc"
DEFAULT_PORT = 8766

_app = None
_ui = None
_server_thread = None
_server_stop = threading.Event()
_server_socket = None
_request_queue = queue.Queue()
_handlers = []
_log_path = None
_log_dir = None
def _log(message):
    if not _log_path:
        _write_early_log(message)
        return
    try:
        with open(_log_path, "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except Exception:
        pass


def _format_exception():
    return traceback.format_exc()


def _find_body(root_comp, body_name=None):
    for body in root_comp.bRepBodies:
        try:
            if not body.isVisible or not body.isSolid:
                continue
        except Exception:
            continue
        if body_name:
            if body.name == body_name:
                return body
        else:
            return body
    return None


def _convert_mm(units_mgr, value):
    try:
        return units_mgr.convert(value, units_mgr.internalUnits, "mm")
    except Exception:
        # Internal units are cm; fallback conversion.
        return value * 10.0


class RpcEventHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            while True:
                request, done_event, response_holder = _request_queue.get_nowait()
                response = _handle_request(request)
                response_holder["response"] = response
                done_event.set()
        except queue.Empty:
            return
        except Exception:
            _log("Handler error:\n" + _format_exception())


def _get_custom_event(app, event_id):
    if hasattr(app, "customEvent"):
        try:
            return app.customEvent(event_id)
        except Exception:
            return None
    if hasattr(app, "customEvents"):
        try:
            return app.customEvents.itemById(event_id)
        except Exception:
            return None
    return None


def _register_custom_event(app, event_id, handler):
    if hasattr(app, "customEvents"):
        try:
            custom_event = app.customEvents.itemById(event_id)
        except Exception:
            custom_event = None
        if not custom_event:
            custom_event = app.customEvents.add(event_id)
        custom_event.add(handler)
        return True
    if hasattr(app, "addCustomEventHandler"):
        if hasattr(app, "registerCustomEvent"):
            app.registerCustomEvent(event_id)
        app.addCustomEventHandler(event_id, handler)
        return True
    if hasattr(app, "registerCustomEvent"):
        custom_event = app.registerCustomEvent(event_id)
        if custom_event:
            custom_event.add(handler)
            return True
    custom_event = _get_custom_event(app, event_id)
    if custom_event:
        custom_event.add(handler)
        return True
    return False


def _unregister_custom_event(app, event_id):
    if hasattr(app, "customEvents"):
        try:
            custom_event = app.customEvents.itemById(event_id)
        except Exception:
            custom_event = None
        if custom_event:
            try:
                app.customEvents.remove(custom_event)
            except Exception:
                pass
        return
    if hasattr(app, "removeCustomEventHandler"):
        try:
            app.removeCustomEventHandler(event_id)
        except Exception:
            pass
        return
    if hasattr(app, "unregisterCustomEvent"):
        try:
            app.unregisterCustomEvent(event_id)
        except Exception:
            pass


def _handle_request(request):
    response = {"ok": False}
    if isinstance(request, dict) and "id" in request:
        response["id"] = request.get("id")

    try:
        cmd = request.get("cmd")
        if cmd == "help":
            response.update({"ok": True, "commands": ["run_python"]})
            return response
        if cmd != "run_python":
            response.update({"ok": False, "error": f"Unknown command: {cmd}"})
            return response

        design = adsk.fusion.Design.cast(_app.activeProduct)
        root_comp = design.rootComponent if design else None
        units_mgr = design.unitsManager if design else None

        context = {
            "app": _app,
            "ui": _ui,
            "design": design,
            "root_comp": root_comp,
            "units_mgr": units_mgr,
            "log": _log,
            "find_body": _find_body,
            "convert_mm": _convert_mm,
        }
        response.update(_handle_run_python(request, context))
        return response
    except Exception:
        response.update({"ok": False, "error": _format_exception()})
        return response


def _safe_json_value(value):
    try:
        json.dumps(value)
        return value
    except Exception:
        return repr(value)


def _handle_run_python(request, context):
    code = request.get("code")
    if not code:
        return {"ok": False, "error": "Missing code"}
    inputs = request.get("inputs") or {}
    if not isinstance(inputs, dict):
        return {"ok": False, "error": "inputs must be a dict"}
    capture_stdout = bool(request.get("capture_stdout", True))
    result_var = request.get("result_var", "result")
    label = request.get("label", "")

    code_len = len(code)
    snippet = code[:200].replace("\n", "\\n")
    if label:
        _log(f"run_python label={label} code_len={code_len} snippet={snippet}")
    else:
        _log(f"run_python code_len={code_len} snippet={snippet}")

    exec_globals = {"adsk": adsk, "__builtins__": __builtins__}
    exec_locals = dict(context)
    exec_locals.update(inputs)

    stdout_buf = io.StringIO() if capture_stdout else None
    start = time.time()
    try:
        if capture_stdout:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stdout_buf):
                exec(code, exec_globals, exec_locals)
        else:
            exec(code, exec_globals, exec_locals)
        elapsed_ms = int((time.time() - start) * 1000)
        result_value = exec_locals.get(result_var)
        response = {
            "ok": True,
            "result": _safe_json_value(result_value),
            "timing_ms": elapsed_ms,
            "log_path": _log_path,
        }
        if capture_stdout:
            response["stdout"] = stdout_buf.getvalue()
        return response
    except Exception:
        elapsed_ms = int((time.time() - start) * 1000)
        response = {
            "ok": False,
            "error": _format_exception(),
            "timing_ms": elapsed_ms,
            "log_path": _log_path,
        }
        if capture_stdout:
            response["stdout"] = stdout_buf.getvalue()
        return response


def _server_loop(port):
    global _server_socket
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(("127.0.0.1", port))
    _server_socket.listen(5)
    _server_socket.settimeout(0.5)
    _log(f"FusionRPCAddIn listening on 127.0.0.1:{port}")

    while not _server_stop.is_set():
        try:
            conn, _addr = _server_socket.accept()
        except socket.timeout:
            continue
        except Exception:
            break
        with conn:
            conn.settimeout(1.0)
            try:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue
                request = json.loads(data.decode("utf-8"))
                _log("FusionRPCAddIn: received request: {}".format(request))
                done_event = threading.Event()
                response_holder = {}
                _request_queue.put((request, done_event, response_holder))
                fired = False
                try:
                    fired = _app.fireCustomEvent(CUSTOM_EVENT_ID)
                except Exception:
                    _log("FusionRPCAddIn: fireCustomEvent failed:\n" + _format_exception())
                _log("FusionRPCAddIn: fireCustomEvent returned {}".format(fired))
                if done_event.wait(10.0):
                    response = response_holder.get("response", {"ok": False, "error": "No response"})
                    _log("FusionRPCAddIn: response ready")
                else:
                    _log("FusionRPCAddIn: timeout waiting for Fusion API response")
                    response = {"ok": False, "error": "Timeout waiting for Fusion API"}
                conn.sendall(json.dumps(response).encode("utf-8"))
            except Exception:
                err = {"ok": False, "error": _format_exception()}
                try:
                    conn.sendall(json.dumps(err).encode("utf-8"))
                except Exception:
                    pass

    try:
        _server_socket.close()
    except Exception:
        pass


def run(context):
    global _app, _ui, _server_thread, _log_path
    _write_early_log("FusionRPCAddIn: run() entered")
    _app = adsk.core.Application.get()
    _ui = _app.userInterface
    _write_early_log("FusionRPCAddIn: got app/ui")
    try:
        custom_attrs = [name for name in dir(_app) if "custom" in name.lower()]
        _write_early_log("FusionRPCAddIn: app custom attrs: " + ", ".join(custom_attrs))
    except Exception:
        _write_early_log("FusionRPCAddIn: failed to inspect app custom attrs")

    port = int(os.environ.get("FUSION_RPC_PORT", DEFAULT_PORT))
    global _log_dir
    try:
        user_root = _app.userDataFolder
        _log_dir = os.path.join(user_root, "FusionRPCAddInLogs")
        _write_early_log(f"FusionRPCAddIn: userDataFolder={user_root}")
    except Exception:
        _log_dir = os.path.join(tempfile.gettempdir(), "FusionRPCAddInLogs")
        _write_early_log("FusionRPCAddIn: using temp log dir")
    try:
        os.makedirs(_log_dir, exist_ok=True)
    except Exception:
        _write_early_log("FusionRPCAddIn: failed to create log dir")
        pass
    _log_path = os.path.join(_log_dir, "fusion_rpc_addin.log")
    _log("FusionRPCAddIn run() starting")
    _log(f"Log path: {_log_path}")

    _write_early_log("FusionRPCAddIn: registering custom event")
    handler = RpcEventHandler()
    try:
        _unregister_custom_event(_app, CUSTOM_EVENT_ID)
        _write_early_log("FusionRPCAddIn: unregistered prior custom event (if any)")
        ok = _register_custom_event(_app, CUSTOM_EVENT_ID, handler)
        if not ok:
            raise RuntimeError("Custom event registration returned False.")
        _handlers.append(handler)
        _write_early_log("FusionRPCAddIn: custom event registered")
    except Exception:
        err = _format_exception()
        _write_early_log("FusionRPCAddIn: custom event registration failed:\n" + err)
        if _ui:
            _ui.messageBox("FusionRPCAddIn failed to register custom event:\n{}".format(err))
        return

    _server_stop.clear()
    _write_early_log("FusionRPCAddIn: starting server thread")
    _server_thread = threading.Thread(target=_server_loop, args=(port,), daemon=True)
    _server_thread.start()
    _write_early_log("FusionRPCAddIn: server thread started")

    _write_early_log("FusionRPCAddIn: showing messageBox")
    _ui.messageBox(f"Fusion RPC Add-In started on 127.0.0.1:{port}\nLog: {_log_path}")
    _write_early_log("FusionRPCAddIn: run() completed")


def stop(context):
    try:
        _log("FusionRPCAddIn stop() called")
        _server_stop.set()
        if _server_socket:
            try:
                _server_socket.close()
            except Exception:
                pass
        if _server_thread:
            _server_thread.join(timeout=2.0)
        if _app:
            _unregister_custom_event(_app, CUSTOM_EVENT_ID)
    except Exception:
        if _ui:
            _ui.messageBox("FusionRPCAddIn stop failed:\n{}".format(_format_exception()))
