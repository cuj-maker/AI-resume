import html
from collections import Counter
from datetime import date

import streamlit as st

from core import exporter, ui, verifier, writer
from db import repository as repo
from db.models import APP_STATUSES, Answer, Application

ui.bootstrap()
ui.sidebar_status()
ui.hero("지원 이력 관리", "기업별 지원 상태·날짜·채용공고·자기소개서와 작성 버전, 최종 제출본을 한곳에서 관리합니다.")


@st.dialog("지원서 삭제")
def confirm_delete(app_id: str, label: str) -> None:
    st.write(f"**{label}** 지원서와 모든 문항 답변·버전·면접 질문을 삭제할까요?")
    c1, c2 = st.columns(2)
    if c1.button("삭제", type="primary", use_container_width=True):
        repo.delete_application(app_id)
        st.session_state["_toast"] = "지원서를 삭제했습니다."
        st.rerun()
    if c2.button("취소", use_container_width=True):
        st.rerun()


@st.dialog("버전 복원")
def confirm_restore(version_id: str, label: str) -> None:
    st.write(f"현재 내용을 **{label}** 버전으로 되돌릴까요? 지원 상태·날짜·메모는 유지됩니다.")
    st.caption("현재 내용을 남겨 두려면 먼저 자기소개서 작성 화면에서 버전으로 저장하세요.")
    c1, c2 = st.columns(2)
    if c1.button("복원", type="primary", use_container_width=True):
        repo.restore_version(version_id)
        st.session_state["_toast"] = f"'{label}' 버전으로 복원했습니다."
        st.rerun()
    if c2.button("취소", use_container_width=True):
        st.rerun()


def _on_status(app_id: str) -> None:
    repo.update_application_fields(app_id, status=st.session_state[f"st_{app_id}"])


def _on_date(app_id: str) -> None:
    d = st.session_state[f"dt_{app_id}"]
    repo.update_application_fields(app_id, applied_date=d.isoformat() if d else "")


def _on_memo(app_id: str) -> None:
    repo.update_application_fields(app_id, memo=st.session_state[f"memo_{app_id}"])


def _answers_view(app: Application, answers: list[Answer], exp_titles: dict) -> None:
    if not answers:
        st.caption("작성된 문항이 없습니다.")
    for i, ans in enumerate(answers, 1):
        st.markdown(f"**{i}. {html.escape(ans.question)}**", unsafe_allow_html=True)
        n = writer.count_chars(ans.content, ans.count_spaces)
        meta = f"{n:,}자" + (f" / {ans.char_limit:,}자 ({'공백 포함' if ans.count_spaces else '공백 제외'})" if ans.char_limit else "")
        if ans.verification:
            bad = sum(1 for v in ans.verification if not v.get("supported", True))
            meta += f" · 근거 없는 문장 {bad}개" if bad else " · 사실 검증 통과"
        used = [exp_titles.get(eid, "삭제된 경험") for eid in ans.used_experience_ids]
        if used:
            meta += " · 사용 경험: " + ", ".join(used)
        st.caption(meta)
        ui.html_box(verifier.highlight(ans.content, ans.verification) if ans.content
                    else "<span class='muted'>(비어 있음)</span>")
        st.write("")


all_apps = repo.list_applications()

# 상태 요약
if all_apps:
    cnt = Counter(a.status for a in all_apps)
    st.markdown(" ".join(ui.chips_html([f"{s} {cnt[s]}"], "type" if s == "작성 중" else "muted")
                         for s in APP_STATUSES if cnt.get(s)), unsafe_allow_html=True)

f1, f2 = st.columns([3, 2])
query = f1.text_input("검색", placeholder="기업명 또는 직무명", label_visibility="collapsed")
status_filter = f2.multiselect("상태", APP_STATUSES, placeholder="지원 상태로 필터", label_visibility="collapsed")
apps = [a for a in all_apps
        if (not query or query.lower() in f"{a.company} {a.position}".lower())
        and (not status_filter or a.status in status_filter)]

if not all_apps:
    st.info("저장된 지원서가 없습니다. 자기소개서 작성 화면에서 **지원서 저장**을 누르면 여기에 모입니다.", icon="🗂️")
    st.page_link("views/2_자기소개서_작성.py", label="자기소개서 작성하기", icon=":material/edit_note:")
elif not apps:
    st.caption("조건에 맞는 지원서가 없습니다.")

exp_titles = {e.id: e.title for e in repo.list_experiences()}

