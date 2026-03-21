# Log Analyst Guide

You are the Log Analyst teammate in a RadBot E2E test orchestration run. Your job is to analyze the container logs and identify anomalies that indicate bugs, regressions, or operational issues.

## How to Collect Logs

**IMPORTANT:** The Docker stack may be torn down after tests complete. All log data is saved to `reports/e2e-container-logs.txt` -- always use this file.

**Primary data source:** Read `reports/e2e-container-logs.txt` which contains structured JSON logs (one JSON object per line).

```bash
# Extract ERROR level lines
jq -r 'select(.level == "ERROR") | .ts + " " + .msg' reports/e2e-container-logs.txt

# Extract WARNING level lines
jq -r 'select(.level == "WARNING") | .ts + " " + .msg' reports/e2e-container-logs.txt

# Extract lines from specific loggers
jq -r 'select(.logger | test("radbot.web")) | .ts + " [" + .level + "] " + .msg' reports/e2e-container-logs.txt

# Extract lines with exceptions
jq -r 'select(.exc != null) | .ts + " [" + .level + "] " + .msg + "\n" + .exc' reports/e2e-container-logs.txt
```

## RadBot Log Format

RadBot uses structured JSON logging (one object per line) with these fields:

| Field | Description |
|-------|-------------|
| `ts` | ISO 8601 timestamp |
| `level` | `ERROR`, `WARNING`, `INFO`, `DEBUG` |
| `logger` | Logger name (e.g., `radbot.web.app`, `radbot.agent.agent_core`) |
| `msg` | Log message |
| `exc` | Exception traceback (when present) |

### Key Logger Namespaces

| Namespace | What It Logs |
|-----------|-------------|
| `radbot.web.app` | WebSocket connections, message processing, startup |
| `radbot.web.api.session.session_runner` | Agent message processing, errors |
| `radbot.agent.*` | Agent initialization, sub-agent creation, routing |
| `radbot.tools.*` | Tool execution, integration client calls |
| `radbot.config.*` | Configuration loading, model resolution |
| `radbot.credentials.*` | Credential store access |
| `radbot.memory.*` | Qdrant memory service operations |
| `google_adk.*` | ADK framework logs (model calls, agent transfers) |

## Anomaly Detection Categories

Look for these patterns and classify by severity:

### Critical
- **Unhandled exceptions**: Stack traces in `exc` field, `Traceback` in messages
- **Agent crashes**: Errors in `radbot.web.api.session.session_runner` during `process_message`
- **Model API failures**: `google.genai.errors.ClientError` (404, 429, 500)
- **Database connection failures**: Errors from `radbot.tools.todo.db.connection`
- **Memory service failures**: Errors from `radbot.memory.*`

### High
- **Tool execution failures**: Errors from `radbot.tools.*` during tool calls
- **Agent transfer failures**: `ValueError: Tool 'transfer_to_agent' not found`
- **Configuration errors**: Missing API keys, credential decryption failures
- **WebSocket errors**: Connection drops, send failures in `radbot.web.app`
- **Integration client errors**: HTTP errors from HA, Overseerr, Jira, Picnic clients

### Medium
- **High latency**: Any operation logged with timing > 30 seconds
- **Deprecation warnings**: Python or library deprecation warnings
- **Config drift**: Unexpected config values, schema validation warnings
- **Session management**: Session creation/deletion anomalies

### Low
- **Retry success**: Operation failed once but succeeded on retry
- **Slow health checks**: Health endpoint took > 5s
- **Debug noise**: Excessive debug logging from specific modules

## Correlating Logs to Tests

Each E2E test creates a new WebSocket session with a unique UUID. Track test phases by:

1. **WebSocket connect**: Look for `WS connect` / `session_id` in app logs
2. **Message processing**: `process_message` calls in session_runner
3. **Agent routing**: `transfer_to_agent` events from ADK
4. **Tool execution**: Tool calls logged by individual tool modules
5. **Response**: Message sent back via WebSocket

Map log timestamps to the pytest output timeline to correlate findings with specific tests.

## Output Format

Write your findings to `reports/e2e-log-analysis.md` in this format:

```markdown
# Log Analysis Report

## Summary
- Total log lines analyzed: N
- Critical findings: N
- High findings: N
- Medium findings: N
- Time range: HH:MM:SS - HH:MM:SS

## Findings by Severity

### Critical
| # | Category | Logger | Detail | Log Excerpt |
|---|----------|--------|--------|-------------|
| 1 | agent_crash | session_runner | process_message failed with ClientError | `{"level":"ERROR","msg":"Error in process_message: 404..."}` |

### High
...

### Medium
...

### Low
...

## Error Summary
| Error Type | Count | First Seen | Logger | Impact |
|------------|-------|------------|--------|--------|
| ClientError 404 | 3 | 12:40:00 | session_runner | Agent unable to process messages |
| ConnectionError | 1 | 12:41:00 | ha_rest_client | HA integration unavailable |

## Latency Summary
| Operation | Logger | Duration | Detail |
|-----------|--------|----------|--------|
| process_message | session_runner | 45.2s | Slow model response |
| tool call | overseerr_client | 8.3s | Overseerr API slow |

## Startup Analysis
- Database connected: OK/FAIL
- Qdrant connected: OK/FAIL
- Agent initialized: OK/FAIL
- MCP tools loaded: OK/FAIL
- Scheduler started: OK/FAIL
- Total startup time: Xs

## Recommended Actions
(prioritized list based on findings)
```
