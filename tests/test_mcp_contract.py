import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


class HermesStub(BaseHTTPRequestHandler):
    runs = {}
    starts = []
    steers = []
    stops = []
    ready = threading.Event()
    create_not_found = False

    def log_message(self, *_args):
        pass

    def _json(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path.startswith("/v1/runs/") and self.path.endswith("/stop"):
            run_id = unquote(self.path[len("/v1/runs/") : -len("/stop")])
            run = self.runs.get(run_id)
            if run is None:
                self._json(404, {"error": {"message": "run not found", "type": "invalid_request_error", "code": "run_not_found", "param": None}})
                return
            status = run.get("status")
            if status in {"completed", "failed", "cancelled", "interrupted", "stopped"}:
                self._json(200, run)
                return
            if status != "running":
                self._json(409, {"error": {"message": "run is not active", "type": "invalid_request_error", "code": "run_not_active", "param": None}})
                return
            self.stops.append(run_id)
            run["status"] = "stopping"
            self._json(200, {"run_id": run_id, "status": "stopping"})
            return
        if self.path.startswith("/v1/runs/") and self.path.endswith("/steer"):
            run_id = unquote(self.path[len("/v1/runs/") : -len("/steer")])
            run = self.runs.get(run_id)
            if run is None:
                self._json(404, {"error": {"message": "run not found", "type": "invalid_request_error", "code": "run_not_found", "param": None}})
                return
            if run.get("status") != "running":
                self._json(409, {"error": {"message": "run is not accepting steer", "type": "invalid_request_error", "code": "run_not_accepting_steer", "param": None}})
                return
            instruction = json.loads(self.rfile.read(int(self.headers["Content-Length"]))) ["text"]
            if instruction == "invalid input":
                self._json(400, {"error": {"message": "invalid steer input", "type": "invalid_request_error", "code": "invalid_steer_input", "param": "text"}})
                return
            if instruction == "race lost":
                self._json(409, {"error": {"message": "steer was not accepted", "type": "conflict_error", "code": "steer_not_accepted", "param": None}})
                return
            self.steers.append((run_id, instruction))
            self._json(200, {"run_id": run_id, "status": "accepted"})
            return
        if self.path != "/v1/runs":
            self._json(404, {"error": {"message": "not found", "type": "invalid_request_error", "code": "route_not_found", "param": None}})
            return
        if getattr(self, "create_not_found", False):
            self._json(404, {"error": {"message": "create route not found", "type": "invalid_request_error", "code": "route_not_found", "param": None}})
            return
        prompt = json.loads(self.rfile.read(int(self.headers["Content-Length"]))) ["input"]
        run_id = "run-stable-1" if prompt in {"inspect the local service", "persist in Hermes"} else f"run-{len(self.runs) + 1}"
        self.starts.append(prompt)
        self.runs[run_id] = {"run_id": run_id, "status": "running"}
        self.ready.set()
        self._json(202, {"run_id": run_id, "status": "running"})

    def do_GET(self):
        run_id = unquote(self.path.removeprefix("/v1/runs/"))
        run = self.runs.get(run_id)
        if run is None:
            self._json(404, {"error": {"message": "run not found", "type": "invalid_request_error", "code": "run_not_found", "param": None}})
            return
        self._json(200, run)


def rpc(proc, request):
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def start_stub():
    HermesStub.runs.clear()
    HermesStub.starts.clear()
    HermesStub.steers.clear()
    HermesStub.stops.clear()
    HermesStub.ready.clear()
    HermesStub.create_not_found = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), HermesStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def start_adapter(url):
    env = os.environ.copy()
    env["HERMES_GATEWAY_URL"] = url
    return subprocess.Popen(
        [sys.executable, "-m", "hermes_gateway_mcp.server"],
        cwd=Path(__file__).parents[1],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def test_public_mcp_start_and_status_are_async_and_stateless():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        initialized = rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert initialized["result"]["protocolVersion"] == "2025-06-18"

        tools = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert {"hermes_start_task", "hermes_get_task", "hermes_steer_task", "hermes_stop_task"} <= names
        steer_schema = next(t for t in tools["result"]["tools"] if t["name"] == "hermes_steer_task")["inputSchema"]
        assert steer_schema["required"] == ["run_id", "instruction"]
        assert steer_schema["properties"]["run_id"]["minLength"] == 1
        assert steer_schema["properties"]["instruction"]["minLength"] == 1
        stop_schema = next(t for t in tools["result"]["tools"] if t["name"] == "hermes_stop_task")["inputSchema"]
        assert stop_schema["required"] == ["run_id"]
        assert stop_schema["properties"]["run_id"]["minLength"] == 1
        start_schema = next(t for t in tools["result"]["tools"] if t["name"] == "hermes_start_task")["inputSchema"]
        assert start_schema["required"] == ["prompt"]
        assert start_schema["properties"]["prompt"]["minLength"] == 1

        began = time.monotonic()
        started = rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "hermes_start_task", "arguments": {"prompt": "inspect the local service"}
        }})
        assert time.monotonic() - began < 1
        start_data = json.loads(started["result"]["content"][0]["text"])
        assert start_data == {"run_id": "run-stable-1", "status": "running", "hermes_status": "running"}
        assert HermesStub.starts == ["inspect the local service"]

        active = rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "hermes_get_task", "arguments": {"run_id": "run-stable-1"}
        }})
        active_data = json.loads(active["result"]["content"][0]["text"])
        assert active_data["run_id"] == "run-stable-1"
        assert active_data["status"] == "running"
        assert "result" not in active_data

        HermesStub.runs["run-stable-1"] = {
            "run_id": "run-stable-1", "status": "completed", "output": "service is healthy"
        }
        completed = rpc(proc, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
            "name": "hermes_get_task", "arguments": {"run_id": "run-stable-1"}
        }})
        completed_data = json.loads(completed["result"]["content"][0]["text"])
        assert completed_data == {
            "run_id": "run-stable-1", "status": "completed", "hermes_status": "completed",
            "result": "service is healthy",
        }
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_validates_prompt_without_calling_gateway():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        invalid = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "hermes_start_task", "arguments": {"prompt": "   "}
        }})
        assert invalid["result"]["isError"] is True
        assert "prompt" in invalid["result"]["content"][0]["text"]
        assert HermesStub.starts == []
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_status_works_after_adapter_restart_without_local_run_store():
    stub = start_stub()
    first = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    second = None
    try:
        rpc(first, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        started = rpc(first, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "hermes_start_task", "arguments": {"prompt": "persist in Hermes"}
        }})
        run_id = json.loads(started["result"]["content"][0]["text"])["run_id"]
        first.kill()
        first.wait()

        second = start_adapter(f"http://127.0.0.1:{stub.server_port}")
        rpc(second, {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}})
        status = rpc(second, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "hermes_get_task", "arguments": {"run_id": run_id}
        }})
        restarted_data = json.loads(status["result"]["content"][0]["text"])
        assert restarted_data == {"run_id": run_id, "status": "running", "hermes_status": "running"}
    finally:
        if first.poll() is None:
            first.kill()
            first.wait()
        if second is not None:
            second.kill()
            second.wait()
        stub.shutdown()


