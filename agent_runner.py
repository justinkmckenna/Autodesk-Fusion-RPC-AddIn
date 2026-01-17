#!/usr/bin/env python3
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

LOG_ROOT = os.environ.get(
    "FUSION_MCP_LOG_ROOT",
    os.path.join(os.path.dirname(__file__), "logs"),
)
ENV_PATH = os.environ.get(
    "FUSION_ENV_PATH",
    os.path.join(os.path.dirname(__file__), ".env"),
)
CALIBRATION_PATH = os.environ.get(
    "FUSION_MCP_CALIBRATION",
    os.path.join(os.path.dirname(__file__), "calibration.json"),
)


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


def _get_region(calibration, name):
    region = calibration.get(name)
    if not region:
        raise KeyError(f"Region not found in calibration.json: {name}")
    return region


def _load_env():
    if not os.path.exists(ENV_PATH):
        return
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


def _center_of_bbox(bbox):
    return (bbox["x"] + bbox["width"] / 2.0, bbox["y"] + bbox["height"] / 2.0)


def _compute_silhouette_bbox(image_path, threshold=30):
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    px = img.load()
    w, h = img.size
    sample = []
    for y in range(0, min(30, h)):
        for x in range(0, min(30, w)):
            sample.append(px[x, y])
    if not sample:
        return None
    bg = tuple(sum(c[i] for c in sample) // len(sample) for i in range(3))
    bg_brightness = sum(bg) / 3.0

    left = w
    right = 0
    top = h
    bottom = 0
    found = False
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            brightness = (r + g + b) / 3.0
            # Prefer dark pixels (model) vs light grid lines.
            if brightness < bg_brightness - 18:
                found = True
                if x < left:
                    left = x
                if x > right:
                    right = x
                if y < top:
                    top = y
                if y > bottom:
                    bottom = y

    if not found:
        # Fallback to color-difference thresholding.
        left = w
        right = 0
        top = h
        bottom = 0
        found = False
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                r, g, b = px[x, y]
                if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > threshold:
                    found = True
                    if x < left:
                        left = x
                    if x > right:
                        right = x
                    if y < top:
                        top = y
                    if y > bottom:
                        bottom = y
        if not found:
            return None

    return {"left": left, "right": right, "top": top, "bottom": bottom, "width": w, "height": h}


def _find_dark_row_targets(image_path, min_span=80):
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        from PIL import Image
    except Exception:
        return None

    img = Image.open(image_path).convert("RGB")
    px = img.load()
    w, h = img.size
    sample = []
    for y in range(0, min(30, h)):
        for x in range(0, min(30, w)):
            sample.append(px[x, y])
    if not sample:
        return None
    bg = tuple(sum(c[i] for c in sample) // len(sample) for i in range(3))
    bg_brightness = sum(bg) / 3.0

    best = None
    for y in range(0, h, 4):
        left = None
        right = None
        count = 0
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            brightness = (r + g + b) / 3.0
            if brightness < bg_brightness - 18:
                count += 1
                if left is None:
                    left = x
                right = x
        if left is None or right is None or (right - left) < min_span:
            continue
        score = count * (right - left)
        if best is None or score > best["score"]:
            best = {"y": y, "left": left, "right": right, "score": score}
    return best


def _looks_like_measure_panel(image_path):
    if not image_path or not os.path.exists(image_path):
        return False
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        pixels = list(img.getdata())
        total = len(pixels)
        if total == 0:
            return False
        stride = max(1, total // 10000)
        dark = 0
        count = 0
        bright_sum = 0.0
        for idx in range(0, total, stride):
            r, g, b = pixels[idx]
            brightness = (r + g + b) / 3.0
            bright_sum += brightness
            count += 1
            if brightness < 120:
                dark += 1
        mean_brightness = bright_sum / max(1, count)
        dark_ratio = dark / max(1, count)
        return mean_brightness < 190 and dark_ratio > 0.08
    except Exception:
        return False


def _point_in_region(x, y, region):
    return (
        region["x"] <= x <= region["x"] + region["width"]
        and region["y"] <= y <= region["y"] + region["height"]
    )


def _shift_y_below_panel(current_y, panel, canvas):
    new_y = panel["y"] + panel["height"] + 40
    max_y = canvas["y"] + canvas["height"] - 10
    if new_y > max_y:
        new_y = max(canvas["y"] + 10, panel["y"] - 40)
    return new_y


class MCPClient:
    def __init__(self, server_cmd=None, connect_addr=None):
        self.process = None
        self.sock = None
        if connect_addr:
            host, port = connect_addr
            self.sock = socket.create_connection((host, port))
            self.sock_file = self.sock.makefile("rwb")
        else:
            self.process = subprocess.Popen(
                server_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        self._id = 0

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass

    def _send(self, payload):
        data = (json.dumps(payload) + "\n")
        if self.sock:
            self.sock_file.write(data.encode("utf-8"))
            self.sock_file.flush()
        else:
            self.process.stdin.write(data)
            self.process.stdin.flush()

    def _recv(self):
        if self.sock:
            line = self.sock_file.readline()
            if not line:
                raise RuntimeError("MCP server disconnected")
            line = line.decode("utf-8")
        else:
            line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server disconnected")
        return json.loads(line)

    def request(self, method, params=None):
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        response = self._recv()
        if "error" in response:
            raise RuntimeError(response["error"])
        return response.get("result")

    def call_tool(self, name, arguments=None):
        arguments = arguments or {}
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(result.get("content"))
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except Exception:
                return {"raw": text}
        return {}


def vision_stub(image_paths, goal):
    return {
        "schema_version": "1.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ui_state": {
            "app": "Autodesk Fusion",
            "document_name": None,
            "workspace": "Unknown",
            "active_tab": "Unknown",
            "active_command": None,
            "selection_summary": {"selection_type": "unknown", "count": 0},
            "panels_visible": {
                "browser": True,
                "timeline": True,
                "sketch_palette": False,
                "inspect_panel": False,
                "measure_dialog": False,
            },
            "view_mode": {"camera": "unknown", "visual_style": "unknown"},
        },
        "extraction": {
            "sketch_context": {
                "is_editing_sketch": False,
                "sketch_name": None,
                "dimensions_detected": [],
                "constraints_detected": [],
            },
            "measurements": {"measure_dialog_open": False, "entries": []},
            "timeline": {"visible": True, "highlighted_feature": None, "features_visible": []},
            "alerts": [],
        },
        "task_state": {
            "goal": goal,
            "requirements": {
                "units": "mm",
                "must_preserve": [
                    "front_frame_interface",
                    "middle_plate_alignment",
                    "overall_back_plate_outer_dimensions",
                ],
                "must_fit": [
                    "raspberry_pi_3b_board_outline",
                    "mount_hole_pattern",
                    "ports_clearance",
                ],
                "tolerances": {
                    "general_clearance_mm": 0.8,
                    "port_clearance_mm": 1.2,
                    "screw_clearance_mm": 0.4,
                },
            },
            "known_targets": {"pi3b_mount_hole_spacing_mm": {"x": 58.0, "y": 49.0}},
            "progress": {
                "identified_back_plate_component": False,
                "located_mount_feature": False,
                "updated_hole_pattern": False,
                "updated_port_cutouts": False,
                "verification_passed": False,
            },
        },
        "proposed_next_steps": [
            {
                "intent": "request_better_view",
                "target": "canvas",
                "why": "Stub observation only.",
                "needs_confirmation": False,
                "confidence": 0.2,
            }
        ],
        "recapture_plan": [
            {
                "region_name": "canvas",
                "reason": "Ensure we can see the model.",
                "preferred_action": "capture_screen",
            }
        ],
        "confidence": 0.4,
        "notes": "Vision model not yet connected.",
        "image_paths": image_paths,
    }


def _basic_validate_observation(observation):
    required = ["schema_version", "timestamp", "ui_state", "extraction", "task_state", "confidence"]
    for key in required:
        if key not in observation:
            raise ValueError(f"VisionObservation missing required field: {key}")
    ui_state = observation.get("ui_state", {})
    if "app" not in ui_state:
        raise ValueError("VisionObservation ui_state.app missing")
    if "panels_visible" not in ui_state:
        raise ValueError("VisionObservation ui_state.panels_visible missing")
    confidence = observation.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise ValueError("VisionObservation confidence must be a number")
    if not (0.0 <= float(confidence) <= 1.0):
        raise ValueError("VisionObservation confidence must be between 0.0 and 1.0")

    for feature in observation.get("extraction", {}).get("timeline", {}).get("features_visible", []):
        bbox = feature.get("screen_bbox", {})
        for key in ("x", "y", "width", "height"):
            if not isinstance(bbox.get(key), int):
                raise ValueError("screen_bbox fields must be integers")
    for alert in observation.get("extraction", {}).get("alerts", []):
        bbox = alert.get("screen_bbox")
        if bbox:
            for key in ("x", "y", "width", "height"):
                if not isinstance(bbox.get(key), int):
                    raise ValueError("alert screen_bbox fields must be integers")
    for entry in observation.get("extraction", {}).get("measurements", {}).get("entries", []):
        bbox = entry.get("screen_bbox")
        if bbox:
            for key in ("x", "y", "width", "height"):
                if not isinstance(bbox.get(key), int):
                    raise ValueError("measurement screen_bbox fields must be integers")
    for target in observation.get("extraction", {}).get("viewcube", {}).get("targets", []):
        bbox = target.get("screen_bbox")
        if bbox:
            for key in ("x", "y", "width", "height"):
                if not isinstance(bbox.get(key), int):
                    raise ValueError("viewcube target screen_bbox fields must be integers")


def _normalize_observation(partial, goal, image_paths):
    observation = _error_observation(goal, image_paths, "normalized")
    if not isinstance(partial, dict):
        return observation

    observation["notes"] = partial.get("notes", "")
    observation["schema_version"] = partial.get("schema_version", "1.0")
    observation["timestamp"] = partial.get("timestamp", datetime.utcnow().isoformat() + "Z")

    ui_state = partial.get("ui_state", {})
    observation["ui_state"].update(ui_state)
    if not observation["ui_state"].get("app"):
        observation["ui_state"]["app"] = "Autodesk Fusion"
    panels = observation["ui_state"].get("panels_visible", {})

    extraction = partial.get("extraction", {})
    observation["extraction"].update(
        {k: v for k, v in extraction.items() if k not in ("timeline", "measurements", "viewcube", "post_click")}
    )

    timeline = extraction.get("timeline", {}) if isinstance(extraction, dict) else {}
    features = timeline.get("features_visible", []) if isinstance(timeline, dict) else []
    normalized_features = []
    for feature in features[:8]:
        bbox = feature.get("screen_bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            bbox = {"x": int(bbox[0]), "y": int(bbox[1]), "width": int(bbox[2]), "height": int(bbox[3])}
        elif isinstance(bbox, dict):
            bbox = {
                "x": int(bbox.get("x", 0)),
                "y": int(bbox.get("y", 0)),
                "width": int(bbox.get("width", 0)),
                "height": int(bbox.get("height", 0)),
            }
        else:
            bbox = {"x": 0, "y": 0, "width": 0, "height": 0}
        normalized_features.append(
            {
                "name": feature.get("name", ""),
                "type_hint": feature.get("type_hint", "unknown"),
                "is_suppressed": bool(feature.get("is_suppressed", False)),
                "screen_bbox": bbox,
                "confidence": float(feature.get("confidence", 0.0)),
            }
        )

    observation["extraction"]["timeline"] = {
        "visible": timeline.get("visible", bool(normalized_features)),
        "highlighted_feature": timeline.get("highlighted_feature"),
        "features_visible": normalized_features,
    }

    if normalized_features:
        panels["timeline"] = True
    observation["ui_state"]["panels_visible"] = panels

    alerts = []
    if isinstance(extraction, dict) and "alerts" in extraction:
        alerts = extraction.get("alerts", [])
    if isinstance(timeline, dict) and "alerts" in timeline:
        alerts = timeline.get("alerts", []) or alerts
    if alerts:
        observation["extraction"]["alerts"] = alerts

    measurements = {}
    if isinstance(extraction, dict) and "measurements" in extraction:
        measurements = extraction.get("measurements", {})
    if measurements:
        entries = measurements.get("entries", [])
        normalized_entries = []
        for entry in entries:
            bbox = entry.get("screen_bbox")
            if isinstance(bbox, list) and len(bbox) == 4:
                bbox = {"x": int(bbox[0]), "y": int(bbox[1]), "width": int(bbox[2]), "height": int(bbox[3])}
            elif isinstance(bbox, dict):
                bbox = {
                    "x": int(bbox.get("x", 0)),
                    "y": int(bbox.get("y", 0)),
                    "width": int(bbox.get("width", 0)),
                    "height": int(bbox.get("height", 0)),
                }
            normalized_entries.append({**entry, "screen_bbox": bbox} if bbox else entry)
        measurements["entries"] = normalized_entries
        observation["extraction"]["measurements"] = measurements

    viewcube = {}
    if isinstance(extraction, dict) and "viewcube" in extraction:
        viewcube = extraction.get("viewcube", {})
    if viewcube:
        targets = viewcube.get("targets", [])
        normalized_targets = []
        for target in targets:
            bbox = target.get("screen_bbox")
            if isinstance(bbox, list) and len(bbox) == 4:
                bbox = {"x": int(bbox[0]), "y": int(bbox[1]), "width": int(bbox[2]), "height": int(bbox[3])}
            elif isinstance(bbox, dict):
                bbox = {
                    "x": int(bbox.get("x", 0)),
                    "y": int(bbox.get("y", 0)),
                    "width": int(bbox.get("width", 0)),
                    "height": int(bbox.get("height", 0)),
                }
            normalized_targets.append({**target, "screen_bbox": bbox} if bbox else target)
        viewcube["targets"] = normalized_targets
        observation["extraction"]["viewcube"] = viewcube

    post_click = []
    if isinstance(extraction, dict) and "post_click" in extraction:
        post_click = extraction.get("post_click", [])
    if post_click:
        observation["extraction"]["post_click"] = post_click

    if "confidence" in partial:
        observation["confidence"] = float(partial.get("confidence", 0.0))

    if "task_state" in partial and isinstance(partial["task_state"], dict):
        observation["task_state"].update(partial["task_state"])
    if isinstance(partial.get("proposed_next_steps"), list):
        observation["proposed_next_steps"] = partial["proposed_next_steps"]
    if isinstance(partial.get("recapture_plan"), list):
        observation["recapture_plan"] = partial["recapture_plan"]
    if "viewcube" not in observation["extraction"]:
        observation["extraction"]["viewcube"] = {"visible": False, "face": "Unknown", "targets": []}
    return observation


def _read_image_b64(path):
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _build_vision_prompt(focus=None):
    prompt = (
        "You are a vision extractor for Autodesk Fusion UI. "
        "Return JSON only, strictly matching VisionObservation schema v1.0. "
        "Include all required top-level fields: schema_version, timestamp, ui_state, "
        "extraction, task_state, proposed_next_steps, recapture_plan, confidence, notes. "
        "Focus primarily on the timeline image: identify up to 8 feature names, "
        "estimate their bounding boxes relative to the timeline image, and detect any error alerts. "
        "For timeline features, populate extraction.timeline.features_visible with name, "
        "type_hint, is_suppressed, screen_bbox {x,y,width,height} as integers, and confidence. "
        "Set ui_state.panels_visible.timeline true if the timeline is visible. "
        "If the browser panel is visible, set ui_state.panels_visible.browser true. "
        "If a viewcube image is provided, set extraction.viewcube.visible and extraction.viewcube.face "
        "(Front|Top|Right|Home|Unknown) and include extraction.viewcube.targets with label "
        "and screen_bbox {x,y,width,height} relative to the viewcube image. "
        "If measure panel images are provided, extract numeric measurement entries into "
        "extraction.measurements.entries with metric, value, units, label, screen_bbox {x,y,width,height}, and confidence. "
        "If the Results section shows Distance/Angle, always include them as entries. "
        "If post-click crop images are provided, include extraction.post_click entries with "
        "label, on_silhouette (true/false), highlight_visible (true/false), and confidence. "
        "If error markers are visible, add them to extraction.alerts with severity and text. "
        "If unsure, leave fields empty and lower confidence. No extra text."
    )
    if focus == "measure_panel":
        prompt += " Focus on the measure panel images; measurements are the top priority."
    if focus == "viewcube":
        prompt += " Focus on the viewcube image; viewcube face and targets are the top priority."
    return prompt


def _vision_request_payload(image_paths, goal, focus=None):
    images = []
    for path in image_paths:
        b64 = _read_image_b64(path)
        images.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

    return {
        "model": os.environ.get("FUSION_VISION_MODEL", "gpt-4o-mini"),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _build_vision_prompt(focus=focus)},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Goal: "
                            + goal
                            + (
                                ". Focus on measurements from the measure panel."
                                if focus == "measure_panel"
                                else (
                                    ". Focus on viewcube targets and face."
                                    if focus == "viewcube"
                                    else ". Extract only timeline-focused data for now (timeline features + alerts)."
                                )
                            )
                            + (" Post-click crops follow the measure panel images." if focus == "measure_panel" else "")
                            + " Return JSON-only VisionObservation."
                        ),
                    },
                    *images,
                ],
            },
        ],
    }


