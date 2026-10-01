from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROTOCOL_VERSION = "2025-06-18"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8642"
TIMEOUT_SECONDS = float(os.getenv("HERMES_GATEWAY_TIMEOUT", "10"))

TOOLS = [
    {
        "name": "hermes_start_task",
        "description": "Start a natural-language task in Hermes asynchronously and return its stable run ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "The objective for Hermes to execute.", "minLength": 1}},
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "hermes_get_task",
        "description": "Retrieve the current status and, when complete, the result of a Hermes task by run ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "description": "The Hermes run ID returned by hermes_start_task.", "minLength": 1}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "hermes_steer_task",
        "description": "Send additional instructions to an active Hermes run without starting a replacement run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "The active Hermes run ID to steer.", "minLength": 1},
                "instruction": {"type": "string", "description": "Additional guidance for the active Hermes run.", "minLength": 1},
            },
            "required": ["run_id", "instruction"],
            "additionalProperties": False,
        },
    },
]


class GatewayError(Exception):
    pass


class UnknownRunError(GatewayError):
    pass


class InvalidRunStateError(GatewayError):
    pass


def _gateway_url() -> str:
    return os.getenv("HERMES_GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    api_key = os.getenv("HERMES_GATEWAY_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(f"{_gateway_url()}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        if exc.code == 404:
            raise UnknownRunError("unknown Hermes run ID") from exc
        if exc.code in {400, 409, 422} and method == "POST" and path.endswith("/steer"):
            raise InvalidRunStateError("invalid run state: Hermes run is not steerable") from exc
        raise GatewayError(f"Hermes Gateway HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GatewayError(f"Hermes Gateway unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GatewayError("Hermes Gateway returned invalid JSON") from exc


def _normalized_status(status: Any) -> str:
    value = str(status or "unknown").strip().lower().replace(" ", "_")
    if value in {"queued", "pending", "created"}:
        return "queued"
    if value in {"running", "started", "in_progress", "in-progress", "active"}:
        return "running"
    if value in {"completed", "complete", "succeeded", "success", "done"}:
        return "completed"
    if value in {"failed", "failure", "error"}:
        return "failed"
    if value in {"stopped", "stopping", "stop", "cancelled", "canceled", "interrupted"}:
        return "stopped"
    if value in {
        "waiting",
        "waiting_for_approval",
        "waiting_for_input",
        "waiting_for_intervention",
        "intervention_required",
        "approval_required",
        "paused",
    }:
        return "waiting"
    return value


def _failure_summary(run: dict[str, Any]) -> Any:
    for key in ("error_summary", "failure", "error", "reason", "message"):
        value = run.get(key)
        if value is not None:
            if isinstance(value, dict):
                return value.get("message") or value.get("detail") or value
            return value
    return None


def _run_response(run: dict[str, Any]) -> dict[str, Any]:
    run_id = run.get("id", run.get("run_id"))
    if not isinstance(run_id, str) or not run_id:
        raise GatewayError("Hermes Gateway response did not include a run ID")
    original = run.get("status", run.get("state"))
    result = {"run_id": run_id, "status": _normalized_status(original), "hermes_status": original}

    timestamps = run.get("timestamps")
    if isinstance(timestamps, dict):
        result["timestamps"] = timestamps
    for key, value in run.items():
        if key.endswith("_at") and value is not None:
            result[key] = value

    output = run.get("output", run.get("result"))
    if output is not None:
        result["result"] = output
    if result["status"] == "failed":
        summary = _failure_summary(run)
        if summary is not None:
            result["error_summary"] = summary
    return result


def _error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _call_tool(name: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return _error("arguments must be an object")
    if name == "hermes_start_task":
        prompt = arguments.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return _error("prompt must be a non-empty string")
        try:
            response = _request("POST", "/v1/runs", {"input": prompt})
            return {"content": [{"type": "text", "text": json.dumps(_run_response(response), separators=(",", ":"))}]}
        except GatewayError as exc:
            return _error(str(exc))
    if name == "hermes_get_task":
        run_id = arguments.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            return _error("run_id must be a non-empty string")
        try:
            response = _request("GET", f"/v1/runs/{quote(run_id, safe='')}")
            return {"content": [{"type": "text", "text": json.dumps(_run_response(response), separators=(",", ":"))}]}
        except GatewayError as exc:
            return _error(str(exc))
    if name == "hermes_steer_task":
        run_id = arguments.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            return _error("run_id must be a non-empty string")
        instruction = arguments.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            return _error("instruction must be a non-empty string")
        try:
            _request("POST", f"/v1/runs/{quote(run_id, safe='')}/steer", {"text": instruction})
            return {"content": [{"type": "text", "text": json.dumps({
                "run_id": run_id,
                "status": "accepted",
                "message": f"steering instruction accepted for Hermes run {run_id}",
            }, separators=(",", ":"))}]}
        except GatewayError as exc:
            return _error(str(exc))
    return _error(f"unknown tool: {name}")


def _handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "hermes-gateway-mcp", "version": "0.1.0"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        return {"jsonrpc": "2.0", "id": request_id, "result": _call_tool(params.get("name"), params.get("arguments", {}))}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = _handle(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except (json.JSONDecodeError, TypeError) as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
