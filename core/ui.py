"""공통 UI: 테마 CSS, 컴포넌트, 페이지 간 상태 유지."""
from __future__ import annotations

import html

import streamlit as st

from core import llm
from db import repository as repo

STAR_META = {
    "S": ("Situation", "상황", "#2D4BD8"),
    "T": ("Task", "과제·목표", "#7B4DD8"),
    "A": ("Action", "행동·해결", "#0E9F6E"),
    "R": ("Result", "결과·성과", "#E8590C"),
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
html, body, p, li, label, input, textarea, h1, h2, h3, h4, h5, h6, .stMarkdown {
  font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
.block-container { padding-top: 3.2rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.02em; }

.hero { padding: 22px 26px; border-radius: 18px; margin-bottom: 18px;
  background: linear-gradient(135deg, #FFFFFF 0%, #EEF2FF 100%); border: 1px solid #E1E6F5; }
.hero-title { font-size: 1.7rem; font-weight: 700; color: #1E2330; margin: 0; line-height: 1.3; letter-spacing: -0.02em; }
.hero-sub { color: #5B6275; margin-top: 4px; font-size: .95rem; }

.step { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1.05rem; margin: 4px 0 8px; }
.step-num { width: 26px; height: 26px; border-radius: 50%; background: #2D4BD8; color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: .82rem; flex: none; }
.step-desc { color: #6B7285; font-weight: 400; font-size: .85rem; }

.chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem;
  margin: 0 6px 6px 0; background: #EEF1FF; color: #2D4BD8; white-space: nowrap; }
.chip.comp { background: #E6F7EF; color: #0B7A55; }
.chip.warn { background: #FFF1E6; color: #B5470B; }
.chip.muted { background: #EFF1F5; color: #555D70; }
.chip.type { background: #1E2330; color: #fff; }

.star-card { background: #fff; border: 1px solid #E6E9F0; border-left: 4px solid var(--c);
  border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; }
.star-head { font-weight: 700; color: var(--c); font-size: .85rem; letter-spacing: .02em; }
.star-body { color: #2A3040; font-size: .92rem; line-height: 1.65; margin-top: 2px; }
.star-empty { color: #A0A6B4; font-style: italic; }

.answer-box { background: #fff; border: 1px solid #E3E6EE; border-radius: 12px; padding: 16px 18px;
  line-height: 1.85; font-size: .95rem; color: #222836; }
mark.unsupported { background: #FFE3E3; color: inherit; border-bottom: 2px solid #E03131; padding: 0 2px; border-radius: 3px; }

.exp-meta { color: #6B7285; font-size: .8rem; }
.muted { color: #6B7285; font-size: .85rem; }
.rec { padding: 8px 0; border-bottom: 1px dashed #E3E6EE; }
.rec-score { font-weight: 700; color: #2D4BD8; }
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def _init_db_once() -> bool:
    repo.init_db()
    return True


def bootstrap() -> None:
    """각 페이지 맨 위에서 호출: DB 준비, 상태 유지, 대기 중인 값 적용, 테마."""
    _init_db_once()
    keep_state()
    apply_pending()
    apply_theme()


# ─────────────────────────── 상태 유지 ───────────────────────────
# 'p_'로 시작하는 위젯 키는 페이지를 이동해도 값이 유지된다.
# (Streamlit은 화면에 없는 위젯의 상태를 지우므로, 매 실행마다 다시 할당해 정리 대상에서 뺀다.)
def keep_state() -> None:
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("p_"):
            st.session_state[k] = st.session_state[k]


def init(key: str, default) -> None:
    if key not in st.session_state:
        st.session_state[key] = default


def queue(updates: dict, toast: str | None = None) -> None:
    """위젯이 이미 그려진 뒤에 값을 바꿔야 할 때: 다음 실행 시작 시 적용한다. None은 삭제."""
    st.session_state.setdefault("_pending", {}).update(updates)
    if toast:
        st.session_state["_toast"] = toast


def apply_pending() -> None:
    for k, v in st.session_state.pop("_pending", {}).items():
        if v is None:
            st.session_state.pop(k, None)
        else:
            st.session_state[k] = v
    if msg := st.session_state.pop("_toast", None):
        st.toast(msg, icon="✅")


def clear_prefix(*prefixes: str) -> None:
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(prefixes):
            del st.session_state[k]


# ─────────────────────────── 컴포넌트 ───────────────────────────
def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="hero"><div class="hero-title">{html.escape(title)}</div>'
        f'<div class="hero-sub">{html.escape(subtitle)}</div></div>',
        unsafe_allow_html=True,
    )


def step(num: int | str, title: str, desc: str = "") -> None:
    d = f'<span class="step-desc">{html.escape(desc)}</span>' if desc else ""
    st.markdown(
        f'<div class="step"><span class="step-num">{num}</span>{html.escape(title)} {d}</div>',
        unsafe_allow_html=True,
    )


def chips_html(items: list[str], kind: str = "") -> str:
    return "".join(f'<span class="chip {kind}">{html.escape(i)}</span>' for i in items if i)


def chips(items: list[str], kind: str = "") -> None:
    if items:
        st.markdown(chips_html(items, kind), unsafe_allow_html=True)


def star_card(letter: str, text: str) -> None:
    en, ko, color = STAR_META[letter]
    body = html.escape(text).replace("\n", "<br>") if text.strip() else '<span class="star-empty">내용 없음</span>'
    st.markdown(
        f'<div class="star-card" style="--c:{color}"><div class="star-head">{letter} · {en} — {ko}</div>'
        f'<div class="star-body">{body}</div></div>',
        unsafe_allow_html=True,
    )


def html_box(inner_html: str) -> None:
    st.markdown(f'<div class="answer-box">{inner_html}</div>', unsafe_allow_html=True)


def sidebar_status() -> None:
    s = llm.settings()
    with st.sidebar:
        st.markdown("#### AI 연결")
        if s["api_key"]:
            st.markdown(
                f'<span class="status-dot" style="background:#0E9F6E"></span>API 키 설정됨<br>'
                f'<span class="muted">모델: <code>{html.escape(s["model"])}</code></span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="status-dot" style="background:#E03131"></span>API 키 없음',
                unsafe_allow_html=True,
            )
            st.caption(".env 파일에 `OPENAI_API_KEY=...`를 한 줄로 입력하고 앱을 다시 시작하세요.")
        # PRD §11: 세션 시작 시 1회 자동 연결 확인, 실패하면 안내
        if s["api_key"] and "_conn_checked" not in st.session_state:
            st.session_state["_conn_checked"] = llm.test_connection()
        checked = st.session_state.get("_conn_checked")
        if checked and not checked[0]:
            st.error(checked[1])
        if st.button("연결 테스트", use_container_width=True, disabled=not s["api_key"]):
            with st.spinner("확인 중…"):
                st.session_state["_conn_checked"] = ok_msg = llm.test_connection()
            (st.success if ok_msg[0] else st.error)(ok_msg[1])
        u = repo.usage_totals()
        if u["calls"]:
            st.caption(f"누적 AI 호출 {u['calls']}회 · 토큰 {u['prompt_tokens'] + u['completion_tokens']:,}")


def require_api() -> bool:
    if not llm.is_configured():
        st.warning("OpenAI API 키가 설정되지 않아 AI 기능을 사용할 수 없습니다. 사이드바 안내를 확인하세요.", icon="🔑")
        return False
    return True
