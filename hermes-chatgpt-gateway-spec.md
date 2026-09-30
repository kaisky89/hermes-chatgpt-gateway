## Problem Statement

The user wants to connect a locally running Hermes Agent on a Raspberry Pi to ChatGPT so that ChatGPT can act as the high-level orchestrator while Hermes performs local execution.

Hermes already provides much of the required agent infrastructure: a long-running Gateway, a Runs API, access to local tools and skills, and its own subagent/delegation capabilities. The missing piece is a clean integration layer that allows ChatGPT to start, observe, steer, and stop Hermes runs without exposing the Raspberry Pi directly to the public internet or duplicating Hermes functionality.

The desired interaction should feel natural from ChatGPT. The user should be able to ask ChatGPT to perform a task, ChatGPT should decide when Hermes is useful, delegate the task to Hermes, allow Hermes to work asynchronously, monitor the run until it reaches a meaningful state, and then continue processing the result.

The solution should preserve the existing Hermes Gateway setup and existing messaging integrations such as Telegram, Discord, or Slack. ChatGPT should become an additional interface to the same Hermes system rather than replacing or bypassing the existing messaging layer.

The integration should remain intentionally small. It should not create another agent framework, scheduler, memory implementation, or orchestration engine. Those responsibilities already belong either to ChatGPT Work or Hermes.

---

## Solution

Build a lightweight MCP server that acts as a protocol adapter between ChatGPT and the existing Hermes Gateway Runs API.

The overall architecture will be:

```text
ChatGPT / ChatGPT Work
        │
        │ MCP
        ▼
Hermes Gateway MCP Adapter
        │
        │ HTTP
        ▼
Hermes Gateway
        │
        ▼
Hermes Agent
        │
        ├── Local tools
        ├── Skills
        ├── Files
        ├── Terminal
        ├── Browser / web tools
        └── Hermes subagents
```

Existing messaging integrations remain parallel entry points:

```text
Telegram ──┐
Discord ───┤
Slack ─────┤
           ▼
     Hermes Gateway
           ▲
           │
ChatGPT → MCP Adapter
```

The MCP adapter is therefore conceptually another Hermes connector, similar to Telegram or Discord, but optimized for programmatic agent orchestration instead of human messaging.

The first version exposes only four primary operations:

- Start a Hermes task.
- Get the current state and result of a Hermes task.
- Steer an active Hermes task with additional instructions.
- Stop an active Hermes task.

ChatGPT Work is the preferred orchestration environment for long-running jobs. It can start a Hermes run, retain the returned run identifier, repeatedly check the run state as part of a longer Work task, and continue once Hermes reports completion, failure, or another terminal/intervention state.

The adapter itself should remain stateless wherever possible. Hermes remains the source of truth for run state.

The Raspberry Pi should not require inbound router port forwarding. The MCP adapter should be exposed to ChatGPT using OpenAI's private/secure MCP connectivity mechanism where available.

---

## User Stories

1. As a ChatGPT user, I want to ask ChatGPT to delegate work to my local Hermes Agent, so that local capabilities can participate in my normal ChatGPT workflows.

2. As a ChatGPT user, I want ChatGPT to remain the primary conversational interface, so that I do not need to switch to Telegram, SSH, or another Hermes interface for every task.

3. As a ChatGPT user, I want ChatGPT to decide when Hermes is useful, so that I do not have to manually invoke a special Hermes command for every request.

4. As a ChatGPT user, I want to explicitly ask ChatGPT to use Hermes when desired, so that I can override automatic orchestration when I know local execution is appropriate.

5. As a ChatGPT user, I want Hermes to run on my Raspberry Pi, so that local tools, files, services, and hardware remain accessible to the agent.

6. As a ChatGPT user, I want the integration to reuse the existing Hermes Gateway, so that I do not need to run a second independent Hermes installation.

7. As a Hermes user, I want Telegram, Discord, Slack, and other existing Hermes integrations to continue working, so that adding ChatGPT does not break my existing workflows.

8. As a Hermes user, I want ChatGPT to act as another entry point into Hermes, so that all interfaces reach the same underlying agent system.

9. As a user, I want ChatGPT to start a Hermes task with a natural-language objective, so that Hermes can decide how to execute the task internally.

10. As a user, I want the start operation to return quickly with a run identifier, so that ChatGPT does not need to keep a long network request open while Hermes works.

