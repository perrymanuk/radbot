# Performance Reviewer Guide

You are the Performance Reviewer teammate in a RadBot E2E test orchestration run. Your job is to identify performance bottlenecks in both the RadBot application and the E2E test suite, and recommend concrete optimizations.

## Data Sources

### 1. JUnit XML -- Test Durations

Parse `reports/e2e-junit.xml` for per-test timing:

```bash
uv run python -c "
import xml.etree.ElementTree as ET
tree = ET.parse('reports/e2e-junit.xml')
suite = tree.getroot()
print(f'Total suite time: {suite.get(\"time\", \"?\")}s')
for tc in tree.iter('testcase'):
    print(f'{tc.get(\"name\")}: {float(tc.get(\"time\", 0)):.1f}s')
"
```

### 2. Container Logs -- Operation Latencies

Read `reports/e2e-container-logs.txt` (structured JSON) for timing data.

**Key metrics to extract:**

```bash
LOG=reports/e2e-container-logs.txt

# ADK model call timings (look for google_adk logs)
jq -r 'select(.logger | test("google_adk")) | .ts + " " + .msg' $LOG

# Error timings (how long before errors occurred)
jq -r 'select(.level == "ERROR") | .ts + " " + .msg' $LOG

# Agent initialization timing
jq -r 'select(.msg | test("Created|Initialized|loaded")) | .ts + " " + .msg' $LOG

# WebSocket session processing
jq -r 'select(.msg | test("process_message|send_events")) | .ts + " " + .msg' $LOG
```

### 3. Historical Run Data

Check `reports/e2e-analysis-history/` for previous run summaries:

```bash
ls -lt reports/e2e-analysis-history/run-*.json | head -5
```

Compare current durations against the most recent previous run to detect regressions.

### 4. Pytest Output

Read `reports/e2e-pytest-output.txt` for:
- Per-test pass/fail/skip with durations
- Tests that were skipped (and why -- missing services)
- Timeout failures

### 5. Application Code -- Hot Paths

Read these key files to identify performance anti-patterns:

| File | What to Look For |
|------|-----------------|
| `radbot/web/app.py` | WebSocket handler efficiency, message processing pipeline |
| `radbot/web/api/session/session_runner.py` | Agent runner setup, context caching, event processing |
| `radbot/agent/agent_core.py` | Root agent creation, sub-agent initialization |
| `radbot/agent/agent_tools_setup.py` | Schema init, tool loading |
| `radbot/agent/specialized_agent_factory.py` | Sub-agent creation pipeline |
| `radbot/tools/mcp/dynamic_tools_loader.py` | MCP tool loading (can be slow) |
| `radbot/memory/embedding.py` | Qdrant embedding calls |

### 6. Test Code -- E2E Efficiency

Read test infrastructure for unnecessary overhead:

| File | What to Look For |
|------|-----------------|
| `tests/e2e/conftest.py` | Fixture scope, cleanup overhead |
| `tests/e2e/helpers/ws_client.py` | WebSocket timeout padding, wait intervals |
| `tests/e2e/test_*.py` | Redundant setup, tests that could be parallelized |

## Analysis Categories

### A. Application Performance

#### A1. LLM/Model Call Efficiency
| Check | What to Look For | Impact |
|-------|-----------------|--------|
| Model call count | How many Gemini API calls per user message? | High |
| Sub-agent routing overhead | Unnecessary transfers between agents | High |
| Context window bloat | Large system prompts or excessive conversation history | Medium |
| Model selection | Expensive models (gemini-2.5-pro) used for simple routing | High |

#### A2. Tool Execution Efficiency
| Check | What to Look For | Impact |
|-------|-----------------|--------|
| Sequential tool calls | Tools called one-at-a-time when they could be parallel | High |
| Unnecessary tool calls | Tools called for data already available | Medium |
| Integration client latency | Slow HTTP calls to HA, Overseerr, Jira, etc. | Medium |
| Database query efficiency | Slow or redundant PostgreSQL queries | Medium |

#### A3. Agent Architecture
| Check | What to Look For | Impact |
|-------|-----------------|--------|
| Agent initialization cost | Time to create root agent + all sub-agents | High |
| Transfer overhead | Extra Gemini calls for agent transfers | High |
| Memory service latency | Qdrant search/store operations | Medium |
| MCP tool loading | Startup penalty from loading MCP toolsets | Medium |

#### A4. WebSocket Pipeline
| Check | What to Look For | Impact |
|-------|-----------------|--------|
| Message processing time | End-to-end latency from receive to response | High |
| Event serialization | Large event payloads (truncation at 100KB) | Medium |
| Concurrent session handling | Lock contention in session manager | Medium |

