# Scheduler (Cron Jobs)

The scheduler allows the agent to create, list, and delete recurring tasks that run on a cron schedule. When a scheduled task fires, its prompt is sent to the agent and the response is pushed to all connected web UI clients via WebSocket.

## Architecture

- **Backend**: APScheduler `AsyncIOScheduler` with `CronTrigger`
- **Storage**: PostgreSQL `scheduled_tasks` table (same DB as todos)
- **Engine**: `SchedulerEngine` singleton in `radbot/tools/scheduler/engine.py`
- **API**: REST endpoints at `/api/scheduler/tasks`

## Agent Tools

The agent has three scheduling tools:

### `create_scheduled_task`
Create a recurring task.

Parameters:
- `name` (str, required): Human-readable name for the task
- `cron_expression` (str, required): Standard cron expression (e.g., `0 9 * * *` for 9am daily)
- `prompt` (str, required): The prompt to send to the agent when the task fires
- `description` (str, optional): Description of what the task does

Example conversation:
```
User: Schedule a weather check every morning at 9am
Agent: [calls create_scheduled_task with name="morning_weather",
        cron_expression="0 9 * * *",
        prompt="What's the weather forecast for today?"]
```

### `list_scheduled_tasks`
List all scheduled tasks with their status, next run time, and run count.

### `delete_scheduled_task`
Delete a scheduled task by its ID.

Parameters:
- `task_id` (str, required): UUID of the task to delete

## Cron Expression Format

Standard 5-field cron syntax: `minute hour day_of_month month day_of_week`

| Expression | Meaning |
|-----------|---------|
| `0 9 * * *` | Every day at 9:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 */2 * * *` | Every 2 hours |
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `0 0 1 * *` | First day of each month at midnight |

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scheduler/tasks` | List all scheduled tasks |
| POST | `/api/scheduler/tasks` | Create a new scheduled task |
| DELETE | `/api/scheduler/tasks/{task_id}` | Delete a scheduled task |

## How It Works

1. Agent creates a task via the `create_scheduled_task` tool
2. Task is stored in PostgreSQL and registered with APScheduler
3. When the cron trigger fires, the engine sends the prompt to the agent
4. The agent's response is broadcast to all connected WebSocket clients
5. The response appears in the web UI as a message from "SCHEDULER"
6. Last result is stored in the DB for when no clients are connected

## Configuration

In `config.yaml`:
```yaml
scheduler:
  enabled: true
  timezone: "US/Pacific"
  max_concurrent_jobs: 5
```

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    prompt TEXT NOT NULL,
    description TEXT,
    session_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMPTZ,
    last_result TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB
);
```

## Files

| File | Purpose |
|------|---------|
| `radbot/tools/scheduler/__init__.py` | Package exports |
| `radbot/tools/scheduler/db.py` | Database schema + CRUD |
| `radbot/tools/scheduler/schedule_tools.py` | Agent tool functions |
| `radbot/tools/scheduler/engine.py` | APScheduler engine singleton |
| `radbot/web/api/scheduler.py` | REST API router |
