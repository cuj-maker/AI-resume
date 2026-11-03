import html
from datetime import date

import streamlit as st

from core import exporter, matcher, reviewer, ui, verifier, writer
from core.llm import LLMError
from db import repository as repo
from db.models import APP_STATUSES, CHAR_PRESETS, TONES, Answer, Application, new_id

QUICK_FIX = ["더 짧게", "더 구체적으로", "더 논리적으로", "직무 연관성 강조", "첫 문장 강화"]
STAR_FIELDS = {"S": "situation", "T": "task", "A": "action", "R": "result"}


# ─────────────────────────── 상태 ───────────────────────────
def _cl() -> dict:
    """위젯이 아닌 작성 상태(추천, 검증·첨삭 결과 등)."""
    if "cl" not in st.session_state:
        st.session_state["cl"] = {"app_id": None, "posting": {}, "qids": [], "q": {}}
    return st.session_state["cl"]


def _qk(qid: str, name: str) -> str:
    return f"p_q_{qid}_{name}"


def add_question(text: str = "", limit: int = 0, spaces: bool = True, content: str = "",
                 used: list | None = None, verification: list | None = None) -> None:
    cl = _cl()
    qid = new_id()[:8]
    cl["qids"].append(qid)
    cl["q"][qid] = {"recs": [], "verification": verification or [], "verified_text": content if verification else "",
                    "used_ids": used or [], "review": None, "review_text": "", "prev_answer": None}
    st.session_state[_qk(qid, "text")] = text
    st.session_state[_qk(qid, "limit")] = int(limit)
    st.session_state[_qk(qid, "spaces")] = spaces
    st.session_state[_qk(qid, "ans")] = content
    st.session_state[_qk(qid, "sel")] = list(used or [])


def remove_question(qid: str) -> None:
    cl = _cl()
    cl["qids"] = [q for q in cl["qids"] if q != qid]
    cl["q"].pop(qid, None)
    ui.clear_prefix(f"p_q_{qid}_")


def set_limit(qid: str, n: int) -> None:
    st.session_state[_qk(qid, "limit")] = n


def reset_all() -> None:
    ui.clear_prefix("p_cl_", "p_q_")
    st.session_state.pop("cl", None)
    _cl()
    add_question()


def load_application(app_id: str) -> None:
    app = repo.get_application(app_id)
    if not app:
        return
    reset_all()
    cl = _cl()
    remove_question(cl["qids"][0])
    cl["app_id"] = app.id
    cl["posting"] = app.posting_analysis or {}
    st.session_state.update({
        "p_cl_company": app.company, "p_cl_position": app.position, "p_cl_posting": app.job_posting,
        "p_cl_info": app.company_info, "p_cl_tone": app.tone if app.tone in TONES else TONES[0],
        "p_cl_status": app.status if app.status in APP_STATUSES else APP_STATUSES[0],
        "p_cl_date": date.fromisoformat(app.applied_date) if app.applied_date else None,
    })
    for a in repo.list_answers(app.id):
        add_question(a.question, a.char_limit, a.count_spaces, a.content, a.used_experience_ids, a.verification)
    if not cl["qids"]:
        add_question()


def build_records() -> tuple[Application, list[Answer]]:
    s, cl = st.session_state, _cl()
    d = s.get("p_cl_date")
    app = Application(
        company=s.get("p_cl_company", "").strip(),
        position=s.get("p_cl_position", "").strip(),
        job_posting=s.get("p_cl_posting", ""),
        company_info=s.get("p_cl_info", ""),
        tone=s.get("p_cl_tone", TONES[0]),
        posting_analysis=cl["posting"],
        status=s.get("p_cl_status", APP_STATUSES[0]),
        applied_date=d.isoformat() if d else "",
    )
    if cl["app_id"]:
        old = repo.get_application(cl["app_id"])
        app.id = cl["app_id"]
        if old:
            app.created_at = old.created_at
            app.memo = old.memo
    answers = []
    for qid in cl["qids"]:
        q = cl["q"][qid]
        content = s.get(_qk(qid, "ans"), "")
        answers.append(Answer(
            application_id=app.id,
            question=s.get(_qk(qid, "text"), ""),
            char_limit=int(s.get(_qk(qid, "limit"), 0) or 0),
            count_spaces=bool(s.get(_qk(qid, "spaces"), True)),
            content=content,
            used_experience_ids=q["used_ids"],
            # 수정 후 재검증하지 않은 결과는 저장하지 않는다
            verification=q["verification"] if q.get("verified_text") == content else [],
        ))
    return app, answers


