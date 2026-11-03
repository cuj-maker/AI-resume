from collections import Counter

import streamlit as st

from core import exporter, matcher, ui, writer
from core.llm import LLMError
from db import repository as repo
from db.models import RESUME_SECTIONS, Profile, ResumeDraft, ResumeItem

ui.bootstrap()
ui.sidebar_status()
ui.hero("이력서 작성", "인적사항·학력·자격증과 저장된 경험으로 경력·프로젝트·핵심 역량까지 갖춘 직무 맞춤 이력서를 만듭니다.")

profile = repo.get_profile()
exps = repo.list_experiences()
exp_map = {e.id: e for e in exps}

# ── 1단계: 기본 정보 (RS-01)
with st.container(border=True):
    ui.step(1, "기본 인적사항 · 학력 · 자격", "한 번 저장하면 계속 사용됩니다. 경력·프로젝트는 경험 저장소에서 가져옵니다.")
    with st.form("profile_form", border=False):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("이름", profile.name)
        email = c2.text_input("이메일", profile.email)
        phone = c3.text_input("연락처", profile.phone)
        links = st.text_input("링크 (GitHub, 포트폴리오 등)", profile.links)
        c4, c5 = st.columns(2)
        education = c4.text_area("학력", profile.education, height=100, placeholder="OO대학교 경영학과 (2019.03 ~ 2025.02)")
        skills = c5.text_area("기술 스택 · 보유 역량", profile.skills, height=100, placeholder="Python, SQL, Excel, Figma")
        c6, c7, c8 = st.columns(3)
        certifications = c6.text_area("자격증", profile.certifications, height=90, placeholder="정보처리기사 (2024.06)")
        training = c7.text_area("교육 및 수료", profile.training, height=90, placeholder="OO 부트캠프 데이터 분석 과정 수료 (2024.01)")
        languages = c8.text_area("어학", profile.languages, height=90, placeholder="TOEIC 900 (2024.03)")
        if st.form_submit_button("기본 정보 저장", icon=":material/save:", type="primary"):
            repo.save_profile(Profile(name=name, email=email, phone=phone, links=links, education=education,
                                      skills=skills, certifications=certifications, languages=languages,
                                      training=training))
            ui.queue({}, toast="기본 정보를 저장했습니다.")
            st.rerun()

# ── 2단계: 직무 맞춤 생성 (RS-02, RS-03)
with st.container(border=True):
    ui.step(2, "직무 맞춤 경험 정리", "관련도가 높은 경험이 위로 정렬됩니다.")
    if not exps:
        st.warning("저장된 경험이 없습니다. 먼저 경험 저장소에서 경험을 추가해 주세요.", icon="📂")
    ui.init("p_rs_position", "")
    ui.init("p_rs_posting", "")
    ui.init("p_rs_sel", [e.id for e in exps])
    st.session_state["p_rs_sel"] = [i for i in st.session_state["p_rs_sel"] if i in exp_map]
    c1, c2 = st.columns([1, 2])
    c1.text_input("지원 직무", key="p_rs_position", placeholder="예: 데이터 분석가")
    c2.text_area("채용공고 (선택)", key="p_rs_posting", height=68)
    st.multiselect("포함할 경험", list(exp_map), key="p_rs_sel",
                   format_func=lambda i: f"{exp_map[i].title} ({exp_map[i].type})")

    if st.button("이력서 항목 생성", icon=":material/auto_awesome:", type="primary",
                 disabled=not st.session_state["p_rs_sel"]):
        if ui.require_api():
            try:
                posting = {}
                if st.session_state["p_rs_posting"].strip():
                    with st.spinner("채용공고를 분석하는 중…"):
                        posting = matcher.analyze_posting("", st.session_state["p_rs_position"],
                                                          st.session_state["p_rs_posting"], "").model_dump()
                with st.spinner("이력서 항목을 작성하는 중…"):
                    draft = writer.generate_resume(repo.get_profile(), [exp_map[i] for i in st.session_state["p_rs_sel"]],
                                                   st.session_state["p_rs_position"], posting)
                ui.clear_prefix("p_rs_b_")
                st.session_state["rs_order"] = [it.experience_id for it in draft.items]
                st.session_state["rs_relevance"] = {it.experience_id: it.relevance for it in draft.items}
                core = draft.core_competencies or [c for c, _ in Counter(
                    c for i in st.session_state["p_rs_sel"] for c in exp_map[i].competencies).most_common(6)]
                upd = {"p_rs_summary": draft.summary, "p_rs_core": ", ".join(core)}
                upd |= {f"p_rs_b_{it.experience_id}": "\n".join(it.bullets) for it in draft.items}
                ui.queue(upd, toast="이력서 항목을 작성했습니다. 직접 다듬을 수 있습니다.")
                st.rerun()
            except LLMError as ex:
                st.error(str(ex))

# ── 3단계: 편집 · 미리보기 · 내보내기 (RS-04)
order = [i for i in st.session_state.get("rs_order", []) if i in exp_map]
if order:
    ui.init("p_rs_summary", "")
    ui.init("p_rs_core", "")
    rel = st.session_state.get("rs_relevance", {})
    st.write("")
    ui.step(3, "다듬기 · 내보내기")
    edit, preview = st.columns(2, gap="large")
    with edit:
        st.text_area("요약", key="p_rs_summary", height=100)
        st.text_input("핵심 역량 (쉼표로 구분)", key="p_rs_core")
        for sec_title, types in RESUME_SECTIONS:
            sec = [eid for eid in order if exp_map[eid].type in types]
            if not sec:
                continue
            st.markdown(f"**{sec_title}**")
            for eid in sec:
                ui.init(f"p_rs_b_{eid}", "")
                st.text_area(f"{exp_map[eid].title} · 관련도 {rel.get(eid, 0)}", key=f"p_rs_b_{eid}", height=110,
                             help="한 줄에 한 항목씩 적습니다.")
    draft = ResumeDraft(
        summary=st.session_state["p_rs_summary"],
        core_competencies=[c.strip() for c in st.session_state["p_rs_core"].split(",") if c.strip()],
        items=[ResumeItem(experience_id=eid, relevance=rel.get(eid, 0),
                          bullets=[b.strip().lstrip("-•· ").strip() for b in st.session_state[f"p_rs_b_{eid}"].split("\n") if b.strip()])
               for eid in order],
    )
    prof = repo.get_profile()
    md = exporter.resume_md(prof, draft, exp_map, st.session_state["p_rs_position"])
    with preview:
        with st.container(border=True):
            st.markdown(md)
        d1, d2 = st.columns(2)
        fname = f"이력서_{prof.name or '이름'}"
        d1.download_button("Markdown", md, file_name=f"{fname}.md", use_container_width=True)
        d2.download_button("Word (DOCX)", exporter.resume_docx(prof, draft, exp_map, st.session_state["p_rs_position"]),
                           file_name=f"{fname}.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           use_container_width=True)
        if "[보완 필요" in md:
            st.info("`[보완 필요]` 표시는 경험 자료에 정보가 없어 비워 둔 부분입니다.", icon="✏️")
