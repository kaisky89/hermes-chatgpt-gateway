# Hermes ChatGPT Gateway

A thin stdio MCP adapter that exposes Hermes Gateway runs to ChatGPT through the official outbound tunnel.

The adapter exposes four tools: start a task, get a task, steer an active task, and stop a task. It keeps no run database, worker, or polling loop. Hermes remains the source of truth. Telegram, Discord, Slack, and other Hermes interfaces remain independent.

Architecture and trust boundaries

ChatGPT -> outbound tunnel client -> local stdio MCP adapter -> http://127.0.0.1:8642 Hermes Gateway

The Raspberry Pi makes an outbound tunnel connection. No inbound router port forwarding is required. The adapter does not expose an HTTP or LAN listener; only the Hermes Gateway uses its loopback HTTP endpoint. Keep the Gateway bound to loopback. The tunnel health/admin endpoint is also bound to 127.0.0.1.

V1 non-goals: no adapter-side persistence, queue, worker, polling loop, LLM orchestration, domain remapping, replacement of Hermes connectors, or pinned tunnel-client release/integrity verification. The last item is intentionally out of scope for this personal deployment.

Clean Raspberry Pi installation

Prerequisites:

- Raspberry Pi OS or another Linux system with systemd user services.
- A non-root user, here named pi, with a working home directory.
- Python 3.9 or newer; Python 3.11/3.12 is recommended.
- uv installed for that user and available in PATH.
- A working Hermes Agent installation under /home/pi/.hermes.
- The official tunnel-client binary installed for the Pi architecture and available at /home/pi/.local/bin/tunnel-client.
- An existing OpenAI tunnel profile and its control-plane credentials.

Checkout and install:

    mkdir -p /home/pi/code
    git clone git@github.com:kaisky89/hermes-chatgpt-gateway.git /home/pi/code/hermes-chatgpt-gateway
    cd /home/pi/code/hermes-chatgpt-gateway
    uv sync
    chmod 700 scripts/run-hermes-gateway-mcp scripts/run-hermes-chatgpt-tunnel scripts/smoke-test

The project is pure Python and has no build-time service daemon. uv creates or uses the project environment from pyproject.toml and uv.lock. Run commands as the service user, not root.

Runtime files and permissions

Create these files outside the repository:

    install -d -m 700 /home/pi/.config/hermes-chatgpt-gateway
    install -d -m 700 /home/pi/.config/tunnel-client
    chmod 600 /home/pi/.config/hermes-chatgpt-gateway/hermes.env
    chmod 600 /home/pi/.config/hermes-chatgpt-gateway/openai-tunnel.env
    chmod 600 /home/pi/.config/tunnel-client/hermes-chatgpt.yaml

hermes.env uses trusted shell assignments:

    HERMES_GATEWAY_URL=http://127.0.0.1:8642
    HERMES_GATEWAY_TIMEOUT=10
    # Set only when the Gateway requires it:
    # HERMES_GATEWAY_API_KEY=...

openai-tunnel.env contains the tunnel credentials:

    CONTROL_PLANE_API_KEY=...
    CONTROL_PLANE_TUNNEL_ID=...

Install the profile and service templates:

    install -D -m 600 deploy/hermes-chatgpt.yaml /home/pi/.config/tunnel-client/hermes-chatgpt.yaml
    install -D -m 600 deploy/hermes-gateway.service /home/pi/.config/systemd/user/hermes-gateway.service
    install -D -m 600 deploy/hermes-chatgpt-tunnel.service /home/pi/.config/systemd/user/hermes-chatgpt-tunnel.service

Expected layout:

    /home/pi/code/hermes-chatgpt-gateway/
      deploy/
      scripts/
      src/
      tests/
    /home/pi/.config/hermes-chatgpt-gateway/hermes.env
    /home/pi/.config/hermes-chatgpt-gateway/openai-tunnel.env
    /home/pi/.config/tunnel-client/hermes-chatgpt.yaml
    /home/pi/.config/systemd/user/hermes-gateway.service
    /home/pi/.config/systemd/user/hermes-chatgpt-tunnel.service

Local start and readiness checks

For a direct adapter test:

    cd /home/pi/code/hermes-chatgpt-gateway
    HERMES_GATEWAY_ENV_FILE=/home/pi/.config/hermes-chatgpt-gateway/hermes.env scripts/run-hermes-gateway-mcp

The command uses JSON-RPC over stdin/stdout and logs only safe JSON records to stderr. It must not be exposed as a network service.

Verify Hermes locally before starting the tunnel:

    curl --fail --silent --show-error http://127.0.0.1:8642/health

A successful response is HTTP 200. The exact body is Hermes-version dependent. A 405 from POST/GET probing another Gateway route can still mean the listener is reachable; use /health for readiness.

Verify the tunnel profile before enabling autostart:

    tunnel-client doctor --profile hermes-chatgpt
    tunnel-client run --profile hermes-chatgpt

The profile health/admin endpoint is 127.0.0.1:8081 as configured in deploy/hermes-chatgpt.yaml. While the client runs, verify it returns HTTP 200:

    curl --fail --silent --show-error http://127.0.0.1:8081/