def _save(version_label: str | None = None, final: bool = False) -> None:
    app, answers = build_records()
    repo.save_application(app, answers)
    _cl()["app_id"] = app.id
    msg = f"{app.company} 지원서를 저장했습니다."
    if version_label is not None or final:
        v = repo.save_version(app.id, version_label or "", is_final=final)
        msg = f"'{v.label}'을(를) {'최종 제출본으로 ' if final else ''}저장했습니다."
        # 최종 제출 시 바뀐 상태·날짜를 화면에 반영
        cur = repo.get_application(app.id)
        ui.queue({"p_cl_status": cur.status,
                  "p_cl_date": date.fromisoformat(cur.applied_date) if cur.applied_date else None}, toast=msg)
    else:
        ui.queue({}, toast=msg)
    st.rerun()


# ─────────────────────────── 초기화 ───────────────────────────
ui.bootstrap()
ui.sidebar_status()
if load_id := st.session_state.pop("cl_load", None):
    load_application(load_id)
cl = _cl()
if not cl["qids"]:
    add_question()
for k, v in {"p_cl_company": "", "p_cl_position": "", "p_cl_posting": "", "p_cl_info": "",
             "p_cl_tone": TONES[0], "p_cl_status": APP_STATUSES[0], "p_cl_date": None}.items():
    ui.init(k, v)
for qid in cl["qids"]:  # 이전 버전 상태 호환
    cl["q"][qid].setdefault("review", None)
    cl["q"][qid].setdefault("review_text", "")
    cl["q"][qid].setdefault("prev_answer", None)

exps = repo.list_experiences()
exp_map = {e.id: e for e in exps}

# ─────────────────────────── 화면 ───────────────────────────
ui.hero("자기소개서 작성", "공고와 문항을 입력하면 저장된 경험 중 가장 잘 맞는 것을 골라 STAR 구조로 답변을 쓰고, 첨삭까지 해 드립니다.")

head = st.columns([4, 1])
if cl["app_id"]:
    fv = repo.final_version(cl["app_id"])
    head[0].markdown(
        f"<span class='muted'>편집 중: 저장된 지원서</span> "
        + ui.chips_html([st.session_state["p_cl_status"]], "type")
        + (ui.chips_html([f"최종 제출본: {fv.label}"], "comp") if fv else ""),
        unsafe_allow_html=True,
    )
else:
    head[0].caption("새 지원서")
head[1].button("새로 작성", icon=":material/restart_alt:", use_container_width=True, on_click=reset_all)

if not exps:
    st.warning("저장된 경험이 없습니다. 먼저 경험 저장소에서 경험을 추가해 주세요.", icon="📂")
    st.page_link("views/1_경험_저장소.py", label="경험 저장소로 이동", icon=":material/arrow_forward:")