def _parse_retry_after(headers):
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def vision_client(
    image_paths,
    goal,
    max_attempts=3,
    initial_delay=0.0,
    raw_log_path=None,
    focus=None,
):
    api_key = os.environ.get("FUSION_VISION_API_KEY")
    endpoint = os.environ.get("FUSION_VISION_ENDPOINT", "https://api.openai.com/v1/chat/completions")
    if not api_key:
        raise RuntimeError("FUSION_VISION_API_KEY is not set")

    if initial_delay > 0:
        time.sleep(initial_delay)

    payload = _vision_request_payload(image_paths, goal, focus=focus)
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
            last_error = None
            break
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < max_attempts:
                retry_after = _parse_retry_after(exc.headers)
                sleep_for = retry_after if retry_after is not None else (2 ** (attempt - 1))
                time.sleep(sleep_for)
                continue
            raise RuntimeError(f"Vision request failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            raise RuntimeError(f"Vision request failed: {exc}") from exc
    if last_error is not None:
        raise RuntimeError("Vision request failed after retries")

    parsed = json.loads(body)
    content = parsed["choices"][0]["message"]["content"]
    if raw_log_path:
        try:
            with open(raw_log_path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except Exception:
            pass
    parsed_content = json.loads(content)
    observation = _normalize_observation(parsed_content, goal, image_paths)
    _basic_validate_observation(observation)
    observation["image_paths"] = image_paths
    return observation


def vision_call_or_stub(image_paths, goal, allow_stub=True):
    try:
        observation = vision_client(image_paths, goal)
        return observation
    except Exception as exc:
        if allow_stub:
            fallback = vision_stub(image_paths, goal)
            fallback["confidence"] = 0.0
            fallback["notes"] = f"Vision fallback: {exc}"
            return fallback
        raise


def _safe_observation_on_invalid(observation, error):
    observation["confidence"] = 0.0
    observation["notes"] = f"Invalid VisionObservation: {error}"
    return observation


def _error_observation(goal, image_paths, error):
    return {
        "schema_version": "1.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ui_state": {
            "app": "Autodesk Fusion",
            "document_name": None,
            "workspace": "Unknown",
            "active_tab": "Unknown",
            "active_command": None,
            "selection_summary": {"selection_type": "unknown", "count": 0},
            "panels_visible": {
                "browser": False,
                "timeline": False,
                "sketch_palette": False,
                "inspect_panel": False,
                "measure_dialog": False,
            },
            "view_mode": {"camera": "unknown", "visual_style": "unknown"},
        },
        "extraction": {
            "sketch_context": {
                "is_editing_sketch": False,
                "sketch_name": None,
                "dimensions_detected": [],
                "constraints_detected": [],
            },
            "measurements": {"measure_dialog_open": False, "entries": []},
            "timeline": {"visible": False, "highlighted_feature": None, "features_visible": []},
            "viewcube": {"visible": False, "face": "Unknown", "targets": []},
            "post_click": [],
            "alerts": [],
        },
        "task_state": {
            "goal": goal,
            "requirements": {
                "units": "mm",
                "must_preserve": [],
                "must_fit": [],
                "tolerances": {},
            },
            "known_targets": {},
            "progress": {
                "identified_back_plate_component": False,
                "located_mount_feature": False,
                "updated_hole_pattern": False,
                "updated_port_cutouts": False,
                "verification_passed": False,
            },
        },
        "proposed_next_steps": [],
        "recapture_plan": [],
        "confidence": 0.0,
        "notes": f"Vision error: {error}",
        "image_paths": image_paths,
    }


class Planner:
    def __init__(self):
        self.state = "BOOTSTRAP"
        self.pending_action = None
        self.stuck_count = 0
        self.last_progress = None
        self.vision_confirmed = False
        self.baseline_measured = False
        self.action_queue = []
        self.measurement_attempts = 0
        self.awaiting_measurement = False
        self.measure_variant = 0
        self.last_click_distance = None
        self.last_post_click_crops = []
        self.nav_done = False
        self.last_canvas_path = None
        self.last_scale_factor = 1.0

    def update_progress(self, progress):
        if self.last_progress is None:
            self.last_progress = progress.copy()
            return
        if progress != self.last_progress:
            self.stuck_count = 0
            self.last_progress = progress.copy()
        else:
            self.stuck_count += 1

    def decide_action(self, observation):
        if self.action_queue:
            return self.action_queue.pop(0)
        if self.pending_action:
            action = self.pending_action
            self.pending_action = None
            return action

        if observation.get("confidence", 0) < 0.65:
            return {"tool": "wait", "arguments": {"milliseconds": 250}, "intent": "wait"}

        if self.state == "BOOTSTRAP":
            self.state = "LOCATE"
            return {"tool": "key_press", "arguments": {"keys": ["escape"]}, "intent": "escape"}
        if self.state == "LOCATE":
            self.state = "MEASURE_BASELINE"
            return {"tool": "wait", "arguments": {"milliseconds": 300}, "intent": "navigate"}
        if self.state == "MEASURE_BASELINE":
            return {"tool": "wait", "arguments": {"milliseconds": 300}, "intent": "measure"}
        if self.state == "EDIT":
            self.state = "VERIFY"
            return {"tool": "wait", "arguments": {"milliseconds": 300}, "intent": "edit"}
        if self.state == "VERIFY":
            self.state = "DONE"
            return {"tool": "wait", "arguments": {"milliseconds": 300}, "intent": "verify"}
        return None


def click_bbox_center(client, bbox, calibration, region_name, scale_factor=1.0):
    region = _get_region(calibration, region_name)
    center_x, center_y = _center_of_bbox(bbox)
    abs_x = region["x"] + center_x * scale_factor
    abs_y = region["y"] + center_y * scale_factor
    return client.call_tool(
        "mouse_click",
        {"x": int(round(abs_x)), "y": int(round(abs_y))},
    )


def _click_canvas_relative(client, calibration, rel_x, rel_y, scale_factor=1.0):
    canvas = _get_region(calibration, "canvas")
    abs_x = canvas["x"] + canvas["width"] * rel_x
    abs_y = canvas["y"] + canvas["height"] * rel_y
    return client.call_tool(
        "mouse_click",
        {"x": int(round(abs_x * scale_factor)), "y": int(round(abs_y * scale_factor))},
    )


def _click_region_relative(client, calibration, region_name, rel_x, rel_y, scale_factor=1.0):
    region = _get_region(calibration, region_name)
    abs_x = region["x"] + region["width"] * rel_x
    abs_y = region["y"] + region["height"] * rel_y
    return client.call_tool(
        "mouse_click",
        {"x": int(round(abs_x * scale_factor)), "y": int(round(abs_y * scale_factor))},
    )


def _capture_click_crop(client, actions_log, x, y, label):
    crop = {
        "x": max(0, int(x - 120)),
        "y": max(0, int(y - 120)),
        "width": 240,
        "height": 240,
    }
    result = client.call_tool("capture_screen", {"region": crop})
    _log_action(
        actions_log,
        {"tool": "capture_screen", "region_name": "post_click_crop", "label": label, "result": result},
    )
    return result.get("image_path")


def _log_action(actions_log, entry):
    entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
    with open(actions_log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _update_scale_from_capture(screen_info, capture):
    display_w = screen_info.get("width")
    display_h = screen_info.get("height")
    image_w = capture.get("width")
    image_h = capture.get("height")
    if not all([display_w, display_h, image_w, image_h]):
        return 1.0, None
    ratio_w = image_w / float(display_w)
    ratio_h = image_h / float(display_h)
    ratio = (ratio_w + ratio_h) / 2.0
    if 1.8 <= ratio <= 2.2:
        return display_w / float(image_w), ratio
    return 1.0, ratio


def _capture_plan(observation, planner_state, calibration, force_measure=False):
    regions = ["timeline", "canvas"]
    if "browser" in calibration:
        regions.append("browser")
    if "viewcube" in calibration:
        regions.append("viewcube")

    measure_open = False
    if observation:
        measure_open = observation.get("extraction", {}).get("measurements", {}).get(
            "measure_dialog_open",
            False,
        )
    if force_measure or measure_open or planner_state in ("VERIFY", "MEASURE_BASELINE"):
        if "measure_panel" in calibration:
            regions.append("measure_panel")

    sketch_edit = False
    if observation:
        sketch_edit = observation.get("extraction", {}).get("sketch_context", {}).get(
            "is_editing_sketch",
            False,
        )
    if sketch_edit or planner_state == "EDIT":
        if "sketch_palette" in calibration:
            regions.append("sketch_palette")
        if "sketch_dimension" in calibration:
            regions.append("sketch_dimension")
    return regions


def _bootstrap(client, run_dir, calibration, vision_delay=0.0):
    actions_log = os.path.join(run_dir, "actions.jsonl")
    client.request("initialize", {})
    _click_canvas_relative(client, calibration, 0.5, 0.5)
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "canvas", "target": "focus"})
    time.sleep(0.1)
    client.call_tool("key_press", {"keys": ["escape"]})
    client.call_tool("key_press", {"keys": ["escape"]})
    _log_action(actions_log, {"tool": "key_press", "keys": ["escape", "escape"]})

    captures = []
    for region_name in ("timeline", "canvas", "browser"):
        result = client.call_tool("capture_screen", {"region_name": region_name})
        captures.append(result)
        _log_action(actions_log, {"tool": "capture_screen", "region_name": region_name, "result": result})

    image_paths = [item.get("image_path") for item in captures if item.get("image_path")]
    try:
        raw_path = os.path.join(run_dir, "vision_raw.txt")
        observation = vision_client(
            image_paths,
            "Modify back plate to fit Raspberry Pi 3B",
            initial_delay=vision_delay,
            raw_log_path=raw_path,
        )
        try:
            _basic_validate_observation(observation)
        except Exception as exc:
            observation = _safe_observation_on_invalid(observation, exc)
    except Exception as exc:
        observation = _error_observation("Modify back plate to fit Raspberry Pi 3B", image_paths, exc)
    obs_path = os.path.join(run_dir, "observation.json")
    with open(obs_path, "w", encoding="utf-8") as fh:
        json.dump(observation, fh, indent=2)

    ui_state = observation.get("ui_state", {})
    panels = ui_state.get("panels_visible", {})
    is_fusion = ui_state.get("app") == "Autodesk Fusion"
    panels_ok = panels.get("browser") is True and panels.get("timeline") is True
    if not (is_fusion and panels_ok):
        print(
            "Bootstrap failed: Ensure Autodesk Fusion is frontmost and the Browser + Timeline panels are visible."
        )
        return False, observation
    return True, observation


def _measure_baseline(client, actions_log, calibration, scale_factor, canvas_path, variant=0):
    _click_canvas_relative(client, calibration, 0.5, 0.5, scale_factor=scale_factor)
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "canvas", "target": "focus"})
    time.sleep(0.1)

    client.call_tool("key_press", {"keys": ["escape"]})
    client.call_tool("key_press", {"keys": ["escape"]})
    _log_action(actions_log, {"tool": "key_press", "keys": ["escape", "escape"]})

    client.call_tool("key_press", {"keys": ["i"]})
    _log_action(actions_log, {"tool": "key_press", "keys": ["i"]})
    time.sleep(0.2)

    # Quick local check: ensure the measure panel is actually open.
    panel_check = client.call_tool("capture_screen", {"region_name": "measure_panel"})
    _log_action(actions_log, {"tool": "capture_screen", "region_name": "measure_panel_check", "result": panel_check})
    if not _looks_like_measure_panel(panel_check.get("image_path")):
        client.call_tool("key_press", {"keys": ["i"]})
        _log_action(actions_log, {"tool": "key_press", "keys": ["i"], "target": "retry_open_measure"})
        time.sleep(0.2)
        panel_check = client.call_tool("capture_screen", {"region_name": "measure_panel"})
        _log_action(
            actions_log,
            {"tool": "capture_screen", "region_name": "measure_panel_check", "result": panel_check},
        )

    # Best-effort: enable snap points + vertex filter for point-to-point measurement.
    _click_region_relative(client, calibration, "measure_panel", 0.14, 0.30, scale_factor=scale_factor)
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "measure_panel", "target": "selection_filter"})
    time.sleep(0.1)
    _click_region_relative(client, calibration, "measure_panel", 0.42, 0.30, scale_factor=scale_factor)
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "measure_panel", "target": "vertex_filter"})
    time.sleep(0.1)
    _click_region_relative(client, calibration, "measure_panel", 0.12, 0.22, scale_factor=scale_factor)
    _log_action(actions_log, {"tool": "mouse_click", "region_name": "measure_panel", "target": "show_snap_points"})
    time.sleep(0.35)

    row_target = _find_dark_row_targets(canvas_path) if canvas_path else None
    bbox = _compute_silhouette_bbox(canvas_path) if canvas_path else None
    margin = 20 if variant == 0 else 30
    y_ratio = 0.5 if variant == 0 else 0.4
    bbox_reason = "ok"
    if bbox:
        if (bbox["right"] - bbox["left"]) > bbox["width"] * 0.95:
            bbox = None
            bbox_reason = "full_width"
        elif (bbox["bottom"] - bbox["top"]) > bbox["height"] * 0.95:
            bbox = None
            bbox_reason = "full_height"
    else:
        bbox_reason = "none"

    canvas_w = None
    canvas_h = None
    if canvas_path and not bbox:
        try:
            from PIL import Image

            with Image.open(canvas_path) as img:
                canvas_w, canvas_h = img.size
        except Exception:
            canvas_w = None
            canvas_h = None

    if row_target:
        row_margin = 5
        left_x = max(row_target["left"] + row_margin, 0)
        right_x = max(row_target["right"] - row_margin, left_x + 1)
        click_y = row_target["y"]
        bbox_reason = "row_scan_dark_pixels"
    elif bbox:
        left_x = max(bbox["left"] + margin, 0)
        right_x = min(bbox["right"] - margin, bbox["width"])
        click_y = int(bbox["top"] + (bbox["bottom"] - bbox["top"]) * y_ratio)
    else:
        if canvas_w and canvas_h:
            left_x = int(canvas_w * 0.2)
            right_x = int(canvas_w * 0.8)
            click_y = int(canvas_h * (0.6 if variant == 0 else 0.45))
        else:
            left_x = 200
            right_x = 800
            click_y = 420

    canvas = _get_region(calibration, "canvas")
    panel = _get_region(calibration, "measure_panel")
    abs_left_x = canvas["x"] + left_x * scale_factor
    abs_right_x = canvas["x"] + right_x * scale_factor
    abs_y = canvas["y"] + click_y * scale_factor
    panel_avoid = False
    if panel and _point_in_region(abs_left_x, abs_y, panel):
        abs_y = _shift_y_below_panel(abs_y, panel, canvas)
        panel_avoid = True
    if panel and _point_in_region(abs_right_x, abs_y, panel):
        abs_y = _shift_y_below_panel(abs_y, panel, canvas)
        panel_avoid = True
    _log_action(
        actions_log,
        {
            "tool": "silhouette_targets",
            "left": {"x": left_x, "y": click_y},
            "right": {"x": right_x, "y": click_y},
            "scale_factor": scale_factor,
            "panel_avoid": panel_avoid,
            "bbox_reason": bbox_reason,
        },
    )

    client.call_tool("mouse_click", {"x": int(round(abs_left_x)), "y": int(round(abs_y))})
    _log_action(
        actions_log,
        {
            "tool": "mouse_click",
            "region_name": "canvas",
            "target": "left_silhouette",
            "applied": {"x": int(round(abs_left_x)), "y": int(round(abs_y))},
            "scale_factor": scale_factor,
        },
    )
    left_crop = None
    if variant > 0:
        left_crop = _capture_click_crop(client, actions_log, abs_left_x, abs_y, "left")
    time.sleep(0.15)
    client.call_tool("mouse_click", {"x": int(round(abs_right_x)), "y": int(round(abs_y))})
    _log_action(
        actions_log,
        {
            "tool": "mouse_click",
            "region_name": "canvas",
            "target": "right_silhouette",
            "applied": {"x": int(round(abs_right_x)), "y": int(round(abs_y))},
            "scale_factor": scale_factor,
        },
    )
    right_crop = None
    if variant > 0:
        right_crop = _capture_click_crop(client, actions_log, abs_right_x, abs_y, "right")

    post = client.call_tool("capture_screen", {"region_name": "measure_panel"})
    _log_action(actions_log, {"tool": "capture_screen", "region_name": "measure_panel", "result": post})

    click_distance = abs(right_x - left_x)
    return [post.get("image_path")], [left_crop, right_crop], click_distance

    post = client.call_tool("capture_screen", {"region_name": "measure_panel"})
    _log_action(actions_log, {"tool": "capture_screen", "region_name": "measure_panel", "result": post})

    return [pre.get("image_path"), post.get("image_path")]