11. As a user, I want Hermes runs to continue after the initial MCP call returns, so that long-running tasks are supported.

12. As a user, I want ChatGPT to retrieve the state of a Hermes run using its run identifier, so that it can monitor asynchronous execution.

13. As a user, I want ChatGPT to determine whether a Hermes task is queued, running, completed, failed, stopped, or waiting for input, so that it can react appropriately.

14. As a user, I want ChatGPT to retrieve the final Hermes result once a run completes, so that the result can be incorporated into the ongoing conversation.

15. As a user, I want ChatGPT Work to monitor long-running Hermes tasks, so that I do not have to repeatedly ask whether Hermes has finished.

16. As a user, I want ChatGPT Work to retain the Hermes run identifier during a long-running task, so that all later status checks reference the correct run.

17. As a user, I want ChatGPT Work to poll Hermes until a meaningful state is reached, so that asynchronous Hermes work can be handled automatically.

18. As a user, I want polling to stop when Hermes completes successfully, so that unnecessary status requests are avoided.

19. As a user, I want polling to stop when Hermes fails, so that ChatGPT can report or handle the failure.

20. As a user, I want polling to stop when Hermes is explicitly stopped, so that ChatGPT does not continue waiting for an abandoned task.

21. As a user, I want ChatGPT to recognize when Hermes requires approval or user intervention, so that potentially sensitive actions do not proceed silently.

22. As a user, I want ChatGPT to be able to provide additional instructions to a running Hermes task, so that I can refine a task without restarting it.

23. As a user, I want ChatGPT to steer an active Hermes run based on newly discovered information, so that orchestration can remain adaptive.

24. As a user, I want ChatGPT to stop a Hermes task, so that unnecessary, incorrect, or unsafe runs can be cancelled.

25. As a user, I want a stop request to be associated with a specific run identifier, so that unrelated Hermes tasks remain unaffected.

26. As a user, I want multiple Hermes runs to coexist, so that different ChatGPT or Work tasks can use Hermes independently.

27. As a user, I want every run to have a unique stable identifier, so that concurrent work can be tracked reliably.

28. As a user, I want the MCP adapter to avoid maintaining its own duplicate job database, so that Hermes remains the authoritative source of run state.

29. As a user, I want Hermes to retain responsibility for choosing its own local tools, so that ChatGPT does not need to understand every local capability.

30. As a user, I want Hermes to retain responsibility for invoking its own skills, so that existing Hermes configuration is reusable.

31. As a user, I want Hermes to be able to launch its own subagents, so that complex local tasks can be decomposed without ChatGPT managing every subtask.

32. As a user, I want ChatGPT to delegate a high-level objective rather than micromanaging Hermes, so that communication between ChatGPT and the Raspberry Pi remains efficient.

33. As a user, I want Hermes subagent implementation details to remain hidden from ChatGPT unless relevant, so that the integration stays loosely coupled.

34. As a user, I want Hermes to return a concise task result to ChatGPT, so that ChatGPT can decide what to do next.

35. As a user, I want ChatGPT to be able to reason over a Hermes result, so that local execution can be combined with ChatGPT's broader orchestration.

36. As a user, I want ChatGPT to be able to launch another Hermes task based on the result of a previous task, so that multi-stage workflows are possible.

37. As a user, I want ChatGPT to be able to steer a run rather than always starting another run, so that the current Hermes context can be preserved where appropriate.

38. As a user, I want the adapter to expose only a small, well-defined tool surface, so that ChatGPT has predictable interactions with Hermes.

39. As a user, I want MCP tool names and descriptions to clearly communicate their purpose to ChatGPT, so that the model selects the correct operation.

40. As a user, I want task parameters to be validated before requests are sent to Hermes, so that malformed MCP calls fail clearly.

41. As a user, I want Hermes API errors to be translated into useful MCP errors, so that ChatGPT can understand what went wrong.

42. As a user, I want network failures between the adapter and Hermes to be reported distinctly from Hermes agent failures, so that troubleshooting is easier.

43. As a user, I want an unknown run identifier to produce a clear response, so that stale or incorrect references can be diagnosed.

44. As a user, I want attempts to steer a completed task to fail clearly, so that invalid task transitions are not silently ignored.

45. As a user, I want attempts to stop an already completed task to return a sensible result, so that repeated operations are safe and understandable.

