import html

import streamlit as st

from core import exporter, interview, ui
from core.llm import LLMError
from db import repository as repo
from db.models import INTERVIEW_CATEGORIES, InterviewItem

STAR_FIELDS = {"S": "situation", "T": "task", "A": "action", "R": "result"}
NONE = ""

ui.bootstrap()
ui.sidebar_status()
ui.hero("면접 준비", "작성한 자기소개서와 경험으로 예상 질문·꼬리 질문·직무 질문을 만들고, STAR 답변 연습과 평가를 받습니다.")

apps = repo.list_applications()
app_map = {a.id: a for a in apps}
exps = repo.list_experiences()
exp_map = {e.id: e for e in exps}

if not exps:
    st.warning("저장된 경험이 없습니다. 먼저 경험 저장소에서 경험을 추가해 주세요.", icon="📂")
    st.page_link("views/1_경험_저장소.py", label="경험 저장소로 이동", icon=":material/arrow_forward:")
    st.stop()

# ── 1단계: 대상 선택
ui.init("p_iv_app", apps[0].id if apps else NONE)
if st.session_state["p_iv_app"] not in app_map:
    st.session_state["p_iv_app"] = NONE
with st.container(border=True):
    ui.step(1, "면접 대상", "저장된 지원서를 고르거나, 지원서 없이 직무만으로 준비할 수 있습니다.")
    st.selectbox("지원서", [NONE, *app_map], key="p_iv_app",
                 format_func=lambda i: "지원서 없이 (직무 직접 입력)" if i == NONE
                 else f"{app_map[i].company} · {app_map[i].position} ({app_map[i].status})")
    app_id = st.session_state["p_iv_app"]
    app = app_map.get(app_id)
    if app:
        company, position, posting = app.company, app.position, app.posting_analysis
        answers = repo.list_answers(app.id)
        st.caption(f"자기소개서 문항 {len([a for a in answers if a.content.strip()])}개가 질문 생성에 사용됩니다.")
    else:
        ui.init("p_iv_position", "")
        ui.init("p_iv_company", "")
        c1, c2 = st.columns(2)
        c1.text_input("지원 직무 *", key="p_iv_position", placeholder="예: 서비스 기획")
        c2.text_input("기업명 (선택)", key="p_iv_company")
        company, position, posting, answers = st.session_state["p_iv_company"], st.session_state["p_iv_position"].strip(), {}, []

used_ids = list(dict.fromkeys(i for a in answers for i in a.used_experience_ids if i in exp_map))
context_exps = [exp_map[i] for i in used_ids] or exps  # 답변 생성·평가의 사실 근거


def _items() -> list[InterviewItem]:
    return repo.list_interviews(app_id, position if not app else "")


# ── 2단계: 질문 생성
with st.container(border=True):
    ui.step(2, "예상 질문 만들기")
    has_cl = any(a.content.strip() for a in answers)
    cols = st.columns(3)
    defaults = {"자소서 기반": 3 if has_cl else 0, "꼬리 질문": 3, "직무 질문": 3}
    help_ = {"자소서 기반": "작성한 자기소개서 내용을 파고드는 질문",
             "꼬리 질문": "선택한 경험의 행동·판단·결과를 깊게 묻는 질문",
             "직무 질문": "지원 직무 역량·지식·상황 대처 질문"}
    counts = {}
    for col, cat in zip(cols, INTERVIEW_CATEGORIES):
        key = f"p_iv_n_{INTERVIEW_CATEGORIES.index(cat)}"
        ui.init(key, defaults[cat])
        if cat == "자소서 기반" and not has_cl:
            st.session_state[key] = 0
        counts[cat] = col.number_input(cat, key=key, min_value=0, max_value=10, help=help_[cat],
                                       disabled=cat == "자소서 기반" and not has_cl)
    ui.init("p_iv_exps", [e.id for e in context_exps[:3]])
    st.session_state["p_iv_exps"] = [i for i in st.session_state["p_iv_exps"] if i in exp_map]
    st.multiselect("꼬리 질문을 만들 경험", list(exp_map), key="p_iv_exps",
                   format_func=lambda i: f"{exp_map[i].title} ({exp_map[i].type})",
                   disabled=not counts["꼬리 질문"])

    if st.button("질문 생성", icon=":material/auto_awesome:", type="primary", disabled=not any(counts.values())):
        if ui.require_api():
            try:
                fq_exps = [exp_map[i] for i in st.session_state["p_iv_exps"]]
                with st.spinner("면접 예상 질문을 만드는 중…"):
                    qs = interview.generate_questions(
                        company=company, position=position, posting_analysis=posting, answers=answers,
                        experiences=fq_exps if counts["꼬리 질문"] else context_exps, counts=counts)
                start = len(_items())
                for n, qq in enumerate(qs):
                    repo.save_interview(InterviewItem(
                        application_id=app_id, position=position if not app else app.position,
                        category=qq.category, question=qq.question, intent=qq.intent,
                        experience_id=qq.experience_id, order_no=start + n))
                ui.queue({}, toast=f"질문 {len(qs)}개를 만들었습니다.")
                st.rerun()
            except LLMError as ex:
                st.error(str(ex))

