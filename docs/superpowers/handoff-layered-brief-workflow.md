# Handoff: Layered Brief Workflow

Branch: `feature/layered-brief-workflow`

---

## What this branch does

Introduces a two-tier brief generation model. Every brief now has:

1. **A primary brief** — a fast 1-minute summary written by `write_primary_brief`, covering all focal points at a high level.
2. **Auto-deep sections** — topics the planner marked `AUTO_DEEP` get full deep analysis generated immediately and appended to the brief.
3. **Optional-deep stubs** — topics marked `OPTIONAL_DEEP` appear in the brief as short summaries with an expand button. The user can trigger deep analysis on demand; it runs in the background and patches the brief content in-place.

---

## Generation modes

Each focal point in the plan carries a `generation_mode` field set by the planner:

| Mode | Behaviour |
|---|---|
| `BRIEF_ONLY` | Appears in the primary brief only. No deep section. |
| `AUTO_DEEP` | Primary brief + deep analysis generated immediately at brief creation time. |
| `OPTIONAL_DEEP` | Primary brief + a stub section (`## Topic（可展开分析）`) with a brief summary and a topic overview (2-3 sentences). Deep analysis generated on user demand. |

The planner assigns `OPTIONAL_DEEP` when a topic has a substantive `topic_overview` (≥20 chars). Short or empty overviews cause the topic to fall back to `BRIEF_ONLY`. See `agent/workflow/layered.py` — `normalize_plan_layers()`.

---

## Key files

### Agent layer

- **`agent/models.py`** — `ExpandableTopic` TypedDict: `{ topic_id, focal_point }`. `FocalPoint` includes `topic_overview` (user-facing topic description). No article snapshots stored; article ids live in `focal_point["article_ids"]` and are re-fetched from DB at expansion time.
- **`agent/workflow/layered.py`** — `normalize_plan_layers()`, `get_auto_deep_points()`, `get_optional_deep_points()`, `assemble_layered_report()`, `build_optional_stubs()`. The stub section format is `## {topic}（可展开分析）\n{brief_summary}\n\n{topic_overview}`.
- **`agent/workflow/expansion.py`** — `build_expandable_topics(plan)` builds the list of `ExpandableTopic` objects saved to the DB. `build_expansion_state(topic, fetched_articles)` reconstructs an `AgentState` for a single topic expansion.
- **`agent/workflow/executor.py`** — `execute()` orchestrates: fetch article content → normalize plan → build expandable topics → write primary brief → run auto-deep points in parallel → assemble final report.

### Backend

- **`apps/backend/services/brief_service.py`**
  - `expand_optional_topic(brief_id, topic_id) -> None` — fetches article content, runs the appropriate handler (`handle_summarize` / `handle_search_enhance` / `handle_flash_news`), then calls `_patch_brief_expansion`.
  - `_patch_brief_expansion(brief_id, topic_id, new_section)` — loads `content` and `expandable_topics` from DB, regex-replaces the section under the matching `##` heading (handles both plain `## Topic` and `## Topic（可展开分析）` headings), removes the topic from `expandable_topics`, writes both back in one UPDATE.

- **`apps/backend/router/brief.py`** — `POST /briefs/{brief_id}/expand/{topic_id}` returns **202** immediately. It validates the brief and topic exist, then fires `asyncio.create_task(brief_service.expand_optional_topic(...))` and returns `{"message": "expansion started"}`.

- **`apps/backend/models/view_model.py`** — `ExpandableTopicVO` is `{ topic_id, topic }` only. The full `focal_point` is not exposed to the frontend.

- **`core/models/feed.py`** — `FeedBrief.to_view_model()` projects `expandable_topics` to `[{ "topic_id": ..., "topic": focal_point["topic"] }]`.

### Frontend

- **`src/types/api.ts`** — `ExpandableTopic: { topicId, topic }`.
- **`src/api/client.ts`** — `expandOptionalTopic(briefId, topicId)` fires a POST and ignores the response body (202, no data).
- **`src/pages/SummaryPage.tsx`** — The h2 custom renderer detects expandable topics by matching the heading text against `brief.expandableTopics`. Matching headings get a `<Sparkles>` button with a hover tooltip explaining what it does. Clicking fires `handleExpandTopic` which calls the API and shows a toast: "正在生成深度分析，完成后将自动更新". No polling — the user refreshes the brief to see the updated content.

---

## Data flow: brief creation

```
Planner → focal_points with generation_mode
  ↓
normalize_plan_layers()       # validates modes, merges overlapping topics
  ↓
write_primary_brief()         # fast 1-min summary of all points
  ↓
auto_deep_points → parallel deep analysis
  ↓
assemble_layered_report()     # primary brief + deep sections + optional stubs
  ↓
_insert_brief()               # saves content + expandable_topics JSONB
```

## Data flow: on-demand expansion

```
User clicks Sparkles button
  ↓
POST /briefs/{id}/expand/{topic_id}  → 202 immediately
  ↓ (background task)
expand_optional_topic()
  get_article_content(focal_point["article_ids"])
  build_expansion_state(topic, fetched_articles)
  handle_summarize / handle_search_enhance / handle_flash_news
  _patch_brief_expansion()
    regex-replace ## heading section in content
    remove topic from expandable_topics
    UPDATE feed_brief SET content=..., expandable_topics=...
```

---

## DB schema (relevant columns)

`feed_brief`:
- `content TEXT` — full markdown brief
- `expandable_topics JSONB` — array of `{ topic_id, focal_point }`. Shrinks as topics are expanded. Empty array when all expanded.
- `overview TEXT` — `today_pattern` from the plan, shown as the brief overview card.

---

## Known pre-existing test failures

None. The two previously failing tests in `test_layered_workflow.py` (`test_assemble_report_keeps_brief_first` and `test_optional_section_uses_specific_reason`) have been fixed.

---

## Tests

```bash
# Core expansion tests
uv run python -m unittest \
  test.test_expandable_topics \
  test.test_workflow_executor_layering \
  test.test_optional_expansion_service \
  test.test_optional_expansion_router -v

# Full layered workflow suite (2 pre-existing failures expected)
uv run python -m unittest \
  test.test_layered_workflow \
  test.test_workflow_cleanup \
  test.test_layered_memory_records -v
```
