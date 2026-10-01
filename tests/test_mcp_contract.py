import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class HermesStub(BaseHTTPRequestHandler):
    runs = {}
    starts = []
    ready = threading.Event()

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
        if self.path != "/v1/runs":
            self._json(404, {"error": "not found"})
            return
        prompt = json.loads(self.rfile.read(int(self.headers["Content-Length"]))) ["input"]
        run_id = "run-stable-1"
        self.starts.append(prompt)
        self.runs[run_id] = {"run_id": run_id, "status": "running"}
        self.ready.set()
        self._json(202, {"run_id": run_id, "status": "running"})

    def do_GET(self):
        run_id = self.path.removeprefix("/v1/runs/")
        run = self.runs.get(run_id)
        if run is None:
            self._json(404, {"error": "unknown run"})
            return
        self._json(200, run)


def rpc(proc, request):
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def start_stub():
    HermesStub.runs.clear()
    HermesStub.starts.clear()
    HermesStub.ready.clear()
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
        assert {"hermes_start_task", "hermes_get_task"} <= names
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
        assert json.loads(status["result"]["content"][0]["text"])["run_id"] == run_id
    finally:
        if first.poll() is None:
            first.kill()
            first.wait()
        if second is not None:
            second.kill()
            second.wait()
        stub.shutdown()
