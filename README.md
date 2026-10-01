# Hermes ChatGPT Gateway

A small MCP adapter that exposes Hermes Gateway runs to MCP clients.

## What it exposes

- `hermes_start_task`: submits a prompt to `POST /v1/runs` and returns immediately with Hermes' `run_id`.
- `hermes_get_task`: reads `GET /v1/runs/{run_id}` and returns normalized lifecycle status, the native Hermes status, available lifecycle timestamps, a completed `result`, or a failed-run `error_summary` when present.

The adapter keeps no run database, worker, or polling loop. Hermes remains the source of truth.

## Run

```sh
HERMES_GATEWAY_URL=http://127.0.0.1:8642 \
  uv run hermes-gateway-mcp
```

`HERMES_GATEWAY_URL` defaults to `http://127.0.0.1:8642`. Set `HERMES_GATEWAY_API_KEY` when the Gateway requires bearer authentication. `HERMES_GATEWAY_TIMEOUT` controls the bounded downstream request timeout in seconds.

The MCP server uses JSON-RPC over stdin/stdout, so it can be registered as a local stdio MCP server. It does not expose the Hermes Gateway itself.

## Tests

```sh
uv run --with pytest pytest
```

The contract tests launch the adapter through its public MCP protocol and use a local controlled Hermes-compatible HTTP stub. They cover discovery, prompt validation, asynchronous start, active and completed status, stable run IDs, and adapter restart without a local job store.

The downstream paths and payloads follow the documented Hermes Runs API: `POST /v1/runs` with an `input` string, then `GET /v1/runs/{run_id}`.
