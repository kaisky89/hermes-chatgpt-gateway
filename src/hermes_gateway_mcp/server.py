from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "2025-06-18"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8642"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 120.0

logger = logging.getLogger("hermes_gateway_mcp")

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
    {
        "name": "hermes_stop_task",
        "description": "Request cancellation of one Hermes run and return the downstream cancellation result for that run.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "description": "The Hermes run ID to stop.", "minLength": 1}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
]


@dataclass(frozen=True)
class Config:
    gateway_url: str
    timeout: float
    api_key: str | None


class AdapterError(Exception):
    category = "internal adapter failure"


class ConfigurationError(AdapterError):
    category = "invalid configuration"


class InvalidInputError(AdapterError):
    category = "invalid input"


class GatewayAuthError(AdapterError):
    category = "Gateway authentication failure"


class GatewayConnectivityError(AdapterError):
    category = "Gateway connectivity/timeout failure"


class MalformedResponseError(AdapterError):
    category = "malformed/unexpected response"


class InternalAdapterError(AdapterError):
    category = "internal adapter failure"


class HermesHTTPError(AdapterError):
    """A structured Hermes HTTP error, forwarded without domain reclassification."""

    category = "Hermes Gateway error"

    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body

    def __str__(self) -> str:
        if isinstance(self.body, dict):
            payload = {"status": self.status, **self.body}
        else:
            payload = {"status": self.status, "body": self.body}
        return json.dumps(payload, separators=(",", ":"))


def _config() -> Config:
    raw_url = os.getenv("HERMES_GATEWAY_URL", DEFAULT_GATEWAY_URL).strip()
    parsed = urlparse(raw_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ConfigurationError("HERMES_GATEWAY_URL must be an absolute HTTP(S) URL without credentials, query, or fragment")
    try:
        timeout = float(os.getenv("HERMES_GATEWAY_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError as exc:
        raise ConfigurationError("HERMES_GATEWAY_TIMEOUT must be a number") from exc
    if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ConfigurationError(f"HERMES_GATEWAY_TIMEOUT must be greater than 0 and at most {MAX_TIMEOUT_SECONDS:g} seconds")
    return Config(raw_url.rstrip("/"), timeout, os.getenv("HERMES_GATEWAY_API_KEY") or None)


def _log(event: str, request_id: Any = None, run_id: str | None = None, **fields: Any) -> None:
    record: dict[str, Any] = {"event": event, "request_id": str(request_id) if request_id is not None else None}
    if run_id is not None:
        record["run_id"] = run_id
    record.update(fields)
    logger.info(json.dumps(record, separators=(",", ":"), sort_keys=True))


def _request(method: str, path: str, payload: dict[str, Any] | None = None, *, request_id: Any = None) -> dict[str, Any]:
    try:
        config = _config()
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        request = Request(f"{config.gateway_url}{path}", data=data, headers=headers, method=method)
        with urlopen(request, timeout=config.timeout) as response:
            raw = response.read()
    except ConfigurationError:
        raise
    except HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MalformedResponseError("Gateway returned a non-JSON error response") from error
        if exc.code in {401, 403}:
            raise GatewayAuthError("Gateway authentication failed") from exc
        raise HermesHTTPError(exc.code, body) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GatewayConnectivityError("Gateway is unreachable or timed out") from exc

    if not raw:
        raise MalformedResponseError("Gateway response body was empty")
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedResponseError("Gateway returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise MalformedResponseError("Gateway response must be a JSON object")
    return decoded


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
    if value in {"stopping", "stop"}:
        return "stopping"
    if value in {"stopped", "cancelled", "canceled", "interrupted"}:
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
        raise InternalAdapterError("Gateway response did not include a run ID")
    original = run.get("status", run.get("state"))
    result: dict[str, Any] = {"run_id": run_id, "status": _normalized_status(original), "hermes_status": original}
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


def _error(error: AdapterError | str) -> dict[str, Any]:
    if isinstance(error, HermesHTTPError):
        message = str(error)
    elif isinstance(error, AdapterError):
        message = f"{error.category}: {error}"
    else:
        message = error
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _validate_text(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{key} must be a non-empty string")
    return value


def _call_tool(name: str, arguments: Any, request_id: Any = None) -> dict[str, Any]:
    try:
        if not isinstance(arguments, dict):
            raise InvalidInputError("arguments must be an object")
        if name == "hermes_start_task":
            prompt = _validate_text(arguments, "prompt")
            response = _request("POST", "/v1/runs", {"input": prompt}, request_id=request_id)
            run_id = response.get("run_id") or response.get("id")
            _log("hermes_start_task", request_id, run_id if isinstance(run_id, str) else None)
            return {"content": [{"type": "text", "text": json.dumps(_run_response(response), separators=(",", ":"))}]}
        if name == "hermes_get_task":
            run_id = _validate_text(arguments, "run_id")
            response = _request("GET", f"/v1/runs/{quote(run_id, safe='')}", request_id=request_id)
            _log("hermes_get_task", request_id, run_id)
            return {"content": [{"type": "text", "text": json.dumps(_run_response(response), separators=(",", ":"))}]}
        if name == "hermes_steer_task":
            run_id = _validate_text(arguments, "run_id")
            instruction = _validate_text(arguments, "instruction")
            _request("POST", f"/v1/runs/{quote(run_id, safe='')}/steer", {"text": instruction}, request_id=request_id)
            _log("hermes_steer_task", request_id, run_id)
            return {"content": [{"type": "text", "text": json.dumps({"run_id": run_id, "status": "accepted", "message": f"steering instruction accepted for Hermes run {run_id}"}, separators=(",", ":"))}]}
        if name == "hermes_stop_task":
            run_id = _validate_text(arguments, "run_id")
            response = _request("POST", f"/v1/runs/{quote(run_id, safe='')}/stop", request_id=request_id)
            _log("hermes_stop_task", request_id, run_id)
            return {"content": [{"type": "text", "text": json.dumps(_run_response(response), separators=(",", ":"))}]}
        raise InvalidInputError(f"unknown tool: {name}")
    except AdapterError as exc:
        _log("mcp_error", request_id, category=exc.category)
        return _error(exc)
    except Exception:
        logger.exception(json.dumps({"event": "internal_adapter_failure", "request_id": str(request_id)}))
        return _error(InternalAdapterError("unexpected adapter failure"))


def _handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "hermes-gateway-mcp", "version": "0.1.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        return {"jsonrpc": "2.0", "id": request_id, "result": _call_tool(params.get("name"), params.get("arguments", {}), request_id)}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
    try:
        _config()
    except ConfigurationError as exc:
        logger.error(json.dumps({"event": "invalid_configuration", "error": str(exc)}))
        raise SystemExit(2)
    for line in sys.stdin:
        try:
            response = _handle(json.loads(line))
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except (json.JSONDecodeError, TypeError) as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
