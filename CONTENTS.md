## Repository layout

- `README.md` — Raspberry Pi installation, architecture, operations, cutover, rollback, and verification guide.
- `hermes-chatgpt-gateway-spec.md` — complete product and implementation specification.
- `deploy/hermes-gateway.service` — user-level Hermes Gateway unit based on the observed Pi runtime.
- `deploy/hermes-chatgpt.yaml` — outbound tunnel profile template.
- `deploy/hermes-chatgpt-tunnel.service` — user-level tunnel unit.
- `scripts/run-hermes-gateway-mcp` — protected-env launcher for the stdio adapter.
- `scripts/run-hermes-chatgpt-tunnel` — protected-env launcher for the tunnel.
- `scripts/smoke-test` — controlled Gateway lifecycle smoke test.
- `tests/test_mcp_contract.py` — MCP and Hermes Runs API contract tests.