46. As a user, I want the adapter to preserve the Hermes Gateway's native run semantics, so that the wrapper does not introduce surprising behavior.

47. As a user, I want the adapter to support Hermes authentication if the Gateway requires it, so that the local API is not assumed to be unauthenticated.

48. As a user, I want Hermes credentials to remain on the Raspberry Pi, so that they are not unnecessarily exposed to ChatGPT.

49. As a user, I want secrets to be supplied through environment or service configuration, so that credentials are not hard-coded.

50. As a user, I want the MCP adapter to communicate with Hermes over localhost by default, so that the Gateway itself does not need to be exposed externally.

51. As a user, I want the Raspberry Pi to initiate secure outbound connectivity where possible, so that I do not need to open inbound router ports.

52. As a user, I want the MCP adapter to be separately deployable from Hermes, so that Hermes itself does not need to be patched.

53. As a Hermes user, I want Hermes upgrades to have minimal impact on the adapter, so that maintaining the integration remains simple.

54. As a developer, I want the adapter to target the documented Hermes Gateway API rather than internal Hermes implementation details, so that the integration is more stable.

55. As a developer, I want the adapter to contain no LLM logic, so that there is a clear separation between orchestration and protocol translation.

56. As a developer, I want the adapter to contain no subagent implementation, so that Hermes remains responsible for its own agent hierarchy.

57. As a developer, I want the adapter to contain no general-purpose scheduler, so that ChatGPT Work remains responsible for high-level orchestration.

58. As a developer, I want the adapter to contain no polling daemon of its own in the initial version, so that unnecessary infrastructure is avoided.

59. As a developer, I want `start_task` to map closely to the Hermes run creation API, so that behavior remains transparent.

60. As a developer, I want `get_task` to map closely to the Hermes run retrieval API, so that run state can be inspected without transformation loss.

61. As a developer, I want `steer_task` to map closely to Hermes' run steering operation, so that an active run can receive additional instructions.

62. As a developer, I want `stop_task` to map closely to Hermes' stop operation, so that cancellation semantics remain owned by Hermes.

63. As a developer, I want the MCP responses to expose the Hermes run ID, so that ChatGPT can use it in later calls.

64. As a developer, I want the MCP response to expose a normalized run status, so that ChatGPT does not need to interpret arbitrary text.

65. As a developer, I want the original Hermes status to remain available where useful, so that new Hermes states can still be diagnosed.

66. As a developer, I want completed tasks to return their result in a structured field, so that ChatGPT can consume it predictably.

67. As a developer, I want failed tasks to expose a useful error summary, so that ChatGPT can either retry, explain the failure, or change strategy.

68. As a developer, I want timestamps to be exposed when available, so that long-running tasks can be diagnosed.

69. As a developer, I want the adapter to enforce reasonable request timeouts, so that a broken Hermes Gateway does not indefinitely block an MCP request.

70. As a developer, I want normal status requests to be short-lived HTTP operations, so that asynchronous execution does not depend on long-lived connections.

71. As a developer, I want the first implementation to work without SSE streaming, so that V1 remains simple.

72. As a developer, I want the design to leave room for Hermes run events later, so that polling can eventually be optimized.

73. As a developer, I want the design to leave room for approval handling later, so that Hermes actions requiring explicit approval can be integrated.

74. As a developer, I want approval support to build on Hermes' native approval state rather than inventing a second approval model.

75. As a developer, I want the design to leave room for listing active runs later, so that debugging and orchestration can become more convenient.

76. As a user, I want ChatGPT to tell me when Hermes is still working if I explicitly ask during a run, so that task progress is understandable.

77. As a user, I want ChatGPT to tell me when Hermes has failed rather than pretending the task completed, so that agent failures are transparent.

78. As a user, I want ChatGPT to distinguish Hermes failure from adapter failure, so that I know where troubleshooting is required.

79. As a user, I want ChatGPT to distinguish adapter failure from secure tunnel failure, so that connectivity issues can be identified.

80. As a user, I want the Hermes Gateway to remain usable locally if the ChatGPT integration is unavailable, so that the new integration does not become a single point of failure.

81. As a user, I want Telegram and other Hermes interfaces to continue working if the MCP adapter crashes, so that the connector remains isolated.

82. As a user, I want the MCP adapter to be restartable independently, so that operational maintenance is simple.

