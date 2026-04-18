# HA Alias Learning Loop (Plan)

<!-- Status: planned, not yet implemented | Depends on: HA MCP migration -->

## Context

Home Assistant's intent resolver (`MatchTargets`, reached via the `mcp_server` integration) matches user phrasing to entities using:

- entity `friendly_name`
- entity `aliases` list (entity registry)
- area `name` + area `aliases` list (area registry)
- floor `name` + floor `aliases` list (floor registry)
- `domain[]` / `device_class[]` filters passed in the tool call

The HA MCP migration (see `docs/implementation/integrations/ha_mcp_migration.md` once shipped) dropped radbot's `search_ha_entities` tool because HA now does the matching natively. But HA's matcher only knows what HA's registries have been *told* about — friendly names and any aliases the user manually added in the HA UI.

In production we routinely see queries like "turn off the basement grow" where:

- "grow" is not a friendly name of any entity
- "grow" is not an alias on anything in HA
- But the entities *are* all grouped under an area called `all grow lights`

On such a query the LLM's first `HassTurnOff(name="basement grow", domain=["light","switch"])` returns `MatchFailedError`. The LLM's recovery today: call `GetLiveContext`, search client-side, re-call `HassTurnOff` with the right area or name. Works, but it's two LLM roundtrips on every such phrase — forever.

**This plan is about capturing those recoveries as persistent aliases so the second+ time the user says "grow" it resolves in one roundtrip.**

## Goal

Let radbot learn entity and area aliases from successful fuzzy-resolution episodes, promote them into HA's registry after enough corroboration, and expose the pipeline so a human can audit / override before or after promotion.

**Non-goals:**

- Do not maintain a parallel "radbot-side" alias map. HA's matcher is the authority; any alias radbot cares about ultimately lives in HA. See "Why not pure-postgres" below.
- Do not auto-learn from first encounter. The learning loop is deliberately conservative — corroboration-gated and user-visible.
- Do not touch exposure config (`homeassistant/expose_entity`). Exposure is the user's policy surface; aliases are a naming surface. They stay separate.

## Why hybrid (postgres candidate queue + HA for production aliases)

**HA is the production store** for two decisive reasons:

1. **HA's resolver has features we'd otherwise rebuild.** `MatchTargets` handles floor > area > entity hierarchy, `domain[]` expansion, `device_class` narrowing, `allow_duplicate_names` toggling, fuzzy matching with aliases. Reproducing this in radbot would be a real project with long-tail edge cases.
2. **Area aliases cover groups of entities for free.** Adding "grow" as an alias on the `all grow lights` area is one write that covers 8 switches. A radbot-side phrase map would have to either re-implement area resolution or rewrite one phrase into N individual entity calls.

**radbot postgres is the learning queue + audit trail** because HA has no concept of:

- "we saw this phrase N times"
- "user confirmed / rejected this mapping"
- "this alias was promoted by radbot on date X, rollback-able via this row"

Pure-HA loses all provenance. Pure-postgres loses HA's native resolver and multi-client benefit. Hybrid keeps both.

## Architecture

```
User message
  └─ casa LLM emits HassTurnOff(name="basement grow", domain=[...])
       └─ HA MCP returns MatchFailedError
            └─ casa LLM calls GetLiveContext
                 └─ LLM picks area "all grow lights" + retries
                      └─ HA MCP succeeds
                           └─ candidate_recorder hook writes a row to
                              ha_alias_candidates
                                (user_phrase, resolved_target_id, session_id, ...)

  (later, async)
  └─ candidate_promoter job
       └─ any candidate with usage_count >= N and user_rejected = false?
            ├─ send notification to user: "I keep seeing 'grow'
            │   — add as an alias for area 'all grow lights'? [yes/no/never]"
            └─ on yes → config/area_registry/update via WS client
                 └─ mark candidate row promoted_at = now()
```

Two independent flows: **candidate recording** runs on every successful fuzzy resolution (synchronous, lightweight); **promotion** is async and human-in-the-loop.

## Components

### 1. DB schema — `ha_alias_candidates`

```sql
CREATE TABLE IF NOT EXISTS ha_alias_candidates (
    candidate_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_kind          TEXT NOT NULL CHECK (target_kind IN ('entity', 'area', 'floor')),
    target_id            TEXT NOT NULL,           -- entity_id / area_id / floor_id
    target_display_name  TEXT NOT NULL,           -- for humans in admin UI
    user_phrase          TEXT NOT NULL,           -- normalized lowercase, stripped
    resolution_path      TEXT NOT NULL,           -- 'getlivecontext' | 'domain_expand' | 'fuzzy_alias' | 'manual'
    usage_count          INT NOT NULL DEFAULT 1,
    session_ids          TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],  -- distinct sessions it's been seen in
    user_confirmed       BOOL NOT NULL DEFAULT FALSE,
    user_rejected        BOOL NOT NULL DEFAULT FALSE,
    promoted_at          TIMESTAMPTZ,             -- when we wrote to HA; NULL if not yet
    promoted_alias_text  TEXT,                    -- exact string we wrote (for rollback)
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes                TEXT,

    UNIQUE (target_kind, target_id, user_phrase)
);

CREATE INDEX ha_alias_candidates_unpromoted
  ON ha_alias_candidates (usage_count DESC, last_seen_at DESC)
  WHERE promoted_at IS NULL AND user_rejected = FALSE;
```