def call_task(proc, request_id, name, arguments):
    response = rpc(proc, {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
        "name": name, "arguments": arguments
    }})
    assert response["result"].get("isError") is not True
    return json.loads(response["result"]["content"][0]["text"])


def test_public_mcp_normalizes_all_supported_lifecycle_states_and_preserves_metadata():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        states = {
            "queued": "pending",
            "running": "active",
            "completed": "succeeded",
            "failed": "error",
            "stopped": "cancelled",
            "waiting": "waiting_for_approval",
        }
        for expected, native in states.items():
            run_id = f"run-{expected}"
            HermesStub.runs[run_id] = {
                "run_id": run_id,
                "state": native,
                "created_at": "2026-10-01T10:00:00Z",
                "started_at": "2026-10-01T10:00:01Z",
                "updated_at": "2026-10-01T10:00:02Z",
            }
            if expected == "completed":
                HermesStub.runs[run_id]["result"] = {"answer": 42}
            if expected == "failed":
                HermesStub.runs[run_id]["error"] = {"message": "tool execution failed"}
            data = call_task(proc, expected, "hermes_get_task", {"run_id": run_id})
            assert data["status"] == expected
            assert data["hermes_status"] == native
            assert data["created_at"] == "2026-10-01T10:00:00Z"
            assert data["updated_at"] == "2026-10-01T10:00:02Z"
            if expected == "completed":
                assert data["result"] == {"answer": 42}
            if expected == "failed":
                assert data["error_summary"] == "tool execution failed"
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_preserves_transient_stopping_as_non_terminal():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    run_id = "run-stopping"
    HermesStub.runs[run_id] = {"run_id": run_id, "status": "stopping"}
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        data = call_task(proc, 2, "hermes_get_task", {"run_id": run_id})
        assert data == {"run_id": run_id, "status": "stopping", "hermes_status": "stopping"}
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_isolates_multiple_runs_and_preserves_gateway_error_details():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        first = call_task(proc, 2, "hermes_start_task", {"prompt": "first independent run"})
        second = call_task(proc, 3, "hermes_start_task", {"prompt": "second independent run"})
        HermesStub.runs[first["run_id"]] = {"run_id": first["run_id"], "status": "completed", "output": "first result"}
        HermesStub.runs[second["run_id"]] = {"run_id": second["run_id"], "status": "failed", "error": "second failed"}
        assert call_task(proc, 4, "hermes_get_task", {"run_id": first["run_id"]})["result"] == "first result"
        assert call_task(proc, 5, "hermes_get_task", {"run_id": second["run_id"]})["error_summary"] == "second failed"
        unknown = rpc(proc, {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {
            "name": "hermes_get_task", "arguments": {"run_id": "does-not-exist"}
        }})
        assert unknown["result"]["isError"] is True
        unknown_error = json.loads(unknown["result"]["content"][0]["text"])
        assert unknown_error == {
            "status": 404,
            "error": {
                "message": "run not found",
                "type": "invalid_request_error",
                "code": "run_not_found",
                "param": None,
            },
        }
        invalid = rpc(proc, {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
            "name": "hermes_get_task", "arguments": {"run_id": "   "}
        }})
        assert invalid["result"] == {"content": [{"type": "text", "text": "run_id must be a non-empty string"}], "isError": True}
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_treats_run_id_as_one_opaque_path_segment():
    stub = start_stub()
    special_id = "run/with?reserved#characters"
    HermesStub.runs[special_id] = {"run_id": special_id, "status": "completed", "output": "opaque"}
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        data = call_task(proc, 2, "hermes_get_task", {"run_id": special_id})
        assert data == {"run_id": special_id, "status": "completed", "hermes_status": "completed", "result": "opaque"}
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_steers_active_run_and_isolates_concurrent_runs():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        first = call_task(proc, 2, "hermes_start_task", {"prompt": "first steerable run"})
        second = call_task(proc, 3, "hermes_start_task", {"prompt": "second steerable run"})
        HermesStub.runs[first["run_id"]] = {"run_id": first["run_id"], "status": "running"}
        HermesStub.runs[second["run_id"]] = {"run_id": second["run_id"], "status": "running"}

        steered = call_task(proc, 4, "hermes_steer_task", {
            "run_id": second["run_id"], "instruction": "also inspect the deployment manifest"
        })
        assert steered == {
            "run_id": second["run_id"],
            "status": "accepted",
            "message": f"steering instruction accepted for Hermes run {second['run_id']}",
        }
        assert HermesStub.steers == [(second["run_id"], "also inspect the deployment manifest")]
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_steering_validates_inputs_and_preserves_gateway_errors():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        for request_id, arguments, expected in [
            (2, {"instruction": "continue"}, "run_id must be a non-empty string"),
            (3, {"run_id": "run-1", "instruction": "   "}, "instruction must be a non-empty string"),
        ]:
            invalid = rpc(proc, {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
                "name": "hermes_steer_task", "arguments": arguments
            }})
            assert invalid["result"] == {"content": [{"type": "text", "text": expected}], "isError": True}

        unknown = rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "hermes_steer_task", "arguments": {
                "run_id": "missing-run", "instruction": "continue"
            }
        }})
        unknown_error = json.loads(unknown["result"]["content"][0]["text"])
        assert unknown_error == {
            "status": 404,
            "error": {
                "message": "run not found",
                "type": "invalid_request_error",
                "code": "run_not_found",
                "param": None,
            },
        }

        HermesStub.runs["terminal-run"] = {"run_id": "terminal-run", "status": "completed"}
        terminal = rpc(proc, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
            "name": "hermes_steer_task", "arguments": {
                "run_id": "terminal-run", "instruction": "continue anyway"
            }
        }})
        terminal_error = json.loads(terminal["result"]["content"][0]["text"])
        assert terminal_error["status"] == 409
        assert terminal_error["error"]["code"] == "run_not_accepting_steer"

        HermesStub.runs["running-run"] = {"run_id": "running-run", "status": "running"}
        for request_id, instruction, status, code in [
            (6, "invalid input", 400, "invalid_steer_input"),
            (7, "race lost", 409, "steer_not_accepted"),
        ]:
            rejected = rpc(proc, {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
                "name": "hermes_steer_task", "arguments": {
                    "run_id": "running-run", "instruction": instruction
                }
            }})
            assert rejected["result"]["isError"] is True
            error = json.loads(rejected["result"]["content"][0]["text"])
            assert error["status"] == status
            assert error["error"]["code"] == code
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_does_not_misclassify_unrelated_create_route_404():
    stub = start_stub()
    HermesStub.create_not_found = True
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        response = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "hermes_start_task", "arguments": {"prompt": "will fail at create"}
        }})
        assert response["result"]["isError"] is True
        error = json.loads(response["result"]["content"][0]["text"])
        assert error["status"] == 404
        assert error["error"]["code"] == "route_not_found"
        assert error["error"]["code"] != "run_not_found"
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()



