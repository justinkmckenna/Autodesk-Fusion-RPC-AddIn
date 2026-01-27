#!/usr/bin/env python3
import argparse
import json
import socket
import sys


def _send_request(host, port, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(data)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks).decode("utf-8")
    return json.loads(raw) if raw else {"ok": False, "error": "Empty response"}


def main():
    parser = argparse.ArgumentParser(description="Fusion RPC client.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("cmd", nargs="?", default=None)
    parser.add_argument("--body", type=str, default=None)
    parser.add_argument("--payload", type=str, default=None)
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--code", type=str, default=None)
    parser.add_argument("--code-file", type=str, default=None)
    parser.add_argument("--code-stdin", action="store_true", default=False)
    parser.add_argument("--inputs", type=str, default=None)
    parser.add_argument("--result-var", type=str, default=None)
    parser.add_argument("--no-stdout", action="store_true", default=False)
    parser.add_argument("--label", type=str, default=None)
    args = parser.parse_args()

    if sum(bool(x) for x in (args.code, args.code_file, args.code_stdin)) > 1:
        raise SystemExit("Use only one of --code, --code-file, or --code-stdin.")

    cmd = args.cmd
    if not cmd:
        if args.code or args.code_file or args.code_stdin:
            cmd = "run_python"
        else:
            raise SystemExit("cmd is required unless --code/--code-file is provided.")

    payload = {"cmd": cmd}
    if args.body:
        payload["body_name"] = args.body
    if args.payload:
        payload.update(json.loads(args.payload))
    if args.code_file:
        with open(args.code_file, "r", encoding="utf-8") as fh:
            payload["code"] = fh.read()
    elif args.code:
        payload["code"] = args.code
    elif args.code_stdin:
        payload["code"] = sys.stdin.read()
    if args.inputs:
        payload["inputs"] = json.loads(args.inputs)
    if args.result_var:
        payload["result_var"] = args.result_var
    if args.no_stdout:
        payload["capture_stdout"] = False
    if args.label:
        payload["label"] = args.label
    for item in args.param:
        if "=" not in item:
            raise SystemExit(f"--param must be key=value, got: {item}")
        key, value = item.split("=", 1)
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
        payload[key] = value

    response = _send_request("127.0.0.1", args.port, payload, args.timeout)
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