Schema init hook: `init_ha_alias_schema()` in `radbot/tools/homeassistant/alias_db.py`, wired into `setup_before_agent_call` alongside the existing schema registry (see `radbot/agent/agent_tools_setup.py`).

### 2. WebSocket alias methods

Extend `radbot/tools/homeassistant/ha_websocket_client.py`:

```python
async def list_entity_registry(self) -> list[dict]:
    return await self.send_command("config/entity_registry/list")

async def update_entity_aliases(self, entity_id: str, aliases: list[str]) -> dict:
    return await self.send_command(
        "config/entity_registry/update",
        entity_id=entity_id,
        aliases=aliases,
    )

async def list_area_registry(self) -> list[dict]:
    return await self.send_command("config/area_registry/list")

async def update_area_aliases(self, area_id: str, aliases: list[str]) -> dict:
    return await self.send_command(
        "config/area_registry/update",
        area_id=area_id,
        aliases=aliases,
    )

async def list_floor_registry(self) -> list[dict]:
    return await self.send_command("config/floor_registry/list")

async def update_floor_aliases(self, floor_id: str, aliases: list[str]) -> dict:
    return await self.send_command(
        "config/floor_registry/update",
        floor_id=floor_id,
        aliases=aliases,
    )
```

The existing transport (`send_command`) already handles auth, reconnect, and message-ID correlation — these are thin convenience wrappers.

**Important detail for `update_*_aliases`:** HA's registry update is a full replace of the `aliases` list, not an append. Implementations must read current aliases first, union/remove, then write back. Do this in an atomic helper.

### 3. Candidate recording hook

Add `record_alias_candidate` in `radbot/tools/homeassistant/alias_learner.py`:

```python
def record_alias_candidate(
    *,
    user_phrase: str,
    target_kind: str,         # 'entity' | 'area' | 'floor'
    target_id: str,
    target_display_name: str,
    resolution_path: str,     # what led us here
    session_id: str | None = None,
) -> None:
    """Upsert a candidate row. Lightweight, never raises into hot path."""
```

Called by casa's `HassTurnOn`/`HassTurnOff`/etc. retry path when:
- the first call returned `MatchFailedError`, AND
- a follow-up call succeeded on the same user phrase with a different resolution strategy

Implementation note: the MCP tool adapter (the ADK `FunctionTool` wrapper around each HA MCP tool) is the natural seam. On success, it inspects whether the preceding call for this LLM turn failed with `MatchFailedError` and if so records a candidate.

**Normalization rules for `user_phrase`:**

- lowercase
- strip surrounding whitespace + punctuation
- collapse internal whitespace
- strip common stop phrases: "the ", "my ", "please ", leading / trailing articles
- keep a `raw_phrase` in `notes` JSON for debugging

### 4. Promotion rules

A nightly (or on-demand) job scans `ha_alias_candidates WHERE promoted_at IS NULL AND user_rejected = FALSE`. Proposed thresholds (tunable via `config:agent.alias_learning`):

```yaml
alias_learning:
  enabled: true
  min_usage_count: 3              # how many successful resolutions before proposing
  min_distinct_sessions: 2        # across multiple user sessions (not one bad session)
  cooldown_days: 7                # don't re-propose a rejected candidate within N days
  auto_promote: false             # if true, skip user notification and promote directly
  max_aliases_per_target: 10      # safety cap on alias list length
```

Three paths a candidate can take:

1. **Proposed → confirmed** — user clicks "yes" on the notification. Alias written to HA, `user_confirmed=true`, `promoted_at=now()`, `promoted_alias_text` recorded.
2. **Proposed → rejected** — user clicks "no". `user_rejected=true`. The candidate is kept so we don't propose it again; future identical resolutions still bump `usage_count` (for telemetry) but no re-proposal until `cooldown_days`.
3. **Proposed → ignored** — no click. The notification expires; the candidate stays in the queue for the next run.

Path (4) — **auto-promote** — is supported but off by default. Behind a config flag for users who want radbot to manage aliases aggressively.

### 5. Tools on casa (manual alias management)

Independently of the learning loop, expose explicit tools the user can invoke:

