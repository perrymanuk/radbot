---
name: e2e-test
description: Run RadBot E2E tests with parallel log analysis, performance review, and test coverage analysis using agent teams
disable-model-invocation: true
user-invocable: true
---

# E2E Test Orchestration with Agent Teams

Run RadBot E2E tests against a Docker compose stack with three agent teammates providing deep analysis of logs, performance, and test coverage gaps.

## Argument Parsing

Parse the user's invocation to determine which tests to run:

- `/e2e-test` -- run ALL E2E tests
- `/e2e-test health` -- run tests matching "health" (`-k health`)
- `/e2e-test overseerr ha` -- run tests matching overseerr or ha
- `/e2e-test test_integration_overseerr.py` -- run a specific test file
- `/e2e-test --run-writes` -- run all tests including ones that mutate external systems

Set `$TEST_FILTER` based on the argument:
- No args: `tests/e2e/`
- Keywords: `tests/e2e/ -k "health or overseerr"`
- Filename: `tests/e2e/$FILENAME`
- `--run-writes` can be combined with any of the above

## Pre-flight Checks

Before running anything, verify:

1. **Docker running**: `docker info > /dev/null 2>&1`
2. **`.env` file exists**: `test -f .env`
3. **Required env vars set**: Check `.env` contains `RADBOT_ADMIN_TOKEN`, `GOOGLE_API_KEY` or `RADBOT_CREDENTIAL_KEY`
4. **Reports directory**: `mkdir -p reports/e2e-analysis-history`

If any check fails, report clearly and stop.

## Orchestration Flow

### 1. Start the Docker Stack

The Docker compose stack provides PostgreSQL, Qdrant, and the RadBot service. Start it
and wait for health checks:

```bash
docker compose up -d --build --wait
```

### 2. Seed Credentials

Seed the Docker stack with credentials from the local dev database:

```bash
RADBOT_ENV=dev uv run python scripts/seed_docker_credentials.py \
  --target-url http://localhost:${RADBOT_EXPOSED_PORT:-8001} \
  --admin-token $(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
  --rewrite-localhost || true
```

### 3. Restart RadBot to Pick Up Credentials

The radbot container initializes the agent (including API key setup) at startup,
before credentials are seeded. Restart it so it picks up the seeded credentials:

```bash
docker compose restart radbot
```

Then poll the health endpoint until ready (timeout after 60s):

```bash
for i in $(seq 1 12); do
  curl -sf http://localhost:${RADBOT_EXPOSED_PORT:-8001}/health && break
  sleep 5
done
```

### 4. Run the Tests

Run the tests in the foreground and wait for completion. Capture output and generate JUnit XML.

```bash
RADBOT_TEST_URL=http://localhost:${RADBOT_EXPOSED_PORT:-8001} \
RADBOT_ADMIN_TOKEN=$(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
uv run --extra dev pytest $TEST_FILTER -v --timeout=120 \
  --junit-xml=reports/e2e-junit.xml 2>&1 | tee reports/e2e-pytest-output.txt
```

Use a 600s timeout. This runs in the FOREGROUND -- wait for it to complete.

Report the pytest results summary to the user before proceeding to analysis.

### 5. Collect Container Logs

Save the container logs for analysis before teardown:

```bash
docker compose logs --no-color --no-log-prefix radbot > reports/e2e-container-logs.txt 2>&1

# Create timestamped copy for history
cp reports/e2e-container-logs.txt "reports/e2e-container-logs-$(date +%Y%m%d-%H%M%S).txt"
```

### 6. Create Team and Spawn Teammates (after tests complete)

Only after the test run finishes, create the team and spawn all analysis teammates.
Since all artifacts are already available, no teammate needs to poll for files.

```
TeamCreate(team_name="e2e-analysis", description="RadBot E2E test analysis team")
```

Spawn teammates 1-2 in parallel (no dependencies). Teammate 3 depends on both.

**Teammate 1: Log Analyst**
- `Agent(name="log-analyst", team_name="e2e-analysis", run_in_background=true, ...)`
- Prompt: "Analyze the RadBot E2E container logs for anomalies. Read `.claude/skills/e2e-test/log-analysis-guide.md` for detailed instructions. The test run is COMPLETE -- all artifacts are ready. Read the saved log file `reports/e2e-container-logs.txt` (structured JSON logs). Write your findings to `reports/e2e-log-analysis.md`."

**Teammate 2: Performance Reviewer**
- `Agent(name="perf-reviewer", team_name="e2e-analysis", run_in_background=true, ...)`
- Prompt: "Review performance of both the RadBot application and the E2E test suite. Read `.claude/skills/e2e-test/performance-review-guide.md` for detailed instructions. The test run is COMPLETE -- `reports/e2e-pytest-output.txt` and `reports/e2e-junit.xml` are ready. Read `reports/e2e-container-logs.txt` for runtime timing data. Compare against previous runs in `reports/e2e-analysis-history/`. Write findings to `reports/e2e-performance-review.md`."