Also inspect the foreground startup summary or journal for the profile name, stdio target, tunnel ID, and an empty first_failing_dependency. Never paste API keys or full credential-bearing diagnostics into tickets or logs.

Production user services

The Hermes unit was based on the current Raspberry Pi command and runtime observed during deployment:

    /home/pi/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run

It uses /home/pi/.hermes as its working directory, HERMES_HOME=/home/pi/.hermes, the existing Gateway configuration and port, and user pi. The exact unit name is hermes-gateway.service in the user manager. Do not run the development/manual Gateway at the same time; both use the same port.

Prepare and validate before cutover:

    systemd-analyze verify deploy/hermes-gateway.service deploy/hermes-chatgpt-tunnel.service
    install -D -m 600 deploy/hermes-gateway.service /home/pi/.config/systemd/user/hermes-gateway.service
    install -D -m 600 deploy/hermes-chatgpt-tunnel.service /home/pi/.config/systemd/user/hermes-chatgpt-tunnel.service
    systemctl --user daemon-reload
    systemctl --user enable hermes-gateway.service hermes-chatgpt-tunnel.service

If user services must start before an interactive login, enable lingering once:

    loginctl enable-linger pi

Cutover and rollback:

1. Record the current manual command and verify the new unit with systemctl --user cat/status and systemd-analyze verify.
2. Stop the currently running development/manual Gateway cleanly. On this Pi, the observed existing process is currently managed by the system unit hermes-gateway.service; stop that system unit only after preparation is complete.
3. Start the user service immediately on the same port:

       systemctl --user start hermes-gateway.service
       systemctl --user is-active hermes-gateway.service
       curl --fail --silent --show-error http://127.0.0.1:8642/health

4. Start the tunnel independently:

       systemctl --user restart hermes-chatgpt-tunnel.service
       systemctl --user is-active hermes-chatgpt-tunnel.service
       curl --fail --silent --show-error http://127.0.0.1:8081/

Prepared rollback if the user Hermes unit fails: stop it, then restart the previous system-managed process with `sudo systemctl start hermes-gateway.service`. If the previous process was manually launched instead, run the recorded command from /home/pi/.hermes with its original environment. Restore the tunnel only after Gateway readiness is confirmed.

Normal operations

    systemctl --user status hermes-gateway.service hermes-chatgpt-tunnel.service
    systemctl --user restart hermes-gateway.service
    systemctl --user restart hermes-chatgpt-tunnel.service
    systemctl --user stop hermes-chatgpt-tunnel.service
    journalctl --user -u hermes-gateway.service -f
    journalctl --user -u hermes-chatgpt-tunnel.service -f

Restart the tunnel after changing its profile or credentials. Restart Hermes after changing Gateway settings. The two services are independent; stopping the adapter/tunnel does not stop Telegram, Discord, Slack, or other Hermes interfaces.

Troubleshooting:

- Gateway unit inactive: inspect `journalctl --user -u hermes-gateway.service -b`, confirm the Hermes virtualenv and /home/pi/.hermes exist, then use the rollback command above.
- Port already in use: stop the other development/system Gateway before starting the user unit. Never run both on port 8642.
- Adapter exits at startup: check env-file readability, assignment syntax, URL, timeout, and restrictive permissions.
- Tunnel fails: run `tunnel-client doctor --profile hermes-chatgpt`, inspect the service journal, verify the profile path and the two env files, then check 127.0.0.1:8081.
- ChatGPT cannot discover tools: verify the tunnel is active, the MCP command is the absolute launcher path, and the launcher can reach /health through the loopback Gateway.

Credential rotation: stop the tunnel, replace CONTROL_PLANE_API_KEY and/or CONTROL_PLANE_TUNNEL_ID in the protected env file, chmod 600 it, start the tunnel, and verify its health/readiness. Do not commit or print the values. Remove/uninstall with `systemctl --user disable --now hermes-chatgpt-tunnel.service hermes-gateway.service`, remove the installed user unit/profile/env files, and optionally remove the checkout. Do not remove Hermes itself unless that is a separate, intentional operation.

Compatibility expectations: the adapter follows the Hermes Runs API routes POST /v1/runs, GET /v1/runs/{run_id}, POST /v1/runs/{run_id}/steer, and POST /v1/runs/{run_id}/stop. It forwards structured Hermes errors and normalizes lifecycle status for MCP clients. Hermes API or MCP discovery changes require the contract tests to be updated together.

Smoke testing

The repeatable controlled-Gateway smoke test covers MCP discovery and the start/get/steer/stop lifecycle without an LLM or production credentials:

    cd /home/pi/code/hermes-chatgpt-gateway
    scripts/smoke-test

It starts the existing local controlled HTTP stub through the contract tests and checks lifecycle behavior. For a real Hermes check, first verify /health, then use ChatGPT to call all four tools: start a short task, get it until a terminal state, steer an active task when applicable, and stop a separate active task. Verify run IDs, statuses, and returned result/error fields; do not assert exact LLM wording.

Verification and CI

    uv run --with pytest pytest
    uv run --with ruff ruff check .
    uv run python -m compileall -q src tests
    git diff --check

CI runs the contract tests, Ruff, compileall, and diff checks. The tunnel-client release is intentionally not pinned and its integrity is not verified in this repository, as permitted for this personal deployment.
