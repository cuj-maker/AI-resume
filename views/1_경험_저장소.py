import html
import json
import re

import streamlit as st

from core import star, ui
from core.llm import LLMError
from db import repository as repo
from db.models import EXPERIENCE_TYPES, Experience

NEW = "__new__"
# 편집기 위젯 키 ↔ Experience 필드
FIELDS = {
    "p_exp_type": "type",
    "p_exp_title": "title",
    "p_exp_org": "organization",
    "p_exp_role": "role",
    "p_exp_start": "start_date",
    "p_exp_end": "end_date",
    "p_exp_ongoing": "ongoing",
    "p_exp_raw": "raw_text",
    "p_exp_S": "situation",
    "p_exp_T": "task",
    "p_exp_A": "action",
    "p_exp_R": "result",
}
YM = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _split(text: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,\n]", text or "") if t.strip()]


def _editor_state(exp: Experience) -> dict:
    d = {k: getattr(exp, f) for k, f in FIELDS.items()}
    d |= {
        "p_exp_kw": ", ".join(exp.keywords),
        "p_exp_comp": ", ".join(exp.competencies),
        "p_exp_missing": list(exp.missing_info),
        "p_exp_followups": list(exp.follow_up_questions),
        "p_exp_created": exp.created_at,
    }
    return d


def open_editor(exp_id: str) -> None:
    exp = repo.get_experience(exp_id) if exp_id != NEW else Experience()
    if exp is None:
        return
    ui.clear_prefix("p_exp_fu_")
    st.session_state.update(_editor_state(exp))
    st.session_state["p_exp_sel"] = exp_id


def close_editor() -> None:
    st.session_state["p_exp_sel"] = None


def _from_editor(exp_id: str) -> Experience:
    s = st.session_state
    data = {f: s.get(k) for k, f in FIELDS.items()}
    data |= {
        "keywords": _split(s.get("p_exp_kw", "")),
        "competencies": _split(s.get("p_exp_comp", "")),
        "missing_info": s.get("p_exp_missing", []),
        "follow_up_questions": s.get("p_exp_followups", []),
    }
    if exp_id != NEW:
        data["id"] = exp_id
        data["created_at"] = s.get("p_exp_created")
    data = {k: v for k, v in data.items() if v is not None}
    return Experience(**data)


def _analysis_updates(res) -> dict:
    return {
        "p_exp_S": res.situation,
        "p_exp_T": res.task,
        "p_exp_A": res.action,
        "p_exp_R": res.result,
        "p_exp_kw": ", ".join(res.keywords),
        "p_exp_comp": ", ".join(res.competencies),
        "p_exp_missing": res.missing_info,
        "p_exp_followups": res.follow_up_questions,
    }


@st.dialog("경험 삭제")
def confirm_delete(exp_id: str, title: str) -> None:
    st.write(f"**{title or '제목 없음'}** 경험을 삭제할까요? 삭제하면 되돌릴 수 없습니다.")
    c1, c2 = st.columns(2)
    if c1.button("삭제", type="primary", use_container_width=True):
        repo.delete_experience(exp_id)
        st.session_state["p_exp_sel"] = None
        st.session_state["_toast"] = "경험을 삭제했습니다."
        st.rerun()
    if c2.button("취소", use_container_width=True):
        st.rerun()


# ─────────────────────────── 화면 ───────────────────────────
ui.bootstrap()
ui.sidebar_status()
ui.hero("경험 저장소", "경험을 자유롭게 적고 AI로 STAR 구조화하세요. 저장한 경험은 모든 자기소개서와 이력서에서 다시 쓰입니다.")
ui.init("p_exp_sel", None)

exps = repo.list_experiences()
usage = repo.experience_usage()
selected = st.session_state["p_exp_sel"]
if selected not in (None, NEW) and not any(e.id == selected for e in exps):
    selected = st.session_state["p_exp_sel"] = None

left, right = st.columns([2, 3], gap="large")

