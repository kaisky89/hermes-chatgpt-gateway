# Hermes ChatGPT Gateway

A thin stdio MCP adapter that exposes Hermes Gateway runs to ChatGPT through an outbound tunnel. Hermes remains the source of truth; the adapter has no run database, worker, or polling loop.

## Architecture

ChatGPT -> outbound tunnel -> stdio MCP adapter -> Hermes Gateway

The adapter uses the Hermes Gateway Runs API over HTTP. The adapter does not expose an HTTP or LAN listener. Keep the Gateway loopback-only when the adapter and Gateway run on the same host.

## MCP tools

- `hermes_start_task`
- `hermes_get_task`
- `hermes_steer_task`
- `hermes_stop_task`

## Quick start

Start the local stdio adapter with an existing reachable Hermes Gateway:

```sh
HERMES_GATEWAY_ENV_FILE=/path/to/hermes.env scripts/run-hermes-gateway-mcp
```

The command speaks JSON-RPC over stdin/stdout. It is intended to be started by the tunnel client, not exposed as a network service.

## Raspberry Pi deployment

See [docs/deployment.md](docs/deployment.md) for prerequisites, configuration, tunnel installation, user services, optional Gateway service setup, and readiness checks.

## Operations

See [docs/operations.md](docs/operations.md) for service control, logs, health checks, troubleshooting, rotation, rollback, removal, compatibility, and smoke testing.

## Development & tests

```sh
uv run --with pytest pytest
uv run --with ruff ruff check .
uv run python -m compileall -q src tests
scripts/smoke-test
```

Run `git diff --check` before committing documentation changes.

## Design principles

- Hermes is the source of truth.
- No adapter-side run database, worker, or polling loop.
- The Gateway should normally be loopback-only.
- Independent of Telegram, Discord, Slack, and other Hermes interfaces.