# ── 1단계: 지원 정보
with st.container(border=True):
    ui.step(1, "지원 정보", "기업명과 직무는 필수, 공고는 붙여 넣으면 더 정확해집니다.")
    c1, c2, c3 = st.columns([2, 2, 1])
    c1.text_input("기업명 *", key="p_cl_company")
    c2.text_input("직무명 *", key="p_cl_position")
    c3.selectbox("문체", TONES, key="p_cl_tone")
    c4, c5 = st.columns(2)
    c4.text_area("채용공고 / 직무 설명", key="p_cl_posting", height=160, placeholder="채용공고 내용을 붙여 넣으세요.")
    c5.text_area("인재상 / 기업 정보 (선택)", key="p_cl_info", height=160,
                 placeholder="AI는 여기에 적은 기업 정보만 사용하며, 기업에 대해 추측하지 않습니다.")
    c6, c7, _ = st.columns([1, 1, 2])
    c6.selectbox("지원 상태", APP_STATUSES, key="p_cl_status")
    c7.date_input("지원 날짜", key="p_cl_date", format="YYYY-MM-DD")

    pa_col, chip_col = st.columns([1, 4])
    if pa_col.button("공고 분석", icon=":material/search:", use_container_width=True,
                     disabled=not (st.session_state["p_cl_posting"].strip() or st.session_state["p_cl_info"].strip())):
        if ui.require_api():
            try:
                with st.spinner("기업과 직무에 필요한 역량을 분석하는 중…"):
                    res = matcher.analyze_posting(st.session_state["p_cl_company"], st.session_state["p_cl_position"],
                                                  st.session_state["p_cl_posting"], st.session_state["p_cl_info"])
                cl["posting"] = res.model_dump()
                st.rerun()
            except LLMError as ex:
                st.error(str(ex))
    with chip_col:
        p = cl["posting"]
        if p:
            for label, field, kind in (("필수", "required_skills", ""), ("우대", "preferred", "muted"),
                                       ("키워드", "keywords", "comp"), ("인재상", "culture", "warn")):
                if p.get(field):
                    st.markdown(f"<span class='muted'>{label}</span> " + ui.chips_html(p[field], kind), unsafe_allow_html=True)
        else:
            st.caption("공고를 분석하면 요구 역량과 키워드를 추출해 경험 추천과 작성에 반영합니다.")

basics_ok = bool(st.session_state["p_cl_company"].strip() and st.session_state["p_cl_position"].strip())

# ── 2단계: 문항별 작성
st.write("")
ui.step(2, "문항별 작성", "문항마다 경험을 추천받고 답변을 생성·첨삭하세요.")
labels = [f"문항 {i + 1}" for i in range(len(cl["qids"]))]
tabs = st.tabs(labels + ["＋ 문항 추가"])