83. As a user, I want the adapter to produce useful logs, so that failed requests can be diagnosed on the Raspberry Pi.

84. As a user, I want logs to avoid exposing secrets, so that diagnostics do not weaken security.

85. As a developer, I want request and run identifiers to appear in logs where appropriate, so that a ChatGPT tool call can be correlated with a Hermes run.

86. As a developer, I want the adapter to report when Hermes is unreachable, so that health issues are immediately visible.

87. As a developer, I want the adapter to fail startup or report unhealthy configuration when its required Hermes URL is invalid, so that configuration mistakes are obvious.

88. As a user, I want the adapter configuration to allow a custom Hermes Gateway URL, so that the architecture is not tied exclusively to localhost.

89. As a developer, I want localhost to be the default Hermes endpoint, so that the secure configuration is also the easiest configuration.

90. As a developer, I want the adapter implementation to be small enough to audit, so that I can understand exactly what ChatGPT is allowed to do on my Pi.

91. As a user, I want the exposed MCP operations to be intentionally limited, so that ChatGPT does not automatically gain unrestricted arbitrary access to my Raspberry Pi.

92. As a user, I want local privilege boundaries to remain controlled by Hermes, so that the MCP adapter itself does not need system-level permissions.

93. As a user, I want Hermes to decide whether a task requires shell access or another privileged tool, so that existing Hermes safety controls remain effective.

94. As a user, I want ChatGPT Work to be able to combine Hermes with other connected tools, so that workflows can span cloud services and local infrastructure.

95. As a user, I want ChatGPT Work to be able to perform work before starting Hermes, so that it can gather or prepare relevant context.

96. As a user, I want ChatGPT Work to be able to perform work while Hermes is processing, when useful, so that time is not unnecessarily wasted.

97. As a user, I want ChatGPT Work to continue with additional steps after Hermes finishes, so that Hermes can participate in larger workflows.

98. As a user, I want ChatGPT Work to decide that no further Hermes polling is necessary once a terminal state is reached, so that workflows terminate cleanly.

99. As a user, I want normal ChatGPT conversations to still be able to use the adapter for short interactions, so that Work is not mandatory for every Hermes request.

100. As a normal ChatGPT user, I want a started Hermes run to persist even after the conversational turn ends, so that I can manually query it later.

101. As a normal ChatGPT user, I want to be able to ask "what happened with the Hermes task?" in a later turn, so that asynchronous jobs remain usable outside Work.

102. As a normal ChatGPT user, I understand that the normal chat should not be assumed to autonomously wake itself later, so that asynchronous expectations remain correct.

103. As a Work user, I want long-running orchestration to be handled by Work rather than by the MCP adapter, so that the adapter stays simple.

104. As a developer, I want the integration to avoid relying on undocumented arbitrary MCP-to-ChatGPT wake-up callbacks, so that the system depends on supported behavior.

105. As a developer, I want future event-based integration to be additive, so that V1 does not need to be redesigned when better wake-up support becomes available.

106. As a user, I want a future version to optionally react to Hermes run events instead of polling, so that status monitoring becomes more efficient.

107. As a user, I want future support for an approval state, so that Hermes can pause before consequential local actions.

108. As a user, I want future support for approving or rejecting such actions through ChatGPT, so that the entire workflow can remain inside one interface.

109. As a user, I want future support for listing active Hermes tasks, so that I can inspect several parallel jobs.

110. As a user, I want future support for retrieving run history if Hermes exposes it appropriately, so that prior delegated work can be inspected.

111. As a developer, I want future capabilities to remain thin mappings over Hermes capabilities, so that the adapter does not gradually become another orchestration platform.

112. As a developer, I want version compatibility failures with the Hermes Gateway to be clear, so that API changes are easy to detect.

113. As a developer, I want the adapter to be suitable for open sourcing, so that others with Hermes and ChatGPT can reuse the integration.

114. As an open-source user, I want installation and configuration to be minimal, so that I can deploy the adapter next to an existing Hermes Gateway quickly.

115. As an open-source user, I want the project documentation to explain the architecture and trust boundaries, so that I understand what is exposed.

116. As an open-source user, I want the documentation to clearly separate ChatGPT, MCP adapter, Hermes Gateway, Hermes Agent, and Hermes subagents, so that the different layers are easy to understand.