# ── 왼쪽: 목록 + 필터
with left:
    top = st.columns([3, 2])
    top[0].markdown(f"#### 내 경험 <span class='muted'>{len(exps)}개</span>", unsafe_allow_html=True)
    top[1].button("새 경험 추가", icon=":material/add:", type="primary", use_container_width=True,
                  on_click=open_editor, args=(NEW,))

    all_comps = sorted({c for e in exps for c in e.competencies})
    with st.expander("검색 · 필터", expanded=False):
        ui.init("p_exp_q", "")
        ui.init("p_exp_ft", [])
        ui.init("p_exp_fc", [])
        st.session_state["p_exp_fc"] = [c for c in st.session_state["p_exp_fc"] if c in all_comps]
        st.text_input("검색 (제목·내용·키워드)", key="p_exp_q")
        st.multiselect("유형", EXPERIENCE_TYPES, key="p_exp_ft")
        st.multiselect("핵심 역량", all_comps, key="p_exp_fc")

    q = st.session_state["p_exp_q"].strip().lower()
    ft, fc = st.session_state["p_exp_ft"], st.session_state["p_exp_fc"]

    def _match(e: Experience) -> bool:
        if ft and e.type not in ft:
            return False
        if fc and not set(fc) & set(e.competencies):
            return False
        if q:
            hay = " ".join([e.title, e.organization, e.raw_text, *e.keywords, *e.competencies]).lower()
            return q in hay
        return True

    shown = [e for e in exps if _match(e)]
    if not exps:
        st.info("아직 저장된 경험이 없습니다. **새 경험 추가**를 눌러 첫 경험을 적어 보세요.", icon="💡")
    elif not shown:
        st.caption("조건에 맞는 경험이 없습니다.")

    for e in shown:
        with st.container(border=True):
            mark = "▶ " if e.id == selected else ""
            st.markdown(
                f"**{mark}{html.escape(e.title or '제목 없음')}**<br>"
                f"<span class='exp-meta'>{html.escape(' · '.join(x for x in (e.type, e.organization, e.period) if x))}</span>",
                unsafe_allow_html=True,
            )
            tags = ui.chips_html(e.competencies[:4], "comp")
            if e.missing_info:
                tags += ui.chips_html([f"보완 {len(e.missing_info)}"], "warn")
            if e.id in usage:
                tags += ui.chips_html([f"사용 {len(usage[e.id])}회"], "muted")
            if tags:
                st.markdown(tags, unsafe_allow_html=True)
            st.button("열기", key=f"open_{e.id}", on_click=open_editor, args=(e.id,), use_container_width=True)

    with st.expander("백업 · 복원", icon=":material/save:"):
        st.download_button(
            "전체 데이터 JSON 내보내기",
            json.dumps(repo.export_all(), ensure_ascii=False, indent=2),
            file_name="취업서류_백업.json",
            mime="application/json",
            use_container_width=True,
        )
        up = st.file_uploader("백업 파일 가져오기 (같은 항목은 덮어씁니다)", type="json")
        if up and st.button("가져오기", use_container_width=True):
            try:
                counts = repo.import_all(json.loads(up.getvalue().decode("utf-8")))
                ui.queue({}, toast=f"가져오기 완료: 경험 {counts['experiences']}개, 지원서 {counts['applications']}건")
                st.rerun()
            except Exception as ex:  # noqa: BLE001
                st.error(f"백업 파일을 읽지 못했습니다: {ex}")