for qid, tab in zip(list(cl["qids"]), tabs[:-1]):
    q = cl["q"][qid]
    with tab:
        st.text_area("자기소개서 문항 *", key=_qk(qid, "text"), height=80,
                     placeholder="예: 지원 직무와 관련해 문제를 해결했던 경험을 구체적으로 서술해 주세요.")
        # 글자 수 설정: 프리셋 + 직접 입력 + 공백 기준
        lc = st.columns([1] * len(CHAR_PRESETS) + [1.1, 1.6])
        for col, n in zip(lc, CHAR_PRESETS):
            col.button(f"{n:,}자", key=f"preset_{qid}_{n}", on_click=set_limit, args=(qid, n), use_container_width=True,
                       type="primary" if st.session_state[_qk(qid, "limit")] == n else "secondary")
        lc[len(CHAR_PRESETS)].button("제한 없음", key=f"preset_{qid}_0", on_click=set_limit, args=(qid, 0),
                                     use_container_width=True)
        lc[-1].number_input("직접 입력", key=_qk(qid, "limit"), min_value=0, max_value=5000, step=50,
                            label_visibility="collapsed", help="원하는 글자 수를 직접 입력 (0이면 제한 없음)")
        st.toggle("공백 포함 글자 수 기준 (끄면 공백 제외 기준)", key=_qk(qid, "spaces"))

        question = st.session_state[_qk(qid, "text")]
        limit = int(st.session_state[_qk(qid, "limit")] or 0)
        spaces = st.session_state[_qk(qid, "spaces")]

        left, right = st.columns([2, 3], gap="large")

        # 경험 추천·선택
        with left:
            st.markdown("**사용할 경험**")
            if st.button("AI 경험 추천", key=f"rec_{qid}", icon=":material/recommend:", use_container_width=True,
                         disabled=not (question.strip() and exps)):
                if ui.require_api():
                    try:
                        with st.spinner("문항에 맞는 경험을 고르는 중…"):
                            recs = matcher.recommend(question, st.session_state["p_cl_position"], cl["posting"], exps)
                        q["recs"] = [r.model_dump() for r in recs]
                        ui.queue({_qk(qid, "sel"): [r.experience_id for r in recs[:2]]},
                                 toast="추천 경험 상위 2개를 선택했습니다.")
                        st.rerun()
                    except LLMError as ex:
                        st.error(str(ex))
            for r in q["recs"]:
                e = exp_map.get(r["experience_id"])
                if e:
                    st.markdown(
                        f"<div class='rec'><span class='rec-score'>{r['score']}점</span> "
                        f"<b>{html.escape(e.title)}</b><br><span class='muted'>{html.escape(r['reason'])}</span></div>",
                        unsafe_allow_html=True,
                    )
            sel_key = _qk(qid, "sel")
            st.session_state[sel_key] = [i for i in st.session_state.get(sel_key, []) if i in exp_map]
            st.multiselect("경험 선택", list(exp_map), key=sel_key, label_visibility="collapsed",
                           format_func=lambda i: f"{exp_map[i].title} ({exp_map[i].type})",
                           placeholder="경험을 직접 선택하거나 추천을 받으세요")
            for eid in st.session_state[sel_key]:
                with st.expander(exp_map[eid].title):
                    for letter, field in STAR_FIELDS.items():
                        ui.star_card(letter, getattr(exp_map[eid], field))

        # 생성·편집·검증·첨삭
        with right:
            ans_key = _qk(qid, "ans")
            ui.init(ans_key, "")
            selected = [exp_map[i] for i in st.session_state[sel_key]]
            basis = [exp_map[i] for i in (q["used_ids"] or st.session_state[sel_key]) if i in exp_map]

            def _verify_and_set(new_text: str, used_ids: list[str], toast: str, keep_prev: bool = False) -> None:
                used = [exp_map[i] for i in used_ids if i in exp_map]
                with st.spinner("작성된 문장의 근거를 확인하는 중…"):
                    items = verifier.verify(new_text, used, st.session_state["p_cl_info"]) if used else []
                if keep_prev:
                    q["prev_answer"] = st.session_state[ans_key]
                q["used_ids"] = used_ids
                q["verification"] = [i.model_dump() for i in items]
                q["verified_text"] = new_text
                ui.queue({ans_key: new_text}, toast=toast)
                st.rerun()

            def _run_generate(previous: str = "", instruction: str = "") -> None:
                if not basics_ok:
                    st.error("기업명과 직무명을 먼저 입력해 주세요.")
                    return
                if not ui.require_api():
                    return
                try:
                    with st.spinner("자기소개서를 작성하는 중…"):
                        res = writer.generate_answer(
                            company=st.session_state["p_cl_company"], position=st.session_state["p_cl_position"],
                            question=question, char_limit=limit, count_spaces=spaces,
                            tone=st.session_state["p_cl_tone"], posting_analysis=cl["posting"],
                            company_info=st.session_state["p_cl_info"], experiences=selected,
                            previous=previous, instruction=instruction,
                        )
                    _verify_and_set(res.answer, res.used_experience_ids, "답변을 작성하고 사실 검증까지 마쳤습니다.",
                                    keep_prev=bool(previous))
                except LLMError as ex:
                    st.error(str(ex))

            has_answer = bool(st.session_state[ans_key].strip())
            g1, g2 = st.columns([3, 1])
            if g1.button("답변 생성" if not has_answer else "처음부터 다시 생성", key=f"gen_{qid}",
                         icon=":material/auto_awesome:", type="primary", use_container_width=True,
                         disabled=not (question.strip() and selected)):
                _run_generate()
            if q.get("prev_answer") is not None:
                if g2.button("되돌리기", key=f"undo_{qid}", icon=":material/undo:", use_container_width=True,
                             help="첨삭·재작성·분량 조정 전 답변으로 돌아갑니다"):
                    prev = q["prev_answer"]
                    q["prev_answer"] = None
                    ui.queue({ans_key: prev}, toast="이전 답변으로 되돌렸습니다.")
                    st.rerun()

            st.text_area("답변", key=ans_key, height=320, label_visibility="collapsed",
                         placeholder="생성된 답변이 여기에 표시되며, 직접 고칠 수 있습니다.")
            text = st.session_state[ans_key]

            # 글자 수: 공백 포함/제외 모두 표시
            n_with, n_without = writer.count_chars(text, True), writer.count_chars(text, False)
            n = n_with if spaces else n_without
            status = writer.length_status(text, limit, spaces)
            m1, m2 = st.columns([3, 1.4])
            with m1:
                if limit:
                    color = {"ok": "green", "short": "orange", "over": "red"}[status]
                    msg = {"ok": "적정", "short": f"{int(limit * 0.9):,}자 이상 권장", "over": f"{n - limit:,}자 초과"}[status]
                    st.progress(min(n / limit, 1.0))
                    st.caption(f":{color}[{n:,} / {limit:,}자 ({'공백 포함' if spaces else '공백 제외'} 기준) · {msg}]  \n"
                               f"공백 포함 {n_with:,}자 · 공백 제외 {n_without:,}자")
                else:
                    st.caption(f"공백 포함 {n_with:,}자 · 공백 제외 {n_without:,}자")
            if limit and text.strip() and status in ("short", "over"):
                if m2.button("축약" if status == "over" else "확장", key=f"fit_{qid}", icon=":material/straighten:",
                             use_container_width=True, help="목표 글자 수(90~100%)에 맞춰 자동으로 줄이거나 늘립니다"):
                    if not basis:
                        st.error("분량 조정의 근거가 될 경험을 선택해 주세요.")
                    elif ui.require_api():
                        try:
                            with st.spinner("목표 글자 수에 맞추는 중…"):
                                fitted = writer.fit_length(text, limit, spaces, basis)
                            if fitted == text:
                                st.warning("더 나은 분량으로 조정하지 못했습니다. 다시 시도하거나 직접 다듬어 주세요.")
                            else:
                                _verify_and_set(fitted, [e.id for e in basis], "목표 글자 수에 맞췄습니다.", keep_prev=True)
                        except LLMError as ex:
                            st.error(str(ex))

            if text.strip():
                t_ver, t_rev, t_re = st.tabs(["사실 검증", "AI 첨삭", "수정 지시로 다시 쓰기"])

                # 사실 검증
                with t_ver:
                    ver = q["verification"]
                    stale = q.get("verified_text") != text
                    vc1, vc2 = st.columns([3, 1])
                    if not ver or stale:
                        vc1.markdown("<span class='chip warn'>수정됨 · 다시 검증 필요</span>" if stale and ver
                                     else "<span class='chip muted'>미검증</span>", unsafe_allow_html=True)
                    else:
                        bad = [v for v in ver if not v.get("supported", True)]
                        vc1.markdown(f"<span class='chip warn'>근거 없는 문장 {len(bad)}개 / {len(ver)}</span>" if bad
                                     else f"<span class='chip comp'>모든 문장 근거 확인 ({len(ver)})</span>",
                                     unsafe_allow_html=True)
                    if vc2.button("검증하기", key=f"ver_{qid}", use_container_width=True):
                        if not basis:
                            st.error("검증에 사용할 경험을 선택해 주세요.")
                        elif ui.require_api():
                            try:
                                with st.spinner("문장별 근거를 확인하는 중…"):
                                    items = verifier.verify(text, basis, st.session_state["p_cl_info"])
                                q["verification"] = [i.model_dump() for i in items]
                                q["verified_text"] = text
                                st.rerun()
                            except LLMError as ex:
                                st.error(str(ex))
                    if ver and not stale:
                        if any(not v.get("supported", True) for v in ver):
                            ui.html_box(verifier.highlight(text, ver))
                            st.caption("빨간 표시 문장은 경험 자료에서 근거를 찾지 못했습니다. 마우스를 올리면 이유가 보입니다.")
                        with st.expander("문장별 근거 보기"):
                            for v in ver:
                                icon = "✅" if v.get("supported", True) else "⚠️"
                                st.markdown(f"{icon} {html.escape(v['sentence'])}  \n"
                                            f"<span class='muted'>└ {html.escape(v.get('source', ''))}</span>",
                                            unsafe_allow_html=True)
                    if "[보완 필요" in text:
                        st.info("답변에 `[보완 필요]` 표시가 있습니다. 해당 정보를 경험 저장소에 보완하거나 직접 채워 주세요.", icon="✏️")

                # AI 첨삭
                with t_rev:
                    rv = q.get("review")
                    rv_stale = rv is not None and q.get("review_text") != text
                    rc1, rc2 = st.columns([3, 1])
                    rc1.caption("자연스러움 · 중복 표현 · 논리 흐름 · STAR 구조 · 직무 연관성 · 구체성 · 근거 부족을 점검합니다. "
                                "첨삭본에도 새로운 사실은 추가되지 않습니다.")
                    if rc2.button("첨삭 받기" if not rv else "다시 첨삭", key=f"review_{qid}", type="primary",
                                  use_container_width=True):
                        if not basis:
                            st.error("첨삭의 근거가 될 경험을 선택해 주세요.")
                        elif ui.require_api():
                            try:
                                with st.spinner("자기소개서를 첨삭하는 중…"):
                                    res = reviewer.review(
                                        question=question, answer=text, company=st.session_state["p_cl_company"],
                                        position=st.session_state["p_cl_position"], posting_analysis=cl["posting"],
                                        experiences=basis, char_limit=limit, count_spaces=spaces)
                                q["review"] = res.model_dump()
                                q["review_text"] = text
                                st.rerun()
                            except LLMError as ex:
                                st.error(str(ex))
                    if rv:
                        if rv_stale:
                            st.caption(":orange[답변이 수정되어 아래 첨삭은 이전 답변 기준입니다.]")
                        sc = rv["scores"]
                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("자연스러움", sc["naturalness"], border=True)
                        k2.metric("논리 흐름", sc["logic"], border=True)
                        k3.metric("직무 연관성", sc["job_relevance"], border=True)
                        k4.metric("구체성", sc["specificity"], border=True)

                        star_c = rv["star_check"]
                        st.markdown(
                            "**STAR 구조** " + "".join(
                                ui.chips_html([f"{'✓' if star_c[f] else '✗'} {L}"], "comp" if star_c[f] else "warn")
                                for L, f in STAR_FIELDS.items()),
                            unsafe_allow_html=True)
                        if star_c.get("comment"):
                            st.caption(star_c["comment"])
                        if rv.get("flow_feedback"):
                            st.markdown(f"**논리 흐름** — {html.escape(rv['flow_feedback'])}", unsafe_allow_html=True)
                        if rv.get("job_relevance_comment"):
                            st.markdown(f"**직무 연관성** — {html.escape(rv['job_relevance_comment'])}", unsafe_allow_html=True)
                        if rv["duplicates"]:
                            st.markdown("**중복 표현** " + ui.chips_html(rv["duplicates"], "warn"), unsafe_allow_html=True)
                        if rv["abstract_expressions"]:
                            st.markdown("**추상적 표현 → 구체적 표현**")
                            for r in rv["abstract_expressions"]:
                                st.markdown(
                                    f"<div class='rec'><s>{html.escape(r['original'])}</s> → <b>{html.escape(r['suggestion'])}</b>"
                                    f"<br><span class='muted'>{html.escape(r.get('reason', ''))}</span></div>",
                                    unsafe_allow_html=True)
                        if rv["missing_evidence"]:
                            st.markdown("**성과·수치 근거 부족**")
                            for g in rv["missing_evidence"]:
                                st.markdown(f"- {html.escape(g['sentence'])}  \n  <span class='chip warn'>필요: {html.escape(g['need'])}</span>",
                                            unsafe_allow_html=True)
                        if rv.get("revised"):
                            st.markdown("**첨삭본**")
                            ui.html_box(html.escape(rv["revised"]).replace("\n", "<br>"))
                            rn = writer.count_chars(rv["revised"], spaces)
                            st.caption(f"{rn:,}자" + (f" / {limit:,}자" if limit else ""))
                            if st.button("첨삭본 적용", key=f"apply_rev_{qid}", icon=":material/check:",
                                         disabled=rv_stale or rv["revised"] == text):
                                try:
                                    _verify_and_set(rv["revised"], [e.id for e in basis],
                                                    "첨삭본을 적용하고 사실 검증을 마쳤습니다. '되돌리기'로 이전 답변을 복구할 수 있습니다.",
                                                    keep_prev=True)
                                except LLMError as ex:
                                    st.error(str(ex))

                # 수정 지시로 다시 쓰기
                with t_re:
                    fixes = st.pills("빠른 지시", QUICK_FIX, selection_mode="multi", key=f"fix_{qid}")
                    extra = st.text_input("직접 지시", key=f"inst_{qid}", placeholder="예: 협업 과정을 더 강조해 주세요")
                    instruction = ", ".join([*(fixes or []), extra.strip()]).strip(", ")
                    if st.button("지시대로 다시 쓰기", key=f"regen_{qid}", use_container_width=True,
                                 disabled=not (instruction and selected)):
                        _run_generate(previous=text, instruction=instruction)

        st.write("")
        if len(cl["qids"]) > 1:
            st.button("이 문항 삭제", key=f"del_{qid}", icon=":material/delete:", on_click=remove_question, args=(qid,))

