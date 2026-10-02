# Deployment

This project deploys a stdio MCP adapter and an outbound tunnel. Hermes Gateway is an external prerequisite and dependency. Many users already run it separately.

## Prerequisites

- Linux with systemd user services.
- A non-root service user with a working home directory.
- Python 3.9 or newer; Python 3.11/3.12 is recommended.
- `uv` installed for that user and available in `PATH`.
- A reachable Hermes Gateway. If it is colocated with the adapter, prefer a loopback URL such as `http://127.0.0.1:8642`.
- The official tunnel-client binary for the host architecture.
- An existing outbound tunnel profile and control-plane credentials.

Hermes Gateway itself is not required to be installed by this repository. If it is already running, do not install or start `deploy/hermes-gateway.service`.

## Directory layout

Example paths for a Raspberry Pi user named `pi`:

```text
/home/pi/code/hermes-chatgpt-gateway/
  deploy/
  docs/
  scripts/
  src/
  tests/
/home/pi/.config/hermes-chatgpt-gateway/hermes.env
/home/pi/.config/hermes-chatgpt-gateway/openai-tunnel.env
/home/pi/.config/tunnel-client/hermes-chatgpt.yaml
/home/pi/.config/systemd/user/hermes-chatgpt-tunnel.service
```

Clone and install the adapter as the service user:

```sh
mkdir -p /home/pi/code
git clone git@github.com:kaisky89/hermes-chatgpt-gateway.git /home/pi/code/hermes-chatgpt-gateway
cd /home/pi/code/hermes-chatgpt-gateway
uv sync
chmod 700 scripts/run-hermes-gateway-mcp scripts/run-hermes-chatgpt-tunnel scripts/smoke-test
```

Replace `/home/pi` and the username when needed. The checked-in unit and profile templates currently use the Pi paths shown above.

## Environment and permissions

Keep runtime configuration outside the repository:

```sh
install -d -m 700 /home/pi/.config/hermes-chatgpt-gateway
install -d -m 700 /home/pi/.config/tunnel-client
chmod 600 /home/pi/.config/hermes-chatgpt-gateway/hermes.env
chmod 600 /home/pi/.config/hermes-chatgpt-gateway/openai-tunnel.env
chmod 600 /home/pi/.config/tunnel-client/hermes-chatgpt.yaml
```

`hermes.env` uses trusted shell assignments:

```sh
HERMES_GATEWAY_URL=http://127.0.0.1:8642
HERMES_GATEWAY_TIMEOUT=10
# HERMES_GATEWAY_API_KEY=...
```

Set `HERMES_GATEWAY_URL` to the existing Gateway address. Use a loopback address when the adapter and Gateway are colocated.

`openai-tunnel.env` contains the tunnel credentials:

```sh
CONTROL_PLANE_API_KEY=...
CONTROL_PLANE_TUNNEL_ID=...
```

Do not commit these files or print their contents.

## Adapter and tunnel installation

Install the tunnel profile and the required adapter/tunnel user unit:

```sh
install -D -m 600 deploy/hermes-chatgpt.yaml /home/pi/.config/tunnel-client/hermes-chatgpt.yaml
install -D -m 600 deploy/hermes-chatgpt-tunnel.service /home/pi/.config/systemd/user/hermes-chatgpt-tunnel.service
systemctl --user daemon-reload
```

The profile runs the absolute stdio adapter launcher and binds the tunnel health endpoint to `127.0.0.1:8081`. The adapter launcher reads `hermes.env`; the tunnel launcher reads both protected env files.

## Tunnel profile checks

Before enabling autostart:

```sh
tunnel-client doctor --profile hermes-chatgpt
tunnel-client run --profile hermes-chatgpt
curl --fail --silent --show-error http://127.0.0.1:8081/
```

The foreground client should report the expected profile, stdio target, tunnel ID, and no first failing dependency. Never paste credential-bearing diagnostics into tickets or logs.

## User-level tunnel service

Validate and start the tunnel service:

```sh
systemd-analyze verify deploy/hermes-chatgpt-tunnel.service
systemctl --user enable --now hermes-chatgpt-tunnel.service
systemctl --user is-active hermes-chatgpt-tunnel.service
curl --fail --silent --show-error http://127.0.0.1:8081/
```

If the service must start before an interactive login, enable lingering for the service user:

```sh
loginctl enable-linger pi
```

Use the actual service username in place of `pi`.

## Optional: run Hermes Gateway as a user systemd service

`deploy/hermes-gateway.service` is an optional convenience/example for users who do not already manage Hermes Gateway as a service and specifically want a user-level systemd service. It is not the canonical Hermes deployment method and is not required for this project.

If Hermes Gateway is already running, point `HERMES_GATEWAY_URL` at it and skip this section. Do not start a second Gateway on the same port.

Install the template only when it matches the user's Hermes installation and runtime paths:

```sh
systemd-analyze verify deploy/hermes-gateway.service
install -D -m 600 deploy/hermes-gateway.service /home/pi/.config/systemd/user/hermes-gateway.service
systemctl --user daemon-reload
```

Before starting it, stop any existing process that binds the same Gateway port. Then enable and check readiness:

```sh
systemctl --user enable --now hermes-gateway.service
systemctl --user is-active hermes-gateway.service
curl --fail --silent --show-error http://127.0.0.1:8642/health
```

The checked-in unit is retained because it is useful for the current Pi layout. Review and adapt its paths, environment, and command for other Hermes installations.

## First production setup and cutover

1. Record the existing Hermes Gateway startup method and configuration.
2. Confirm `HERMES_GATEWAY_URL` points to the intended reachable Gateway.
3. Validate the adapter directly with:

   ```sh
   HERMES_GATEWAY_ENV_FILE=/home/pi/.config/hermes-chatgpt-gateway/hermes.env scripts/run-hermes-gateway-mcp
   ```

4. Verify Gateway readiness at `/health`.
5. Run `tunnel-client doctor`, then a foreground tunnel test.
6. Install and enable the user-level tunnel service.
7. If using the optional Gateway unit, stop the prior process before starting the new unit on the same port.
8. Verify both service status and local health endpoints before using ChatGPT.

The tunnel and Gateway are independent. Starting or stopping this project's adapter/tunnel does not manage Telegram, Discord, Slack, or other Hermes interfaces.

## Readiness checks

```sh
curl --fail --silent --show-error http://127.0.0.1:8642/health
curl --fail --silent --show-error http://127.0.0.1:8081/
systemctl --user is-active hermes-chatgpt-tunnel.service
```

A successful health request is HTTP 200. The exact Gateway response body is Hermes-version dependent.
