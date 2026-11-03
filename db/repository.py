"""SQLite 저장소. 테이블 스키마는 pydantic 모델 필드에서 자동 생성·확장된다."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar, get_origin

from pydantic import BaseModel

from db.models import Answer, Application, AppVersion, Experience, InterviewItem, Profile, UsageLog, now_iso

ROOT = Path(__file__).resolve().parent.parent
T = TypeVar("T", bound=BaseModel)

TABLES: dict[str, type[BaseModel]] = {
    "experiences": Experience,
    "profile": Profile,
    "applications": Application,
    "answers": Answer,
    "usage": UsageLog,
    "app_versions": AppVersion,
    "interviews": InterviewItem,
}


def db_path() -> Path:
    return Path(os.getenv("APP_DB_PATH") or ROOT / "data" / "app.db")


@contextmanager
def _conn():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        for table, model in TABLES.items():
            fields = list(model.model_fields)
            cols = ", ".join(f'"{f}" PRIMARY KEY' if f == "id" else f'"{f}"' for f in fields)
            c.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols})')
            existing = {r["name"] for r in c.execute(f'PRAGMA table_info("{table}")')}
            for f in fields:
                if f not in existing:  # 모델에 필드가 추가되면 자동으로 컬럼 추가
                    c.execute(f'ALTER TABLE "{table}" ADD COLUMN "{f}"')


def _encode(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return int(v)
    return v


def _decode(model: type[T], row: sqlite3.Row) -> T:
    data = {}
    for name, field in model.model_fields.items():
        if name not in row.keys() or row[name] is None:
            continue
        v = row[name]
        ann = field.annotation
        if (get_origin(ann) or ann) in (list, dict) and isinstance(v, str):
            v = json.loads(v)
        elif field.annotation is bool:
            v = bool(v)
        data[name] = v
    return model.model_validate(data)


def _upsert(table: str, obj: BaseModel) -> None:
    d = obj.model_dump()
    cols = ", ".join(f'"{k}"' for k in d)
    marks = ", ".join("?" for _ in d)
    with _conn() as c:
        c.execute(f'INSERT OR REPLACE INTO "{table}" ({cols}) VALUES ({marks})', [_encode(v) for v in d.values()])


def _all(table: str, order: str = "") -> list:
    model = TABLES[table]
    with _conn() as c:
        rows = c.execute(f'SELECT * FROM "{table}" {order}').fetchall()
    return [_decode(model, r) for r in rows]


def _get(table: str, id_: str):
    with _conn() as c:
        row = c.execute(f'SELECT * FROM "{table}" WHERE id = ?', (id_,)).fetchone()
    return _decode(TABLES[table], row) if row else None


def _delete(table: str, id_: str) -> None:
    with _conn() as c:
        c.execute(f'DELETE FROM "{table}" WHERE id = ?', (id_,))


# ─────────────────────────── 경험 ───────────────────────────
def list_experiences() -> list[Experience]:
    return _all("experiences", "ORDER BY updated_at DESC")


def get_experience(id_: str) -> Experience | None:
    return _get("experiences", id_)


def save_experience(exp: Experience) -> Experience:
    exp.updated_at = now_iso()
    _upsert("experiences", exp)
    return exp


def delete_experience(id_: str) -> None:
    _delete("experiences", id_)


def experience_usage() -> dict[str, list[Application]]:
    """경험 id → 해당 경험을 사용한 지원서 목록 (EXP-08)."""
    apps = {a.id: a for a in list_applications()}
    usage: dict[str, list[Application]] = {}
    for ans in _all("answers"):
        app = apps.get(ans.application_id)
        if not app:
            continue
        for eid in ans.used_experience_ids:
            lst = usage.setdefault(eid, [])
            if app not in lst:
                lst.append(app)
    return usage


# ─────────────────────────── 프로필 ───────────────────────────
def get_profile() -> Profile:
    return _get("profile", "me") or Profile()


def save_profile(p: Profile) -> None:
    p.id = "me"
    p.updated_at = now_iso()
    _upsert("profile", p)


# ─────────────────────────── 지원서 / 답변 ───────────────────────────
def list_applications() -> list[Application]:
    return _all("applications", "ORDER BY updated_at DESC")


def get_application(id_: str) -> Application | None:
    return _get("applications", id_)


def save_application(app: Application, answers: list[Answer]) -> None:
    """지원서와 답변을 한 번에 저장한다. 기존 답변은 교체된다."""
    app.updated_at = now_iso()
    _upsert("applications", app)
    with _conn() as c:
        c.execute('DELETE FROM "answers" WHERE application_id = ?', (app.id,))
    for i, a in enumerate(answers):
        a.application_id = app.id
        a.order_no = i
        _upsert("answers", a)


def list_answers(application_id: str) -> list[Answer]:
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM "answers" WHERE application_id = ? ORDER BY order_no', (application_id,)
        ).fetchall()
    return [_decode(Answer, r) for r in rows]


def delete_application(id_: str) -> None:
    with _conn() as c:
        for t in ("answers", "app_versions", "interviews"):
            c.execute(f'DELETE FROM "{t}" WHERE application_id = ?', (id_,))
        c.execute('DELETE FROM "applications" WHERE id = ?', (id_,))


def update_application_fields(id_: str, **fields) -> None:
    app = get_application(id_)
    if app:
        _upsert("applications", app.model_copy(update=fields | {"updated_at": now_iso()}))


# ─────────────────────────── 작성 버전 / 최종 제출본 ───────────────────────────
def _where(table: str, model, col: str, val: str, order: str = "") -> list:
    with _conn() as c:
        rows = c.execute(f'SELECT * FROM "{table}" WHERE "{col}" = ? {order}', (val,)).fetchall()
    return [_decode(model, r) for r in rows]


def save_version(application_id: str, label: str = "", is_final: bool = False) -> AppVersion | None:
    """현재 저장된 지원서 내용을 버전으로 남긴다."""
    app = get_application(application_id)
    if not app:
        return None
    n = len(list_versions(application_id)) + 1
    v = AppVersion(
        application_id=application_id,
        label=label.strip() or f"버전 {n}",
        snapshot={"application": app.model_dump(), "answers": [a.model_dump() for a in list_answers(application_id)]},
    )
    _upsert("app_versions", v)
    if is_final:
        set_final_version(v.id)
        v.is_final = True
    return v


def list_versions(application_id: str) -> list[AppVersion]:
    return _where("app_versions", AppVersion, "application_id", application_id, "ORDER BY created_at DESC")


def get_version(id_: str) -> AppVersion | None:
    return _get("app_versions", id_)


def set_final_version(version_id: str) -> None:
    """지원서당 최종 제출본은 하나. 지정 시 상태가 '작성 중'이면 '제출 완료'로, 지원 날짜가 없으면 오늘로 채운다."""
    v = get_version(version_id)
    if not v:
        return
    with _conn() as c:
        c.execute('UPDATE "app_versions" SET is_final = 0 WHERE application_id = ?', (v.application_id,))
        c.execute('UPDATE "app_versions" SET is_final = 1 WHERE id = ?', (version_id,))
    app = get_application(v.application_id)
    if app:
        upd = {}
        if app.status == "작성 중":
            upd["status"] = "제출 완료"
        if not app.applied_date:
            upd["applied_date"] = now_iso()[:10]
        if upd:
            update_application_fields(app.id, **upd)


def final_version(application_id: str) -> AppVersion | None:
    return next((v for v in list_versions(application_id) if v.is_final), None)


def restore_version(version_id: str) -> None:
    """버전의 내용(공고·문항·답변)으로 되돌린다. 지원 상태·날짜·메모는 현재 값을 유지한다."""
    v = get_version(version_id)
    cur = get_application(v.application_id) if v else None
    if not v or not cur:
        return
    snap = Application.model_validate(v.snapshot["application"])
    app = snap.model_copy(update={"status": cur.status, "applied_date": cur.applied_date, "memo": cur.memo,
                                  "created_at": cur.created_at})
    save_application(app, [Answer.model_validate(a) for a in v.snapshot.get("answers", [])])


def delete_version(id_: str) -> None:
    _delete("app_versions", id_)


# ─────────────────────────── 면접 준비 ───────────────────────────
def list_interviews(application_id: str, position: str = "") -> list[InterviewItem]:
    items = _where("interviews", InterviewItem, "application_id", application_id, "ORDER BY order_no, created_at")
    if not application_id:
        items = [i for i in items if i.position == position]
    return items


def save_interview(item: InterviewItem) -> None:
    _upsert("interviews", item)


def delete_interview(id_: str) -> None:
    _delete("interviews", id_)


def duplicate_application(id_: str) -> Application | None:
    src = get_application(id_)
    if not src:
        return None
    copy = src.model_copy(update={"id": Application().id, "company": f"{src.company} (복사본)", "created_at": now_iso(),
                                  "status": "작성 중", "applied_date": ""})
    answers = [a.model_copy(update={"id": Answer(application_id="").id}) for a in list_answers(id_)]
    save_application(copy, answers)
    return copy


# ─────────────────────────── 사용량 ───────────────────────────
def log_usage(stage: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    _upsert("usage", UsageLog(stage=stage, model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens))


def usage_totals() -> dict:
    with _conn() as c:
        r = c.execute(
            'SELECT COUNT(*) n, COALESCE(SUM(prompt_tokens),0) p, COALESCE(SUM(completion_tokens),0) o FROM "usage"'
        ).fetchone()
    return {"calls": r["n"], "prompt_tokens": r["p"], "completion_tokens": r["o"]}


# ─────────────────────────── 백업 / 복원 (EXP-09) ───────────────────────────
BACKUP_TABLES = ["experiences", "profile", "applications", "answers", "app_versions", "interviews"]


def export_all() -> dict:
    return {"version": 1, "exported_at": now_iso(), **{t: [o.model_dump() for o in _all(t)] for t in BACKUP_TABLES}}


def import_all(data: dict) -> dict[str, int]:
    """id 기준으로 병합(같은 id는 덮어쓰기). 테이블별 가져온 건수를 반환한다."""
    counts = {}
    for t in BACKUP_TABLES:
        model = TABLES[t]
        items = data.get(t, [])
        for item in items:
            _upsert(t, model.model_validate(item))
        counts[t] = len(items)
    return counts