with tabs[-1]:
    st.caption("기업별로 자기소개서 문항을 여러 개 관리할 수 있습니다. 문항을 추가하면 새 탭이 생깁니다.")
    st.button("문항 추가", icon=":material/add:", on_click=add_question)

# ── 3단계: 저장·버전·내보내기
st.write("")
with st.container(border=True):
    ui.step(3, "저장 · 버전 · 내보내기", "버전으로 남겨 두면 작성 이력에서 비교·복원할 수 있습니다.")
    app, answers = build_records()
    filled = [a for a in answers if a.content.strip()]
    s1, s2, s3, s4 = st.columns([1.2, 2, 1.2, 1.4])
    if s1.button("지원서 저장", icon=":material/save:", type="primary", use_container_width=True, disabled=not basics_ok):
        _save()
    s2.text_input("버전 이름", key="p_cl_vlabel", placeholder="버전 이름 (예: 첨삭 반영본)", label_visibility="collapsed")
    if s3.button("버전 저장", icon=":material/bookmark_add:", use_container_width=True, disabled=not basics_ok):
        _save(version_label=st.session_state.get("p_cl_vlabel", ""))
    if s4.button("최종 제출본으로 저장", icon=":material/verified:", use_container_width=True,
                 disabled=not (basics_ok and filled)):
        _save(version_label=st.session_state.get("p_cl_vlabel", "") or "최종 제출본", final=True)

    fname = f"{app.company or '자기소개서'}_{app.position or ''}".strip("_")
    d1, d2, d3 = st.columns(3)
    d1.download_button("TXT", exporter.cover_letter_txt(app, filled), file_name=f"{fname}.txt",
                       use_container_width=True, disabled=not filled)
    d2.download_button("Markdown", exporter.cover_letter_md(app, filled), file_name=f"{fname}.md",
                       use_container_width=True, disabled=not filled)
    d3.download_button("Word (DOCX)", exporter.cover_letter_docx(app, filled) if filled else b"", file_name=f"{fname}.docx",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       use_container_width=True, disabled=not filled)
    if not basics_ok:
        st.caption("기업명과 직무명을 입력하면 저장할 수 있습니다.")
    elif cl["app_id"]:
        if st.button("이 지원서로 면접 준비하기", icon=":material/record_voice_over:"):
            st.session_state["p_iv_app"] = cl["app_id"]
            st.switch_page("views/5_면접_준비.py")
