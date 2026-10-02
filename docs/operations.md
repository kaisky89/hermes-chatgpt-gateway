# Operations

The adapter is stateless. Hermes Gateway owns run state. The outbound tunnel and optional Gateway service are separate user-level services.

## Status, start, stop, and restart

For the required tunnel service:

```sh
systemctl --user status hermes-chatgpt-tunnel.service
systemctl --user start hermes-chatgpt-tunnel.service
systemctl --user stop hermes-chatgpt-tunnel.service
systemctl --user restart hermes-chatgpt-tunnel.service
```

If the optional Gateway user service is installed, manage it separately:

```sh
systemctl --user status hermes-gateway.service
systemctl --user start hermes-gateway.service
systemctl --user stop hermes-gateway.service
systemctl --user restart hermes-gateway.service
```

Do not run two Gateway processes on the same port.

## Logs

```sh
journalctl --user -u hermes-chatgpt-tunnel.service -b
journalctl --user -u hermes-chatgpt-tunnel.service -f
journalctl --user -u hermes-gateway.service -b
journalctl --user -u hermes-gateway.service -f
```

The adapter writes protocol data to stdout and safe diagnostic records to stderr. Never publish credential-bearing environment files or diagnostics.

## Health checks

```sh
curl --fail --silent --show-error http://127.0.0.1:8642/health
curl --fail --silent --show-error http://127.0.0.1:8081/
systemctl --user is-active hermes-chatgpt-tunnel.service
```

Use the Gateway's configured reachable URL if it is not local. The exact `/health` response body is Hermes-version dependent.

## Troubleshooting

Gateway unavailable: verify the existing Gateway process, `HERMES_GATEWAY_URL`, the `/health` endpoint, and any required API key. If using the optional unit, inspect its journal and confirm its Hermes paths.

Port already in use: identify and stop the other process before starting the optional user Gateway service. Never run two Gateways on the same port.

Adapter exits at startup: check env-file readability, trusted assignment syntax, URL, timeout, and restrictive permissions.

Tunnel fails: run `tunnel-client doctor --profile hermes-chatgpt`, inspect the tunnel journal, verify the profile path and both env files, and check `127.0.0.1:8081`.

ChatGPT cannot discover tools: verify the tunnel is active, the MCP command is the absolute launcher path, and the launcher can reach the Gateway health endpoint.

## Credential rotation

1. Stop the tunnel service.
2. Replace the control-plane values in the protected env file.
3. Restore owner-only permissions with `chmod 600`.
4. Start the tunnel service.
5. Verify tunnel health and readiness.

Do not commit or print credentials. Rotate Gateway credentials using the procedure required by the separately managed Hermes Gateway.

## Rollback

Record the user's prior Gateway startup method before any migration. To roll back an optional user-service cutover:

1. Stop and disable the new user Gateway unit if it is installed.
2. Confirm its process no longer binds the Gateway port.
3. Restore the recorded previous startup method and environment.
4. Verify `/health` before restarting the tunnel.

If only the adapter/tunnel changed, stop the tunnel service and restore the previous tunnel or adapter startup method. Do not assume a root/system service or a particular prior process manager.

## Removal and uninstall

Stop and disable the services that were actually installed:

```sh
systemctl --user disable --now hermes-chatgpt-tunnel.service
systemctl --user disable --now hermes-gateway.service  # only if installed
```

Remove the installed user units, tunnel profile, and protected env files as appropriate. Optionally remove the checkout. Do not remove Hermes itself unless that is a separate, intentional operation. Disable lingering only if no other user services need it.

## Compatibility expectations

The adapter follows these Hermes Runs API routes:

- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/steer`
- `POST /v1/runs/{run_id}/stop`

It forwards structured Hermes errors and normalizes lifecycle status for MCP clients. Hermes API or MCP discovery changes require the contract tests to be updated together. The adapter remains independent of Telegram, Discord, Slack, and other Hermes interfaces.

## V1 non-goals

This project does not add adapter-side persistence, a queue, a worker, a polling loop, LLM orchestration, domain remapping, replacement Hermes connectors, or a pinned tunnel-client release and integrity-verification system.

## Smoke test

Run the controlled-Gateway lifecycle smoke test from the repository:

```sh
scripts/smoke-test
```

It covers MCP discovery and the start/get/steer/stop lifecycle without an LLM or production credentials. For a real Hermes check, verify `/health`, then exercise all four MCP tools through ChatGPT. Check run IDs, statuses, and result/error fields; do not assert exact LLM wording.

## Verification

```sh
uv run --with pytest pytest
uv run --with ruff ruff check .
uv run python -m compileall -q src tests
git diff --check
```