def _pick_viewcube_target(observation, label):
    targets = observation.get("extraction", {}).get("viewcube", {}).get("targets", [])
    desired = label.lower()
    for target in targets:
        target_label = target.get("label", "").lower()
        if target_label in ("x", "y", "z"):
            continue
        if target_label == desired:
            return target.get("screen_bbox")
    return None


def run_simple(client, run_dir):
    actions_log = os.path.join(run_dir, "actions.jsonl")
    calibration = _load_calibration()
    ok, observation = _bootstrap(client, run_dir, calibration)
    if ok:
        print(json.dumps(observation, indent=2))


def run_loop(client, run_dir, max_steps, force_measure=False, vision_delay=0.0, start_measure=False):
    calibration = _load_calibration()
    actions_log = os.path.join(run_dir, "actions.jsonl")
    obs_dir = os.path.join(run_dir, "observations")
    _ensure_dir(obs_dir)
    debug_post_click = False

    planner = Planner()
    ok, bootstrap_obs = _bootstrap(client, run_dir, calibration, vision_delay=vision_delay)
    planner.vision_confirmed = ok
    last_observation = bootstrap_obs
    if not ok:
        return
    if start_measure:
        planner.state = "MEASURE_BASELINE"

    for step in range(max_steps):
        skip_vision = False
        try:
            screen_info = client.call_tool("get_screen_info", {})
            _log_action(actions_log, {"tool": "get_screen_info", "result": screen_info})
        except Exception:
            screen_info = {}

        capture_map = {}
        scale_factor = planner.last_scale_factor or 1.0
        observation = last_observation
        if planner.state == "MEASURE_BASELINE" and not planner.baseline_measured and not planner.awaiting_measurement:
            if not planner.nav_done:
                # NAV phase: fast, no vision. Capture canvas pre/post, run nav batch.
                if "canvas" in calibration:
                    pre_canvas = client.call_tool("capture_screen", {"region_name": "canvas"})
                    _log_action(actions_log, {"tool": "capture_screen", "region_name": "canvas", "result": pre_canvas})
                    capture_map["canvas"] = pre_canvas

                _click_canvas_relative(client, calibration, 0.5, 0.5, scale_factor=scale_factor)
                _log_action(actions_log, {"tool": "mouse_click", "region_name": "canvas", "target": "focus"})
                client.call_tool("key_press", {"keys": ["f6"]})
                _log_action(actions_log, {"tool": "key_press", "keys": ["f6"]})
                client.call_tool("wait", {"milliseconds": 350})
                _log_action(actions_log, {"tool": "wait", "arguments": {"milliseconds": 350}})
                client.call_tool("key_press", {"keys": ["command", "6"]})
                _log_action(actions_log, {"tool": "key_press", "keys": ["command", "6"]})
                client.call_tool("wait", {"milliseconds": 350})
                _log_action(actions_log, {"tool": "wait", "arguments": {"milliseconds": 350}})
                client.call_tool("mouse_scroll", {"delta_y": -120, "steps": 6})
                _log_action(actions_log, {"tool": "mouse_scroll", "arguments": {"delta_y": -120, "steps": 6}})
                nav_canvas = client.call_tool("capture_screen", {"region_name": "canvas"})
                _log_action(actions_log, {"tool": "capture_screen", "region_name": "canvas", "result": nav_canvas})
                capture_map["canvas"] = nav_canvas
                if screen_info:
                    scale_factor, ratio = _update_scale_from_capture(screen_info, nav_canvas)
                    planner.last_scale_factor = scale_factor
                    _log_action(
                        actions_log,
                        {
                            "tool": "scale_check",
                            "display": {"width": screen_info.get("width"), "height": screen_info.get("height")},
                            "capture": {"width": nav_canvas.get("width"), "height": nav_canvas.get("height")},
                            "ratio": ratio,
                            "scale_factor": scale_factor,
                        },
                    )
                planner.last_canvas_path = nav_canvas.get("image_path")
                planner.nav_done = True
                continue
            skip_vision = True

        if planner.awaiting_measurement:
            capture_regions = ["measure_panel"]
            focus = "measure_panel"
        else:
            capture_regions = _capture_plan(last_observation, planner.state, calibration, force_measure=force_measure)
            focus = None
        captures = []
        if not skip_vision:
            for region_name in capture_regions:
                result = client.call_tool("capture_screen", {"region_name": region_name})
                _log_action(actions_log, {"tool": "capture_screen", "region_name": region_name, "result": result})
                captures.append(result)
                capture_map[region_name] = result

        if captures and screen_info:
            scale_factor, ratio = _update_scale_from_capture(screen_info, captures[0])
        else:
            scale_factor = planner.last_scale_factor or 1.0

        image_paths = [item.get("image_path") for item in captures if item.get("image_path")]
        if debug_post_click and planner.awaiting_measurement and planner.last_post_click_crops:
            image_paths.extend(planner.last_post_click_crops)

        if captures and screen_info:
            _log_action(
                actions_log,
                {
                    "tool": "scale_check",
                    "display": {"width": screen_info.get("width"), "height": screen_info.get("height")},
                    "capture": {"width": captures[0].get("width"), "height": captures[0].get("height")},
                    "ratio": ratio,
                    "scale_factor": scale_factor,
                },
            )

        if skip_vision:
            action = {"intent": "measure_baseline"}
        else:
            try:
                raw_path = os.path.join(obs_dir, f"vision_raw-{step+1:03d}.txt")
                observation = vision_client(
                    image_paths,
                    "Modify back plate to fit Raspberry Pi 3B",
                    initial_delay=vision_delay,
                    raw_log_path=raw_path,
                    focus=focus,
                )
                try:
                    _basic_validate_observation(observation)
                except Exception as exc:
                    observation = _safe_observation_on_invalid(observation, exc)
            except Exception as exc:
                observation = _error_observation("Modify back plate to fit Raspberry Pi 3B", image_paths, exc)

            viewcube_path = capture_map.get("viewcube", {}).get("image_path")
            if viewcube_path:
                try:
                    viewcube_raw = os.path.join(obs_dir, f"vision_viewcube-{step+1:03d}.txt")
                    viewcube_obs = vision_client(
                        [viewcube_path],
                        "Extract viewcube only",
                        initial_delay=vision_delay,
                        raw_log_path=viewcube_raw,
                        focus="viewcube",
                    )
                    observation["extraction"]["viewcube"] = viewcube_obs.get("extraction", {}).get(
                        "viewcube",
                        observation.get("extraction", {}).get("viewcube", {"visible": False, "face": "Unknown", "targets": []}),
                    )
                except Exception:
                    pass

        entries = observation.get("extraction", {}).get("measurements", {}).get("entries", [])
        if entries:
            best = max(entries, key=lambda e: e.get("confidence", 0.0))
            observation["notes"] = (
                f"Measurement: {best.get('value')} {best.get('units')} "
                f"({best.get('metric')}, confidence {best.get('confidence')})"
            )

        if not skip_vision:
            if captures and screen_info:
                scale_factor, ratio = _update_scale_from_capture(screen_info, captures[0])
                _log_action(
                    actions_log,
                    {
                        "tool": "scale_check",
                        "display": {"width": screen_info.get("width"), "height": screen_info.get("height")},
                        "capture": {"width": captures[0].get("width"), "height": captures[0].get("height")},
                        "ratio": ratio,
                        "scale_factor": scale_factor,
                    },
                )
            else:
                scale_factor = planner.last_scale_factor or 1.0
            obs_path = os.path.join(obs_dir, f"observation-{step+1:03d}.json")
            with open(obs_path, "w", encoding="utf-8") as fh:
                json.dump(observation, fh, indent=2)

        last_observation = observation
        if not skip_vision:
            planner.update_progress(observation["task_state"]["progress"])
        if planner.stuck_count >= 8:
            planner.state = "RECOVER"

        if not skip_vision:
            if planner.state == "RECOVER":
                action = {"tool": "wait", "arguments": {"milliseconds": 500}, "intent": "recover"}
            else:
                action = planner.decide_action(observation)

        if action is None:
            break

        if planner.awaiting_measurement:
            entries = observation.get("extraction", {}).get("measurements", {}).get("entries", [])
            best = max(entries, key=lambda e: e.get("confidence", 0.0), default=None)
            if (
                best
                and best.get("confidence", 0.0) >= 0.7
                and float(best.get("value", 0.0)) >= 10.0
                and (planner.last_click_distance is None or planner.last_click_distance >= 50)
            ):
                planner.baseline_measured = True
                planner.awaiting_measurement = False
                planner.state = "VERIFY"
            else:
                planner.awaiting_measurement = False
                planner.measurement_attempts += 1
                if planner.measurement_attempts <= 1:
                    planner.measure_variant = 1
                    planner.action_queue = [
                        {"intent": "fit_view"},
                        {"intent": "zoom_in", "steps": 2},
                        {"intent": "measure_baseline"},
                    ]
                else:
                    _log_action(
                        actions_log,
                        {"tool": "request_better_view", "reason": "Measurement failed or confidence < 0.7"},
                    )
                    time.sleep(0.5)
                    continue

        if not planner.vision_confirmed:
            allowed = {"navigate", "measure", "request_better_view", "wait", "escape"}
            if action.get("intent") not in allowed:
                action = {"tool": "wait", "arguments": {"milliseconds": 300}, "intent": "wait"}

        if action.get("intent") == "fit_view":
            client.call_tool("key_press", {"keys": ["f6"]})
            _log_action(actions_log, {"tool": "key_press", "keys": ["f6"]})
            client.call_tool("wait", {"milliseconds": 350})
            _log_action(actions_log, {"tool": "wait", "arguments": {"milliseconds": 350}})
            for region_name in ("canvas", "viewcube"):
                if region_name in calibration:
                    result = client.call_tool("capture_screen", {"region_name": region_name})
                    _log_action(actions_log, {"tool": "capture_screen", "region_name": region_name, "result": result})
            continue

        if action.get("intent") in ("set_view_front", "set_view_top", "set_view_right"):
            target = action["intent"].split("_")[-1]
            shortcut = {"front": "1", "top": "3", "right": "6"}.get(target)
            if shortcut:
                client.call_tool("key_press", {"keys": ["command", shortcut]})
                _log_action(actions_log, {"tool": "key_press", "keys": ["command", shortcut]})
            client.call_tool("wait", {"milliseconds": 350})
            _log_action(actions_log, {"tool": "wait", "arguments": {"milliseconds": 350}})
            viewcube_cap = client.call_tool("capture_screen", {"region_name": "viewcube"})
            _log_action(actions_log, {"tool": "capture_screen", "region_name": "viewcube", "result": viewcube_cap})
            try:
                verify_obs = vision_client(
                    [viewcube_cap.get("image_path")],
                    "Verify viewcube face",
                    initial_delay=vision_delay,
                    focus="viewcube",
                )
                face = (
                    verify_obs.get("extraction", {})
                    .get("viewcube", {})
                    .get("face", "Unknown")
                )
                if face.lower() != target.lower():
                    client.call_tool("key_press", {"keys": ["command", shortcut]})
                    _log_action(actions_log, {"tool": "key_press", "keys": ["command", shortcut], "target": "retry"})
                    client.call_tool("wait", {"milliseconds": 350})
                    _log_action(actions_log, {"tool": "wait", "arguments": {"milliseconds": 350}})
            except Exception:
                pass
            continue

        if action.get("intent") in ("zoom_in", "zoom_out"):
            steps = int(action.get("steps", 3))
            delta = -120 if action.get("intent") == "zoom_in" else 120
            client.call_tool("mouse_scroll", {"delta_y": delta, "steps": steps})
            _log_action(actions_log, {"tool": "mouse_scroll", "arguments": {"delta_y": delta, "steps": steps}})
            result = client.call_tool("capture_screen", {"region_name": "canvas"})
            _log_action(actions_log, {"tool": "capture_screen", "region_name": "canvas", "result": result})
            continue

        if action.get("intent") == "measure_baseline":
            canvas_path = capture_map.get("canvas", {}).get("image_path") or planner.last_canvas_path
            measure_paths, crop_paths, click_distance = _measure_baseline(
                client,
                actions_log,
                calibration,
                scale_factor or planner.last_scale_factor or 1.0,
                canvas_path,
                variant=planner.measure_variant,
            )
            planner.awaiting_measurement = True
            planner.last_click_distance = click_distance
            planner.last_post_click_crops = [p for p in crop_paths if p]
            # Run a focused measurement pass immediately on the post-measure capture.
            measure_paths = [p for p in measure_paths if p]
            if measure_paths:
                try:
                    raw_path = os.path.join(obs_dir, f"vision_raw-measure-{step+1:03d}.txt")
                    observation = vision_client(
                        measure_paths[-1:] + (planner.last_post_click_crops if debug_post_click else []),
                        "Extract baseline measurement",
                        initial_delay=vision_delay,
                        raw_log_path=raw_path,
                        focus="measure_panel",
                    )
                    try:
                        _basic_validate_observation(observation)
                    except Exception as exc:
                        observation = _safe_observation_on_invalid(observation, exc)
                    obs_path = os.path.join(obs_dir, f"observation-{step+1:03d}-measure.json")
                    with open(obs_path, "w", encoding="utf-8") as fh:
                        json.dump(observation, fh, indent=2)
                except Exception:
                    pass
            continue

        if action["intent"] == "edit":
            snapshot = client.call_tool("save_snapshot", {"label": "pre-edit"})
            _log_action(actions_log, {"tool": "save_snapshot", "result": snapshot})
            planner.pending_action = action
            continue

        result = client.call_tool(action["tool"], action.get("arguments", {}))
        _log_action(actions_log, {"tool": action["tool"], "arguments": action.get("arguments", {}), "result": result})

        time.sleep(0.05)