117. As a maintainer, I want the project scope to remain explicitly narrow, so that unrelated feature requests do not turn the adapter into a general Hermes UI.

118. As a maintainer, I want behavior to be defined by externally visible MCP contracts, so that implementation details can evolve without breaking users.

119. As a maintainer, I want comprehensive contract tests around the Hermes API boundary, so that upstream Hermes changes can be detected quickly.

120. As a user, I want the final experience to feel like "ChatGPT can ask my Raspberry Pi's Hermes Agent to do something and continue once it is done," so that the underlying technical complexity remains largely invisible.

---

## Implementation Decisions

- A standalone **Hermes Gateway MCP Adapter** will be built.

- The adapter will be an additional integration alongside existing Hermes messaging integrations. It will not replace Telegram, Discord, Slack, or other Gateway inputs.

- The adapter will communicate with the existing Hermes Gateway through its documented programmatic HTTP API.

- The Hermes Gateway will remain responsible for starting and managing actual `AIAgent` runs.

- Hermes will remain responsible for all local execution logic, including shell usage, file access, skills, browser/web capabilities, memory, and subagent delegation.

- ChatGPT will remain responsible for top-level interaction and orchestration.

- ChatGPT Work will be the preferred environment for tasks that need to remain active while Hermes performs long-running asynchronous work.

- Normal ChatGPT conversations may also invoke the integration, but normal chat must not be treated as a guaranteed autonomous background scheduler after a turn has ended.

- V1 will use an **asynchronous job model**. Starting a Hermes task returns a run ID rather than waiting for the entire task to complete.

- V1 will expose four MCP operations:
  - `hermes_start_task`
  - `hermes_get_task`
  - `hermes_steer_task`
  - `hermes_stop_task`

- `hermes_start_task` will accept at minimum a task prompt/objective.

- `hermes_start_task` will create a Hermes run and return the Hermes run ID and initial state.

- `hermes_get_task` will accept a Hermes run ID and return its current state.

- When the run has completed, `hermes_get_task` will also expose the resulting Hermes output.

- `hermes_steer_task` will accept a run ID and additional instruction and forward that instruction to the active Hermes run.

- `hermes_stop_task` will accept a run ID and request cancellation through the Hermes Gateway.

- The adapter will preserve Hermes' run identifier rather than generating a parallel job identifier unless a future Hermes limitation requires otherwise.

- The adapter will normalize run states enough for ChatGPT to reliably distinguish at least:
  - pending/queued where applicable,
  - running,
  - completed,
  - failed,
  - stopped/cancelled,
  - waiting for approval or intervention where supported.

- The original Hermes state may additionally be exposed for forward compatibility and debugging.

- Hermes remains the system of record for run state.

- The adapter will not persist its own run database in V1.

- The adapter will not implement its own job worker.

- The adapter will not implement its own agent.

- The adapter will not implement its own subagent system.

- The adapter will not implement its own memory system.

- The adapter will not implement a scheduling system.

- The adapter will not implement long-running polling internally in V1.

- For Work-based orchestration, ChatGPT Work will call `hermes_get_task` repeatedly when it needs to monitor a task.

- Polling cadence is intentionally not part of the MCP API contract. Work may determine when another status check is appropriate.

- The system will not depend on the assumption that ChatGPT can be arbitrarily awakened by an inbound MCP event after a normal chat turn has ended.

- V1 will therefore use request/response MCP operations rather than requiring server-initiated task completion callbacks.

- Hermes' existing event/SSE capabilities may be used internally in a later version but are not required for V1.

- Future event support should be additive and should not change the meaning of the four core MCP tools.

- Future approval support may introduce explicit operations such as approving or rejecting a Hermes-requested action.

- Approval state will be sourced from Hermes rather than implemented independently.

- Future functionality may include listing active runs, but this is not required by V1.

- The adapter should be deployable on the same Raspberry Pi as Hermes.

- The default Hermes Gateway address should point to loopback/local host rather than a publicly reachable endpoint.

- The Hermes Gateway itself should not need to be publicly exposed for ChatGPT integration.

- External ChatGPT-to-adapter connectivity should use the supported private MCP connectivity/tunnel mechanism where available.

- No router port forwarding should be required by the intended deployment model.

- The adapter should accept configuration for the Hermes Gateway base URL.

- The adapter should support whatever authentication mechanism the Gateway uses when authentication is configured.

