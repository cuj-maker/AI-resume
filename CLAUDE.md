# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal, local Streamlit app (Python 3.11+) that stores a user's experiences, structures each into STAR (Situation/Task/Action/Result), and generates company/role-tailored Korean cover letters (자기소개서) and resumes via the OpenAI API. UI text, prompts, and output are Korean. `PRD.md` is the spec; requirement IDs (EXP-xx, CL-xx, RS-xx) are referenced in code comments.

## Commands

```
pip install -r requirements.txt
streamlit run app.py
```

There is no test suite in the repo. To smoke-test pages without the API, use `streamlit.testing.v1.AppTest`: monkeypatch `chat_json` on `core.star`, `core.matcher`, `core.writer`, `core.verifier` (each imports it by name) and `core.llm.test_connection`, and set `APP_DB_PATH` to a temp file so the real `data/app.db` is untouched.

## Non-negotiable rule: no fabrication

Generated text may only use facts present in stored experiences (raw text + STAR) and user-entered company info. Never invent numbers, awards, titles, durations, or company facts; missing info becomes a `[보완 필요: ...]` marker. These rules live in `core/prompts.py` `SYSTEM_BASE`, which every generation prompt extends. Every generated answer is followed by a separate verification call (`core/verifier.py`); unsupported sentences are highlighted. Preserve this when changing prompts or the pipeline.

## Architecture

- `app.py` only sets page config and builds `st.navigation` over `views/`. The folder is deliberately **not** named `pages/`: Streamlit auto-discovers `pages/` and then runs page files directly, bypassing `app.py`.
- Every view file must call `ui.bootstrap()` (DB init, state persistence, pending updates, CSS) and `ui.sidebar_status()` before rendering widgets. Setup lives in each page, not `app.py`, so it also runs under AppTest, which executes page files in isolation.
- **Widget state conventions (`core/ui.py`)**:
  - Widget keys prefixed `p_` survive page navigation; `keep_state()` reassigns them on every run so Streamlit doesn't clean them up.
  - Initialize widget values with `ui.init(key, default)` or by setting session_state before the widget renders. Never pass `value=` together with a `p_` key.
  - To change a widget's value after it has rendered (e.g. after an LLM call), use `ui.queue({key: value}, toast=...)` then `st.rerun()`. The update is applied at the next `bootstrap()`. A `None` value deletes the key.
  - Non-widget page state uses plain session keys, e.g. `cl` for the cover-letter page (`qids`, per-question `recs` / `verification` / `verified_text` / `used_ids`).
- **LLM layer (`core/llm.py`)**: the only module that reads `.env`. `chat_json(system, user, schema, stage)` uses JSON mode with the pydantic schema embedded in the system prompt, validates the reply, and retries once on parse failure. If the model rejects a parameter (`temperature`, `response_format`), the request is retried without it. Token usage is logged to the `usage` table. All API errors become `LLMError` with Korean messages for `st.error`.
- **Pipeline**: `star.analyze` → `matcher.analyze_posting` → `matcher.recommend` → `writer.generate_answer` → `verifier.verify`.
  - `writer.fit_length` does the 90–100% char-limit adjustment and keeps the adjusted text only if it's closer to the target. It's reused by generation, the 축약/확장 button, and `reviewer.review` (첨삭).
  - `reviewer.review` drops quoted "duplicate"/"abstract" expressions that don't appear verbatim in the answer.
  - `core/interview.py` generates questions (categories in `INTERVIEW_CATEGORIES`, trimmed to the requested counts), writes STAR model answers, and evaluates user answers.
  - Any step that replaces an answer (generate, 첨삭 apply, fit) re-runs verification via `_verify_and_set` in `views/2_자기소개서_작성.py` and stores `prev_answer` for undo.
- **Storage (`db/repository.py`)**: SQLite. Table columns are generated from the pydantic models in `db/models.py`, and new model fields are added via `ALTER TABLE` on `init_db()`, so adding a field needs no migration. List and dict fields are stored as JSON text. `save_application` replaces all answers of an application. A verification result is saved only if the answer text hasn't changed since it was verified.
  - `app_versions` stores full JSON snapshots (application + answers). At most one `is_final` row per application. `set_final_version` also bumps the status from 작성 중 to 제출 완료 and fills `applied_date`.
  - `restore_version` restores content only and keeps the current status, date, and memo.
  - `interviews` rows have an empty `application_id` when they were created from a position alone. Those rows are filtered by `position`.
  - `delete_application` cascades to answers, versions, and interviews.
- Resume sections are grouped by experience type via `RESUME_SECTIONS` in `db/models.py`. `exporter.resume_blocks` is the single source for both the MD and DOCX layouts.
- AppTest doesn't follow `st.switch_page`, so call `at.switch_page(...)` explicitly in tests.

## Configuration

`.env`: `OPENAI_API_KEY`, `OPENAI_MODEL` (defaults to `gpt-6-astra` if unset), `OPENAI_TEMPERATURE`. Never hardcode the model. `APP_DB_PATH` overrides the DB location (default `data/app.db`).