**Teammate 3: Test Coverage Reviewer** (depends on teammates 1 and 2)
- `Agent(name="test-coverage", team_name="e2e-analysis", run_in_background=true, ...)`
- Prompt: "Analyze E2E run findings and identify test coverage gaps. Read `.claude/skills/e2e-test/test-coverage-guide.md` for detailed instructions. The test run is COMPLETE and `reports/e2e-pytest-output.txt` is ready. Wait for BOTH of these teammate reports to exist (poll every 20s): `reports/e2e-log-analysis.md`, `reports/e2e-performance-review.md`. Then cross-reference findings against existing tests in `tests/` to identify missing unit tests, missing E2E scenarios, and assertion gaps. Propose concrete test code for each gap. Write findings to `reports/e2e-test-coverage.md`."

### 7. Wait for Teammates

Wait for all three teammates to finish and write their report files.
You will be notified automatically when each teammate completes.

### 8. Extract Per-Test Durations

Parse `reports/e2e-junit.xml` to extract per-test durations:

```bash
uv run python -c "
import xml.etree.ElementTree as ET
tree = ET.parse('reports/e2e-junit.xml')
for tc in tree.iter('testcase'):
    print(f\"{tc.get('name')}: {float(tc.get('time', 0)):.1f}s\")
"
```

### 9. Collect Findings and Generate Unified Report

Read the three teammate reports:
- `reports/e2e-log-analysis.md`
- `reports/e2e-performance-review.md`
- `reports/e2e-test-coverage.md`

Generate a unified report combining all findings.

**Markdown report** -- `reports/e2e-analysis-{YYYYMMDD-HHMMSS}.md`:

```markdown
# E2E Test Analysis Report - {timestamp}

## Summary

| Test | Pytest | Duration | Log Findings | Perf Findings | Coverage Gaps |
|------|--------|----------|-------------|---------------|---------------|
| test_health | PASSED | 0.3s | 0 findings | 0 bottlenecks | 0 gaps |
| test_agent_chat | PASSED | 45.2s | 1 medium | 1 bottleneck | 1 gap |

## Delta from Previous Run
(Compare against most recent file in reports/e2e-analysis-history/)

- New issues: ...
- Resolved issues: ...

## Per-Test Details

### Test: test_health
#### Pytest Result: PASSED (0.3s)
#### Log Analysis
(findings from log analyst)
#### Performance
(findings from performance reviewer)
#### Test Coverage Gaps
(gaps identified by coverage reviewer)

## Recommended Actions
(prioritized list based on severity)
```

**JSON report** -- `reports/e2e-analysis-{YYYYMMDD-HHMMSS}.json`:

```json
{
  "timestamp": "2026-03-21T10:30:00Z",
  "tests": [
    {
      "id": "test_health",
      "name": "health_returns_ok",
      "pytest_result": "passed",
      "duration_seconds": 0.3,
      "log_findings": [],
      "perf_findings": [],
      "coverage_gaps": []
    }
  ],
  "summary": {
    "total": 1,
    "passed": 1,
    "failed": 0,
    "skipped": 0,
    "critical_findings": 0,
    "warnings": 0
  }
}
```

### 10. Persist Historical Summary

Save a compact run summary to `reports/e2e-analysis-history/run-{YYYYMMDD-HHMMSS}.json`:

```json
{
  "timestamp": "...",
  "total_duration_seconds": 120.5,
  "test_count": 140,
  "passed": 135,
  "failed": 0,
  "skipped": 5,
  "findings": {"critical": 0, "high": 0, "medium": 1, "low": 0},
  "tests": {
    "test_health_returns_ok": {"result": "passed", "duration_seconds": 0.3},
    "test_agent_chat_greeting": {"result": "passed", "duration_seconds": 45.2}
  }
}
```

### 11. Teardown

After reports are generated:

1. Clean up the team using `TeamDelete`
2. Tear down the Docker stack:

```bash
docker compose down --volumes --remove-orphans 2>/dev/null || true
```

Print a summary of where reports were written.

## Important Notes

- The compose file is `docker-compose.yml` (not a separate e2e file)
- The RadBot health endpoint is `http://localhost:${RADBOT_EXPOSED_PORT:-8001}/health`
- The admin status endpoint is `http://localhost:${RADBOT_EXPOSED_PORT:-8001}/admin/api/status`
- Container logs are structured JSON (one JSON object per line)
- RadBot uses Python's standard logging with structured JSON format (see CLAUDE.md Logging Standard)
- Tests use service availability auto-skip markers (`requires_gemini`, `requires_ha`, etc.)
- Tests marked `writes_external` are skipped unless `--run-writes` is passed
- Teammates are spawned AFTER the test run completes, so all artifacts are fully written before analysis begins
- Test coverage reviewer runs last (waits for log analysis and performance review)