# ── 3단계: 답변 연습
items = _items()
st.write("")
ui.step(3, "답변 연습", f"질문 {len(items)}개")
if not items:
    st.caption("질문을 생성하면 여기에 표시됩니다.")
else:
    f1, f2, f3 = st.columns([3, 1, 1])
    cat_filter = f1.pills("유형", INTERVIEW_CATEGORIES, selection_mode="multi", key="iv_filter",
                          label_visibility="collapsed")
    title = f"{company} {position}".strip() or "면접"
    f2.download_button("Markdown 내보내기", exporter.interview_md(title, items), file_name=f"{title}_면접준비.md",
                       use_container_width=True)
    if f3.button("전체 삭제", icon=":material/delete_sweep:", use_container_width=True):
        for it in items:
            repo.delete_interview(it.id)
        ui.queue({}, toast="질문을 모두 삭제했습니다.")
        st.rerun()

    for it in items:
        if cat_filter and it.category not in cat_filter:
            continue
        exp = exp_map.get(it.experience_id)
        basis = [exp] if exp else context_exps
        with st.container(border=True):
            tags = ui.chips_html([it.category], "type")
            if exp:
                tags += ui.chips_html([exp.title], "muted")
            if it.evaluation:
                tags += ui.chips_html([f"평가 논리 {it.evaluation.get('logic', 0)} · 구체 {it.evaluation.get('specificity', 0)}"], "comp")
            st.markdown(tags, unsafe_allow_html=True)
            st.markdown(f"**Q. {html.escape(it.question)}**", unsafe_allow_html=True)
            if it.intent:
                st.caption(f"질문 의도: {it.intent}")

            with st.expander("답변 연습", icon=":material/mic:"):
                a1, a2 = st.columns([1, 1], gap="large")
                with a1:
                    st.markdown("**STAR 모범 답변**")
                    if st.button("모범 답변 생성" if not it.model_answer else "다시 생성", key=f"iv_gen_{it.id}",
                                 icon=":material/auto_awesome:", use_container_width=True):
                        if ui.require_api():
                            try:
                                with st.spinner("STAR 방식 답변을 작성하는 중…"):
                                    res = interview.star_answer(question=it.question, intent=it.intent,
                                                                company=company, position=position, experiences=basis)
                                it.model_answer, it.tips = res.answer, res.tips
                                repo.save_interview(it)
                                st.rerun()
                            except LLMError as ex:
                                st.error(str(ex))
                    if it.model_answer:
                        ui.html_box(html.escape(it.model_answer).replace("\n", "<br>"))
                        for tip in it.tips:
                            st.caption(f"💡 {tip}")
                    else:
                        st.caption("경험 자료만으로 1분 분량의 답변을 만들어 드립니다.")
                with a2:
                    st.markdown("**내 답변**")
                    ua_key = f"p_iv_ua_{it.id}"
                    ui.init(ua_key, it.user_answer)
                    st.text_area("내 답변", key=ua_key, height=180, label_visibility="collapsed",
                                 placeholder="실제로 말할 답변을 적어 보세요.")
                    b1, b2 = st.columns(2)
                    if b1.button("저장", key=f"iv_save_{it.id}", use_container_width=True):
                        it.user_answer = st.session_state[ua_key]
                        repo.save_interview(it)
                        ui.queue({}, toast="답변을 저장했습니다.")
                        st.rerun()
                    if b2.button("평가받기", key=f"iv_eval_{it.id}", type="primary", use_container_width=True,
                                 disabled=not st.session_state[ua_key].strip()):
                        if ui.require_api():
                            try:
                                with st.spinner("답변의 논리성과 구체성을 평가하는 중…"):
                                    ev = interview.evaluate(it.question, st.session_state[ua_key], basis)
                                it.user_answer = st.session_state[ua_key]
                                it.evaluation = ev.model_dump()
                                repo.save_interview(it)
                                st.rerun()
                            except LLMError as ex:
                                st.error(str(ex))
                    ev = it.evaluation
                    if ev:
                        if it.user_answer != st.session_state[ua_key]:
                            st.caption(":orange[답변이 수정되어 아래 평가는 이전 답변 기준입니다.]")
                        e1, e2 = st.columns(2)
                        e1.metric("논리성", ev.get("logic", 0), border=True)
                        e2.metric("구체성", ev.get("specificity", 0), border=True)
                        star_c = ev.get("star", {})
                        st.markdown("".join(
                            ui.chips_html([f"{'✓' if star_c.get(f) else '✗'} {L}"], "comp" if star_c.get(f) else "warn")
                            for L, f in STAR_FIELDS.items()), unsafe_allow_html=True)
                        if star_c.get("comment"):
                            st.caption(star_c["comment"])
                        if ev.get("summary"):
                            st.markdown(f"**총평** {html.escape(ev['summary'])}", unsafe_allow_html=True)
                        for s_ in ev.get("strengths", []):
                            st.markdown(f"✅ {html.escape(s_)}", unsafe_allow_html=True)
                        for s_ in ev.get("improvements", []):
                            st.markdown(f"🔧 {html.escape(s_)}", unsafe_allow_html=True)
                st.button("질문 삭제", key=f"iv_del_{it.id}", icon=":material/delete:",
                          on_click=repo.delete_interview, args=(it.id,))