# ── 오른쪽: 편집기
with right:
    if selected is None:
        with st.container(border=True):
            st.markdown("#### 경험을 선택하거나 새로 추가하세요")
            st.markdown(
                "경험은 **정리되지 않은 메모처럼** 적어도 괜찮습니다. 무슨 상황이었는지, 내가 맡은 일, 실제로 한 행동, "
                "그리고 결과를 생각나는 대로 적으면 AI가 STAR 구조로 나눠 드립니다.\n\n"
                "AI는 **적은 내용에 없는 사실을 만들지 않습니다.** 부족한 정보는 질문으로 알려 드려요."
            )
            ui.chips(["회사 경력", "인턴", "프로젝트", "대외활동", "아르바이트", "동아리", "수상 경력"], "muted")
    else:
        is_new = selected == NEW
        st.markdown(f"#### {'새 경험' if is_new else '경험 편집'}")

        ui.step(1, "기본 정보")
        c1, c2 = st.columns([1, 2])
        if st.session_state.get("p_exp_type") not in EXPERIENCE_TYPES:
            st.session_state["p_exp_type"] = EXPERIENCE_TYPES[0]
        c1.selectbox("유형", EXPERIENCE_TYPES, key="p_exp_type")
        c2.text_input("제목 *", key="p_exp_title", placeholder="예: 카페 아르바이트 재고 관리 개선")
        c3, c4 = st.columns(2)
        c3.text_input("소속 (회사·기관·학교)", key="p_exp_org")
        c4.text_input("역할 · 직책", key="p_exp_role")
        c5, c6, c7 = st.columns([2, 2, 1])
        c5.text_input("시작 (YYYY-MM)", key="p_exp_start", placeholder="2024-03")
        c6.text_input("종료 (YYYY-MM)", key="p_exp_end", placeholder="2024-08",
                      disabled=st.session_state.get("p_exp_ongoing", False))
        c7.checkbox("진행 중", key="p_exp_ongoing")
        bad_dates = [v for v in (st.session_state.get("p_exp_start", ""), st.session_state.get("p_exp_end", ""))
                     if v and not YM.match(v)]
        if bad_dates:
            st.caption(f":orange[날짜는 YYYY-MM 형식으로 입력하세요: {', '.join(bad_dates)}]")

        ui.step(2, "경험 원문", "자유롭게 적어 주세요. 이 내용이 모든 서류의 사실 근거가 됩니다.")
        st.text_area(
            "경험 원문 *",
            key="p_exp_raw",
            height=200,
            label_visibility="collapsed",
            placeholder="예) 주말 카페 아르바이트를 하며 재고가 자주 떨어지는 문제가 있었다. 사장님께 제안해서 엑셀로 재고표를 만들고…",
        )

        ui.step(3, "STAR 구조", "AI 분석 결과를 검토하고 직접 고칠 수 있습니다.")
        if st.button("AI로 STAR 분석하기", icon=":material/auto_awesome:", type="primary",
                     disabled=not st.session_state.get("p_exp_raw", "").strip()):
            if ui.require_api():
                try:
                    tmp = _from_editor(selected)
                    with st.spinner("경험을 STAR 구조로 분석하는 중…"):
                        res = star.analyze(type_=tmp.type, title=tmp.title, organization=tmp.organization,
                                           role=tmp.role, period=tmp.period, raw_text=tmp.raw_text)
                    ui.queue(_analysis_updates(res), toast="분석을 마쳤습니다. 내용을 검토한 뒤 저장하세요.")
                    st.rerun()
                except LLMError as ex:
                    st.error(str(ex))

        tabs = st.tabs(["편집", "미리보기"])
        with tabs[0]:
            for letter in "STAR":
                en, ko, _ = ui.STAR_META[letter]
                st.text_area(f"{letter} · {en} — {ko}", key=f"p_exp_{letter}", height=90)
            st.text_input("키워드 (쉼표로 구분)", key="p_exp_kw")
            st.text_input("핵심 역량 (쉼표로 구분)", key="p_exp_comp")
        with tabs[1]:
            for letter in "STAR":
                ui.star_card(letter, st.session_state.get(f"p_exp_{letter}", ""))
            ui.chips(_split(st.session_state.get("p_exp_kw", "")))
            ui.chips(_split(st.session_state.get("p_exp_comp", "")), "comp")

        missing = st.session_state.get("p_exp_missing", [])
        followups = st.session_state.get("p_exp_followups", [])
        if missing or followups:
            with st.container(border=True):
                st.markdown("**보완하면 더 설득력 있어져요**")
                ui.chips(missing, "warn")
                for i, fq in enumerate(followups):
                    st.text_input(fq, key=f"p_exp_fu_{i}", placeholder="알고 있는 사실만 적어 주세요 (모르면 비워 두기)")
                if followups and st.button("답변을 원문에 반영하고 다시 분석", icon=":material/refresh:"):
                    qa = [(fq, st.session_state.get(f"p_exp_fu_{i}", "")) for i, fq in enumerate(followups)]
                    merged = star.merge_follow_up(st.session_state.get("p_exp_raw", ""), qa)
                    if merged == st.session_state.get("p_exp_raw", ""):
                        st.warning("입력한 답변이 없습니다.")
                    elif ui.require_api():
                        try:
                            tmp = _from_editor(selected)
                            with st.spinner("보완 내용을 반영해 다시 분석하는 중…"):
                                res = star.analyze(type_=tmp.type, title=tmp.title, organization=tmp.organization,
                                                   role=tmp.role, period=tmp.period, raw_text=merged)
                            upd = _analysis_updates(res) | {"p_exp_raw": merged}
                            upd |= {f"p_exp_fu_{i}": None for i in range(len(followups))}
                            ui.queue(upd, toast="보완 내용을 반영했습니다. 검토 후 저장하세요.")
                            st.rerun()
                        except LLMError as ex:
                            st.error(str(ex))

        if not is_new and selected in usage:
            st.caption("이 경험을 사용한 지원서: " + ", ".join(f"{a.company}({a.position})" for a in usage[selected]))

        st.divider()
        b1, b2, b3 = st.columns([2, 1, 1])
        if b1.button("저장", icon=":material/save:", type="primary", use_container_width=True):
            exp = _from_editor(selected)
            if not exp.title.strip() or not exp.raw_text.strip():
                st.error("제목과 경험 원문은 필수입니다.")
            elif bad_dates:
                st.error("날짜 형식을 확인해 주세요 (YYYY-MM).")
            else:
                if exp.ongoing:
                    exp.end_date = ""
                repo.save_experience(exp)
                ui.queue({"p_exp_sel": exp.id, "p_exp_created": exp.created_at}, toast="경험을 저장했습니다.")
                st.rerun()
        b2.button("닫기", use_container_width=True, on_click=close_editor)
        if not is_new and b3.button("삭제", icon=":material/delete:", use_container_width=True):
            confirm_delete(selected, st.session_state.get("p_exp_title", ""))