def test_public_mcp_stops_active_run_with_ack_and_preserves_concurrent_run_isolation():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        first = call_task(proc, 2, "hermes_start_task", {"prompt": "first stoppable run"})
        second = call_task(proc, 3, "hermes_start_task", {"prompt": "second stoppable run"})
        HermesStub.runs[first["run_id"]]["status"] = "running"
        HermesStub.runs[second["run_id"]]["status"] = "running"
        stopping = call_task(proc, 4, "hermes_stop_task", {"run_id": first["run_id"]})
        assert stopping == {"run_id": first["run_id"], "status": "stopping", "hermes_status": "stopping"}
        assert HermesStub.stops == [first["run_id"]]
        assert call_task(proc, 5, "hermes_get_task", {"run_id": first["run_id"]})["status"] == "stopping"
        assert call_task(proc, 6, "hermes_get_task", {"run_id": second["run_id"]})["status"] == "running"
        HermesStub.runs[first["run_id"]]["status"] = "cancelled"
        terminal = call_task(proc, 7, "hermes_get_task", {"run_id": first["run_id"]})
        assert terminal == {"run_id": first["run_id"], "status": "stopped", "hermes_status": "cancelled"}
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_stop_returns_existing_terminal_hermes_state():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        HermesStub.runs["completed-run"] = {"run_id": "completed-run", "status": "completed"}
        HermesStub.runs["completed-run"]["output"] = "already done"
        terminal = call_task(proc, 2, "hermes_stop_task", {"run_id": "completed-run"})
        assert terminal == {
            "run_id": "completed-run", "status": "completed", "hermes_status": "completed", "result": "already done"
        }
        assert HermesStub.stops == []
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()


def test_public_mcp_stop_preserves_structured_hermes_domain_errors():
    stub = start_stub()
    proc = start_adapter(f"http://127.0.0.1:{stub.server_port}")
    try:
        rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        for request_id, run_id, expected_status, expected_code in [
            (2, "does-not-exist", 404, "run_not_found"),
            (3, "queued-run", 409, "run_not_active"),
        ]:
            if run_id == "queued-run":
                HermesStub.runs[run_id] = {"run_id": run_id, "status": "queued"}
            response = rpc(proc, {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
                "name": "hermes_stop_task", "arguments": {"run_id": run_id}
            }})
            assert response["result"]["isError"] is True
            error = json.loads(response["result"]["content"][0]["text"])
            assert error["status"] == expected_status
            assert error["error"]["code"] == expected_code
            assert error["error"]["type"] == "invalid_request_error"
    finally:
        proc.kill()
        proc.wait()
        stub.shutdown()
