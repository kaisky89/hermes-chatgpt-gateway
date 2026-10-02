## Repository layout

- `README.md` — concise project overview, architecture, tools, quick start, and development checks.
- `docs/deployment.md` — prerequisites, installation, configuration, user services, optional Gateway service setup, cutover, and readiness checks.
- `docs/operations.md` — operations, logs, troubleshooting, rotation, rollback, removal, compatibility, non-goals, and smoke testing.
- `hermes-chatgpt-gateway-spec.md` — complete product and implementation specification.
- `deploy/hermes-gateway.service` — optional user-level Hermes Gateway unit template.
- `deploy/hermes-chatgpt.yaml` — outbound tunnel profile template.
- `deploy/hermes-chatgpt-tunnel.service` — user-level tunnel unit.
- `scripts/run-hermes-gateway-mcp` — protected-env launcher for the stdio adapter.
- `scripts/run-hermes-chatgpt-tunnel` — protected-env launcher for the tunnel.
- `scripts/smoke-test` — controlled Gateway lifecycle smoke test.
- `tests/test_mcp_contract.py` — MCP and Hermes Runs API contract tests.