- Hermes credentials should remain server-side on the Raspberry Pi and should not be part of normal MCP tool parameters.

- Configuration secrets must not be hard-coded.

- MCP operations should have explicit schemas with constrained, descriptive inputs.

- Tool descriptions should be written for effective LLM tool selection, not just for human API consumers.

- Error responses should distinguish:
  - invalid tool input,
  - unknown Hermes run,
  - invalid run state,
  - Gateway authentication failure,
  - Gateway connectivity failure,
  - Hermes agent/run failure,
  - internal adapter failure.

- The adapter should use bounded request timeouts for communication with the Hermes Gateway.

- Starting a task should not wait for Hermes completion.

- Status retrieval should be a short-lived call.

- Steering should only be accepted when Hermes supports steering in the current run state.

- Stop behavior should follow Hermes semantics rather than inventing separate cancellation semantics.

- Idempotent or repeated terminal-state operations should produce clear, predictable results.

- The adapter should use structured logging.

- Logs should allow correlation by Hermes run ID.

- Logs must avoid printing API keys, credentials, or sensitive task payloads unnecessarily.

- The adapter should not require elevated operating-system privileges merely to proxy the Hermes API.

- Existing Hermes permissions and local tool restrictions remain the security boundary for what the Hermes Agent can actually do.

- The project should be small and auditable enough that the user can reasonably inspect what ChatGPT is being given access to.

- The implementation should depend on documented Hermes Gateway interfaces rather than importing private Hermes internals.

- The adapter should be usable independently of ChatGPT Work; Work is an orchestration enhancement rather than part of the adapter runtime.

- The MCP contract should remain valid for other MCP-capable clients where practical.

- The project should be suitable for open-source release.

---

## Testing Decisions

Tests should focus on **externally observable behavior**, not internal implementation details. Tests should verify what an MCP client receives and what the Hermes Gateway is asked to do, rather than asserting private function structure, internal helper usage, or specific implementation patterns.

The MCP surface should be treated as the primary public contract.

The Hermes Gateway HTTP API should be treated as the primary downstream contract.

Tests should cover the start-task flow. Given a valid task request and a Hermes Gateway that accepts the run, the MCP operation should return a valid run identifier and initial state.

Tests should cover asynchronous behavior. `hermes_start_task` must return without waiting for a simulated long-running Hermes job to complete.

Tests should cover status retrieval for each important state:
- running,
- completed,
- failed,
- stopped,
- waiting for approval/intervention where supported.

Tests should verify that a completed task returns its final result.

Tests should verify that a running task does not incorrectly expose itself as completed.

Tests should verify that a failed Hermes run is represented as a Hermes run failure rather than a transport error.

Tests should verify that an unreachable Hermes Gateway results in a connectivity error distinguishable from a failed agent run.

Tests should verify invalid and unknown run IDs.

Tests should verify steering an active task.

Tests should verify the adapter's behavior when Hermes rejects steering because the run is no longer active.

Tests should verify stopping an active task.

Tests should verify behavior when stopping a task that is already terminal.

Tests should verify authentication behavior when the Hermes Gateway requires credentials.

Tests should verify that credentials are not required as MCP tool inputs.

Tests should verify tool input validation, including missing prompts, missing run IDs, and invalid empty steering instructions.

Tests should verify that downstream HTTP status codes and Hermes error payloads are translated into stable MCP-facing errors.

Tests should verify request timeout behavior.

Tests should verify that multiple independent run IDs remain independent.

Tests should verify that a status lookup for one run can never return another run's result.

Tests should verify that no local persistent job state is required for a run started before an adapter restart, assuming Hermes still retains that run and exposes it through the Gateway.

Tests should verify that adapter restart does not inherently cancel Hermes runs.

Tests should verify that Hermes messaging integrations are not part of the MCP adapter's execution path.

Tests should verify that normal MCP calls do not require Telegram, Discord, or Slack to be configured.

Tests should verify that tool descriptions and schemas are discoverable through the MCP server and match the documented contract.

Tests should verify that sensitive configuration values are not exposed through MCP discovery responses.

Tests should verify that common failures do not leak secrets into returned error messages.

Where the codebase already contains HTTP client tests, MCP server contract tests, or tests using a mock external API server, those patterns should be reused as prior art. If this is a new standalone project with no existing test conventions, the tests should use a local fake/stub Hermes Gateway and exercise the MCP server through its public protocol surface.