def main():
    _load_env()
    parser = argparse.ArgumentParser(description="Minimal MCP agent runner for Fusion.")
    parser.add_argument("--loop", action="store_true", help="Run the planner loop.")
    parser.add_argument("--max-steps", type=int, default=5, help="Max steps for loop mode.")
    parser.add_argument(
        "--force-measure",
        action="store_true",
        help="Always capture the measure_panel region each iteration.",
    )
    parser.add_argument(
        "--vision-delay-ms",
        type=int,
        default=0,
        help="Delay before each vision request (milliseconds).",
    )
    parser.add_argument(
        "--start-measure",
        action="store_true",
        help="Start loop directly in MEASURE_BASELINE state.",
    )
    parser.add_argument(
        "--connect",
        type=str,
        default=None,
        help="Connect to an already running MCP server at host:port.",
    )
    args = parser.parse_args()

    run_dir = os.path.join(LOG_ROOT, f"agent-run-{_now_stamp()}")
    _ensure_dir(run_dir)

    client = None
    if args.connect:
        if ":" not in args.connect:
            raise SystemExit("--connect must be in host:port format")
        host, port = args.connect.split(":", 1)
        client = MCPClient(connect_addr=(host, int(port)))
    else:
        server_cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "mcp_server.py")]
        client = MCPClient(server_cmd)
    try:
        if args.loop:
            run_loop(
                client,
                run_dir,
                args.max_steps,
                force_measure=args.force_measure,
                vision_delay=args.vision_delay_ms / 1000.0,
                start_measure=args.start_measure,
            )
        else:
            run_simple(client, run_dir)
    finally:
        client.close()


if __name__ == "__main__":
    main()
