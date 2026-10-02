# Hermes ChatGPT Gateway

A small MCP adapter that exposes Hermes Gateway runs to MCP clients.

## What it exposes

- `hermes_start_task`: submits a prompt to `POST /v1/runs` and returns immediately with Hermes' `run_id`.
- `hermes_get_task`: reads `GET /v1/runs/{run_id}` and returns normalized status plus the completed `output` when present.

The adapter keeps no run database, worker, or polling loop. Hermes remains the source of truth.

## Run

For a direct local run:

```sh
HERMES_GATEWAY_URL=http://127.0.0.1:8642 \
  uv run hermes-gateway-mcp
```

For the tunnel client, use the included launcher. It loads `/home/pi/.config/hermes-chatgpt-gateway/hermes.env` and starts the MCP server:

```sh
chmod +x scripts/run-hermes-gateway-mcp
scripts/run-hermes-gateway-mcp
```

The env file can be located elsewhere by setting `HERMES_GATEWAY_ENV_FILE`. Example contents:

```sh
HERMES_GATEWAY_URL=http://127.0.0.1:8642
# Set only if the Gateway requires bearer authentication.
HERMES_GATEWAY_API_KEY=your-key
HERMES_GATEWAY_TIMEOUT=10
```

The launcher sources this file as shell syntax, so keep it owner-controlled (for example, `chmod 600 /home/pi/.config/hermes-chatgpt-gateway/hermes.env`) and only put trusted assignments in it. The tunnel profile's MCP command should point to the absolute path of `scripts/run-hermes-gateway-mcp` on the Pi. The launcher uses `uv` from `PATH` and runs the project by its detected location.

`HERMES_GATEWAY_URL` defaults to `http://127.0.0.1:8642`. `HERMES_GATEWAY_TIMEOUT` controls the bounded downstream request timeout in seconds.

The MCP server uses JSON-RPC over stdin/stdout, so it can be registered as a local stdio MCP server. It does not expose the Hermes Gateway itself.

## OpenAI tunnel deployment

Templates are in `deploy/`:

- `hermes-chatgpt.yaml` — tunnel profile
- `hermes-chatgpt-tunnel.service` — systemd user service

Install the profile as `/home/pi/.config/tunnel-client/hermes-chatgpt.yaml`. Create `/home/pi/.config/hermes-chatgpt-gateway/openai-tunnel.env` containing `CONTROL_PLANE_API_KEY=...` and `CONTROL_PLANE_TUNNEL_ID=...` (the tunnel ID assigned to this ChatGPT connector). The tunnel client supports `CONTROL_PLANE_TUNNEL_ID` as an environment setting, which takes precedence over YAML config. Create `/home/pi/.config/hermes-chatgpt-gateway/hermes.env` with the Hermes Gateway settings described above. Restrict both files with `chmod 600`.

Install the project at `/home/pi/code/hermes-chatgpt-gateway` (the launcher path in the profile assumes this location). For development or a manual test, start the tunnel in the foreground:

```sh
chmod +x scripts/run-hermes-gateway-mcp scripts/run-hermes-chatgpt-tunnel
scripts/run-hermes-chatgpt-tunnel
```

This loads both env files and runs the `hermes-chatgpt` profile in the foreground. Keep the terminal open; press Ctrl-C to stop the tunnel and its MCP child process. Set `HERMES_CHATGPT_CONFIG_DIR` to change the env-file directory, `OPENAI_TUNNEL_ENV_FILE` or `HERMES_GATEWAY_ENV_FILE` to override an individual env-file path, and `TUNNEL_CLIENT_BIN` if the tunnel client is not on `PATH`.

For production, install and enable the user service:

```sh
install -D -m 600 deploy/hermes-chatgpt.yaml /home/pi/.config/tunnel-client/hermes-chatgpt.yaml
install -D -m 600 deploy/hermes-chatgpt-tunnel.service /home/pi/.config/systemd/user/hermes-chatgpt-tunnel.service
systemctl --user daemon-reload
systemctl --user enable --now hermes-chatgpt-tunnel.service
systemctl --user status hermes-chatgpt-tunnel.service
```

The service starts the tunnel client with the `hermes-chatgpt` profile, loads the control-plane and Hermes environment files, and restarts on failure. Its environment files must use systemd `EnvironmentFile` assignment syntax (`NAME=value`), not shell commands. The launcher also sources the Hermes env file, so keep that file to trusted variable assignments. Check logs with `journalctl --user -u hermes-chatgpt-tunnel.service`.

## Tests

```sh
uv run --with pytest pytest
```

The contract tests launch the adapter through its public MCP protocol and use a local controlled Hermes-compatible HTTP stub. They cover discovery, prompt validation, asynchronous start, active and completed status, stable run IDs, and adapter restart without a local job store.

The downstream paths and payloads follow the documented Hermes Runs API: `POST /v1/runs` with an `input` string, then `GET /v1/runs/{run_id}`.