for a in apps:
    answers = repo.list_answers(a.id)
    versions = repo.list_versions(a.id)
    final = next((v for v in versions if v.is_final), None)
    with st.container(border=True):
        h1, h2 = st.columns([4, 3])
        badges = ui.chips_html([a.status], "type") + (ui.chips_html(["최종 제출본 있음"], "comp") if final else "")
        h1.markdown(
            f"### {html.escape(a.company)} <span class='muted'>· {html.escape(a.position)}</span><br>{badges}"
            f"<span class='exp-meta'>지원 {a.applied_date or '미정'} · 문항 {len(answers)}개 · 버전 {len(versions)}개 · "
            f"수정 {a.updated_at.replace('T', ' ')[:16]}</span>",
            unsafe_allow_html=True,
        )
        b1, b2, b3, b4 = h2.columns(4)
        if b1.button("편집", key=f"edit_{a.id}", icon=":material/edit:", use_container_width=True):
            st.session_state["cl_load"] = a.id
            st.switch_page("views/2_자기소개서_작성.py")
        if b2.button("면접", key=f"iv_{a.id}", icon=":material/record_voice_over:", use_container_width=True):
            st.session_state["p_iv_app"] = a.id
            st.switch_page("views/5_면접_준비.py")
        if b3.button("복제", key=f"dup_{a.id}", icon=":material/content_copy:", use_container_width=True):
            repo.duplicate_application(a.id)
            ui.queue({}, toast="지원서를 복제했습니다.")
            st.rerun()
        if b4.button("삭제", key=f"del_{a.id}", icon=":material/delete:", use_container_width=True):
            confirm_delete(a.id, f"{a.company} · {a.position}")

        # 상태·날짜·메모 바로 수정
        st.session_state[f"st_{a.id}"] = a.status if a.status in APP_STATUSES else APP_STATUSES[0]
        st.session_state[f"dt_{a.id}"] = date.fromisoformat(a.applied_date) if a.applied_date else None
        st.session_state[f"memo_{a.id}"] = a.memo
        m1, m2, m3 = st.columns([1, 1, 3])
        m1.selectbox("지원 상태", APP_STATUSES, key=f"st_{a.id}", on_change=_on_status, args=(a.id,))
        m2.date_input("지원 날짜", key=f"dt_{a.id}", on_change=_on_date, args=(a.id,), format="YYYY-MM-DD")
        m3.text_input("메모", key=f"memo_{a.id}", on_change=_on_memo, args=(a.id,),
                      placeholder="예: 서류 발표 11/20, 인적성 준비")

        with st.expander("상세 보기"):
            t1, t2, t3 = st.tabs(["작성 결과", "채용공고", f"작성 버전 ({len(versions)})"])
            with t1:
                _answers_view(a, answers, exp_titles)
                fname = f"{a.company}_{a.position}"
                filled = [x for x in answers if x.content.strip()]
                d1, d2, d3 = st.columns(3)
                d1.download_button("TXT", exporter.cover_letter_txt(a, filled), file_name=f"{fname}.txt",
                                   key=f"txt_{a.id}", use_container_width=True)
                d2.download_button("Markdown", exporter.cover_letter_md(a, filled), file_name=f"{fname}.md",
                                   key=f"md_{a.id}", use_container_width=True)
                d3.download_button("Word (DOCX)", exporter.cover_letter_docx(a, filled), file_name=f"{fname}.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   key=f"docx_{a.id}", use_container_width=True)
            with t2:
                if a.job_posting.strip():
                    st.text(a.job_posting)
                else:
                    st.caption("저장된 채용공고가 없습니다.")
                if a.company_info.strip():
                    st.markdown("**기업 정보**")
                    st.text(a.company_info)
            with t3:
                if not versions:
                    st.caption("저장된 버전이 없습니다. 자기소개서 작성 화면에서 **버전 저장** 또는 **최종 제출본으로 저장**을 누르세요.")
                for v in versions:
                    with st.container(border=True):
                        v_answers = [Answer.model_validate(x) for x in v.snapshot.get("answers", [])]
                        vc1, vc2, vc3, vc4 = st.columns([3, 1, 1, 1])
                        vc1.markdown(
                            f"**{html.escape(v.label)}** "
                            + (ui.chips_html(["최종 제출본"], "comp") if v.is_final else "")
                            + f"<br><span class='exp-meta'>{v.created_at.replace('T', ' ')[:16]} · 문항 {len(v_answers)}개</span>",
                            unsafe_allow_html=True)
                        if vc2.button("복원", key=f"vr_{v.id}", use_container_width=True):
                            confirm_restore(v.id, v.label)
                        if vc3.button("최종본 지정", key=f"vf_{v.id}", use_container_width=True, disabled=v.is_final):
                            repo.set_final_version(v.id)
                            ui.queue({}, toast=f"'{v.label}'을(를) 최종 제출본으로 지정했습니다.")
                            st.rerun()
                        if vc4.button("삭제", key=f"vd_{v.id}", use_container_width=True):
                            repo.delete_version(v.id)
                            ui.queue({}, toast="버전을 삭제했습니다.")
                            st.rerun()
                        if st.toggle("내용 보기", key=f"vs_{v.id}"):
                            v_app = Application.model_validate(v.snapshot["application"])
                            _answers_view(v_app, v_answers, exp_titles)
                            v_filled = [x for x in v_answers if x.content.strip()]
                            st.download_button("이 버전 DOCX", exporter.cover_letter_docx(v_app, v_filled),
                                               file_name=f"{a.company}_{a.position}_{v.label}.docx",
                                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                               key=f"vdocx_{v.id}")