An integration test suite should run the adapter against a controlled Hermes-compatible HTTP stub. A smaller optional end-to-end suite may run against a real Hermes Gateway when available, but the primary automated test suite should not depend on a live LLM, external model provider, or real network services.

No test should rely on Hermes producing a particular natural-language answer from an LLM. Tests should assert lifecycle and contract behavior rather than model output wording.

---

## Out of Scope

V1 will not replace or modify Hermes' Telegram, Discord, Slack, or other messaging integrations.

V1 will not route ChatGPT messages through Telegram or another messaging platform as a workaround.

V1 will not expose every Hermes capability directly as a separate MCP tool.

V1 will not expose raw arbitrary shell execution directly from the MCP adapter.

V1 will not expose the Raspberry Pi filesystem directly through this adapter.

V1 will not recreate Hermes' tool system.

V1 will not recreate Hermes skills.

V1 will not recreate Hermes memory.

V1 will not recreate Hermes subagents.

V1 will not implement a separate agent planner.

V1 will not implement a separate orchestration engine.

V1 will not include a persistent task database.

V1 will not contain its own background worker queue.

V1 will not implement fixed-interval polling on behalf of ChatGPT.

V1 will not guarantee that a normal ChatGPT conversation autonomously resumes after its turn has ended.

V1 will not depend on arbitrary inbound webhooks being able to wake a particular ChatGPT thread.

V1 will not require SSE/event streaming from Hermes.

V1 will not initially expose Hermes run event streams through MCP.

V1 will not initially implement interactive approval/rejection tools, although the architecture should allow them later.

V1 will not initially provide a task-management UI.

V1 will not initially provide run history browsing.

V1 will not initially provide a tool for listing all active Hermes runs unless implementation experience shows it is required for reliable orchestration.

V1 will not provide its own authentication system beyond the connectivity/authentication required for the MCP endpoint and the existing Hermes Gateway authentication.

V1 will not expose the Hermes Gateway itself directly to the public internet.

V1 will not require router port forwarding.

V1 will not make ChatGPT responsible for deciding which individual Hermes subagent should run. Hermes owns that level of orchestration.

V1 will not guarantee deterministic polling intervals inside ChatGPT Work.

V1 will not rely on undocumented ChatGPT product behavior.

---

## Further Notes

The central architectural principle is:

> **ChatGPT orchestrates; MCP translates; Hermes executes.**

The MCP adapter should remain deliberately boring. That is a feature rather than a limitation.

The intended responsibility split is:

```text
ChatGPT / Work
High-level goals, conversation, workflow orchestration
                │
                ▼
MCP Adapter
Protocol translation and narrow access boundary
                │
                ▼
Hermes Gateway
Run lifecycle management
                │
                ▼
Hermes Agent
Local execution and agent reasoning
                │
                ▼
Hermes subagents / tools / skills
Detailed execution
```

The preferred asynchronous workflow is:

```text
ChatGPT Work
     │
     ├── start_task()
     │       │
     │       └── run_id
     │
     ├── performs other orchestration if useful
     │
     ├── get_task(run_id)
     │       └── running
     │
     ├── get_task(run_id)
     │       └── running
     │
     ├── get_task(run_id)
     │       └── completed
     │
     └── consumes result and continues workflow
```

For a normal ChatGPT conversation, the same MCP contract remains useful, but the expected lifecycle is different:

```text
Turn 1:
ChatGPT → start_task() → run_id

Hermes continues independently.

Later turn:
User: "How did the Hermes task go?"
ChatGPT → get_task(run_id)
```

This distinction is important. The adapter does not need two architectures for Chat and Work. It needs one good asynchronous API. The orchestration environment determines how that API is used.

A later V2 can add approval support and possibly event-aware behavior:

```text
start_task
get_task
steer_task
stop_task

+ approve_action
+ reject_action
+ list_tasks
+ optional event integration
```

Those additions should only be introduced once the four-operation V1 has been proven reliable.

The key success criterion for V1 is simple:

> A user can tell ChatGPT Work to delegate a task to Hermes, Hermes can perform that task asynchronously on the Raspberry Pi using its normal tools and subagents, and ChatGPT Work can monitor the run and continue with the resulting output without requiring changes to the core Hermes agent architecture.