### B. E2E Test Performance

#### B0. Test Redundancy & Consolidation

Identify tests that overlap significantly and could be consolidated:

| Check | What to Look For | Impact |
|-------|-----------------|--------|
| Duplicate E2E scenarios | Tests that exercise the same agent flow | High |
| E2E tests replaceable by unit tests | E2E tests that only validate REST APIs (could be faster) | High |
| Copy-paste test patterns | Near-identical tests that should be parameterized | Medium |
| Redundant agent chat tests | Multiple tests asking similar questions to the same agent | Medium |

#### B1. Test Infrastructure
| Check | What to Look For | Impact |
|-------|-----------------|--------|
| Docker startup time | Time from `docker compose up` to health check passing | High |
| Credential seeding | Time spent seeding credentials from dev DB | Medium |
| Session creation overhead | Cost of creating new WebSocket sessions per test | Medium |

#### B2. Test Execution
| Check | What to Look For | Impact |
|-------|-----------------|--------|
| Timeout padding | Timeouts set much higher than actual execution | Low |
| Sequential agent tests | Agent tests that could run in parallel | High |
| Redundant assertions | Multiple tests asserting the same behavior | Low |

## How to Compute Metrics

### Per-Test Breakdown

For each test, note:
1. **Total time**: from JUnit XML `time` attribute
2. **Category**: REST API (fast) vs Agent chat (slow) vs Integration (variable)
3. **Skip reason**: If skipped, why (service unavailable, no --run-writes)

### Regression Detection

Compare each test's duration against the previous run:
- **Regression**: >20% slower than previous run
- **Improvement**: >15% faster than previous run
- **Stable**: within +/-15%

### Bottleneck Ranking

Rank bottlenecks by **total recoverable time**:
- Recoverable = time that could be eliminated or parallelized
- Rank by `recoverable_seconds * frequency_per_run`

## Output Format

Write findings to `reports/e2e-performance-review.md`:

```markdown
# Performance Review Report

## Summary
- Total suite duration: Xs (previous: Ys, delta: Z%)
- Tests analyzed: N (passed: N, failed: N, skipped: N)
- Regressions detected: N
- Optimization opportunities: N (estimated savings: Xs)

## Test Duration Table

| Test | Duration | Previous | Delta | Category | Status |
|------|----------|----------|-------|----------|--------|
| test_health_returns_ok | 0.3s | 0.3s | 0% | REST | Stable |
| test_agent_chat_greeting | 45.2s | 42.1s | +7% | Agent | Stable |
| test_integration_overseerr | 85.3s | - | NEW | Integration | New |

## Regressions

### [REGRESSION] test_agent_routing (+25%)
- **Current**: 62.5s | **Previous**: 50.0s | **Delta**: +25%
- **Root cause**: Additional sub-agent routing test added
- **Action**: Expected increase -- no action needed

## Application Bottlenecks

### Bottleneck 1: <description> -- Xs recoverable
- **Category**: Model Call Efficiency / Tool Execution / Agent Architecture
- **Evidence**: <log excerpts, timing data>
- **Impact**: Affects N tests, total Xs across suite
- **Recommendation**: <specific code change with file paths>
- **Estimated savings**: Xs per test
- **Effort**: Low / Medium / High

## E2E Test Bottlenecks

### Bottleneck 1: <description> -- Xs recoverable
- **Category**: Test Infrastructure / Test Execution / Redundancy
- **Evidence**: <timing data, code references>
- **Recommendation**: <specific change>
- **Estimated savings**: Xs per run

## Test Redundancy Analysis

### Redundant Tests Identified

| Test A | Test B | Overlap | Recommendation | Time Saved |
|--------|--------|---------|----------------|------------|

### E2E-to-Unit Conversion Candidates

| E2E Test | What It Checks | Unit Test Alternative | Time Saved |
|----------|---------------|----------------------|------------|

## Historical Trend

| Run Date | Total Duration | Tests | Passed | Skipped | Failed |
|----------|---------------|-------|--------|---------|--------|

## Recommended Priority Order

1. **[High Impact, Low Effort]** <description> -- saves Xs
2. **[High Impact, Medium Effort]** <description> -- saves Xs
```

## Important Notes

- Focus on **measurable** bottlenecks backed by timing data from this run's logs
- Always compare against previous runs -- improvements matter as much as regressions
- Distinguish between **app performance** (affects production users) and **test performance** (affects dev velocity)
- Agent chat tests (requiring Gemini API) are inherently slow (30-90s each) -- focus on reducing unnecessary calls rather than absolute time
- REST API tests should complete in < 1s each -- flag any that take longer
- Propose concrete code changes with file paths and line numbers, not abstract advice