| Tool | Parameters | Purpose |
|---|---|---|
| `ha_list_aliases` | `target_kind`, `target_id` | Read current aliases for an entity/area/floor |
| `ha_add_alias` | `target_kind`, `target_id`, `alias`, `reason?` | Union-add one alias; record in candidates as `user_confirmed=true` already |
| `ha_remove_alias` | `target_kind`, `target_id`, `alias` | Remove one alias; update the candidate row `promoted_at=NULL` |
| `ha_list_candidates` | `promoted?`, `limit?` | Read the candidate queue for admin/debug |
| `ha_promote_candidate` | `candidate_id` | Force-promote a candidate (skip threshold) |
| `ha_reject_candidate` | `candidate_id` | Mark rejected |

These cover cases like "Perry: 'add an alias grow to the all grow lights area'" — direct, no learning loop needed.

### 6. Admin panel

New section in `/admin/` → "HA Alias Learning":

- Summary: candidates queued, promoted this month, rejected, top-phrases-by-usage
- Table of unpromoted candidates sorted by `usage_count DESC`, with inline promote/reject buttons
- Table of promoted aliases with rollback
- Pricing-panel style test button: "Preview HA registry state for `<entity_id>`"

Frontend path follows the existing pattern: `radbot/web/frontend/src/components/admin/panels/HaAliasPanel.tsx`, registered in `AdminPage.tsx` NAV_ITEMS + PANEL_MAP.

## Safety guards (design decisions, not afterthoughts)

1. **Never auto-learn from a failed recovery.** Candidates are only written after a full round-trip success. If the LLM bounced between resolutions without ever succeeding, nothing is learned.
2. **Alias collision check before write.** Before calling `update_*_aliases`, list the current registry and refuse if the proposed alias string is already attached to a *different* target. Surface the conflict as a notification and leave the candidate in the queue.
3. **Domain sanity check.** Don't learn a phrase as an entity alias if the matched entities span >2 domains — that means the phrase is really an area-or-group concept, not an entity concept. Re-target the candidate to the area.
4. **Prefer area-level over entity-level.** If multiple entity matches share a single area, propose an area alias. One alias, one write, benefits every entity in the area forever.
5. **Cap alias count per target** (`max_aliases_per_target`, default 10). Prevents alias bloat from tail queries. If hit, surface a "you may want to prune" notification rather than silently dropping.
6. **Provenance in our table, not HA's.** HA's alias list has no "who added this" concept. We keep that in `ha_alias_candidates`. When rolling back, we read `promoted_alias_text` from our row and issue a remove via WS.
7. **User opt-out entirely.** `config:agent.alias_learning.enabled = false` disables the recording hook and the promoter job. Existing aliases stay in HA untouched. This is the escape hatch if someone objects philosophically to "an agent modifying HA config."

## What this adds to casa's base prompt

- 0-6 new FunctionTools (0 if learning is disabled, 3 for read-only learning, 6 for manual + learning). Each small-schema — estimate ~50-80 tokens each. Worst case ~500 tokens on casa's permanent prompt.
- Worth weighing at review time: are these on *casa* or on a separate `admin` sub-agent beto routes to? The learning tools get used rarely; offloading to a dedicated agent would keep casa's permanent prompt tighter. Argues for a new `admin` sub-agent or for putting them on axel (which already has system-admin tools).

## Rollout plan (when picking this up)

1. Migration: `init_ha_alias_schema()` + wire into startup. One commit.
2. WS client methods. One commit.
3. `record_alias_candidate` + hook in the HA MCP tool adapter. One commit.
4. Manual management tools (`ha_add_alias`, `ha_remove_alias`, `ha_list_aliases`). One commit. Ship this as its own PR for manual use before learning loop is enabled.
5. Promoter job + notifications. Behind `alias_learning.enabled` flag (default false). One commit.
6. Admin panel. One commit.
7. Flip `alias_learning.enabled = true` in a final config change after a few days of manual use.

## References

- HA entity registry WebSocket API: https://developers.home-assistant.io/docs/api/websocket/#entity-registry
- HA area registry WebSocket API: https://developers.home-assistant.io/docs/api/websocket/#area-registry
- HA floor registry WebSocket API: https://developers.home-assistant.io/docs/api/websocket/#floor-registry
- HA exposing entities to Assist: https://www.home-assistant.io/voice_control/voice_remote_expose_devices/
- HA MCP server integration: https://www.home-assistant.io/integrations/mcp_server/
- The MCP migration plan this depends on: `docs/implementation/integrations/ha_mcp_migration.md` (once shipped)

## Open questions to resolve on pickup

- **Notification delivery** — we don't currently push interactive prompts to the user outside the chat UI. Candidate options: reuse the existing notifications table + admin badge (simplest), or pop a chat-UI toast with action buttons. Decide before shipping the promoter job.
- **Where do the tools live?** — casa (higher prompt cost, lower friction) vs a dedicated admin sub-agent (extra routing hop, lower prompt cost). Test in prod after manual-tools ship.
- **Normalization corpus** — which stop phrases / common openers are actually in our usage? Revisit after 1 week of candidate data.
- **Floor registry adoption** — HA floors are a relatively new concept (2024+). Check whether Perry's setup uses them before committing UI space.
