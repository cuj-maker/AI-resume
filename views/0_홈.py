import html
from collections import Counter

import streamlit as st

from core import ui
from db import repository as repo

ui.bootstrap()
ui.sidebar_status()
ui.hero("AI 취업 서류 비서", "경험을 한 번 정리해 두면, 기업과 직무에 맞는 자기소개서와 이력서를 사실 그대로 써 드립니다.")

exps = repo.list_experiences()
apps = repo.list_applications()
n_answers = sum(len(repo.list_answers(a.id)) for a in apps)
usage = repo.usage_totals()

c1, c2, c3, c4 = st.columns(4)
c1.metric("저장된 경험", f"{len(exps)}개", border=True)
c2.metric("작성한 지원서", f"{len(apps)}건", border=True)
c3.metric("작성한 문항", f"{n_answers}개", border=True)
c4.metric("AI 사용 토큰", f"{usage['prompt_tokens'] + usage['completion_tokens']:,}", border=True)

st.write("")
left, right = st.columns([3, 2], gap="large")

with left:
    st.markdown("#### 빠른 시작")
    q1, q2, q3, q4 = st.columns(4)
    with q1, st.container(border=True):
        st.markdown("**1. 경험 정리**")
        st.caption("경험을 자유롭게 적으면 AI가 STAR로 정리합니다.")
        st.page_link("views/1_경험_저장소.py", label="경험 추가하기", icon=":material/add_circle:")
    with q2, st.container(border=True):
        st.markdown("**2. 자기소개서**")
        st.caption("공고와 문항을 넣으면 맞는 경험으로 답변을 씁니다.")
        st.page_link("views/2_자기소개서_작성.py", label="작성 시작", icon=":material/edit_note:")
    with q3, st.container(border=True):
        st.markdown("**3. 이력서**")
        st.caption("저장한 경험을 직무에 맞는 이력서 항목으로 바꿉니다.")
        st.page_link("views/3_이력서_작성.py", label="이력서 만들기", icon=":material/badge:")
    with q4, st.container(border=True):
        st.markdown("**4. 면접 준비**")
        st.caption("자소서·경험 기반 예상 질문과 STAR 답변을 연습합니다.")
        st.page_link("views/5_면접_준비.py", label="면접 준비", icon=":material/record_voice_over:")

    st.markdown("#### 최근 지원서")
    if apps:
        sc = Counter(a.status for a in apps)
        st.markdown("".join(f'<span class="chip muted">{html.escape(s)} · {n}</span>' for s, n in sc.most_common()),
                    unsafe_allow_html=True)
    if not apps:
        st.caption("아직 작성한 지원서가 없습니다.")
    for a in apps[:5]:
        st.markdown(f"- **{html.escape(a.company)}** · {html.escape(a.position)} <span class='chip type'>{html.escape(a.status)}</span>"
                    f"<span class='muted'>{a.applied_date or a.updated_at[:10]}</span>", unsafe_allow_html=True)

with right:
    st.markdown("#### 나의 핵심 역량 분포")
    comp = Counter(c for e in exps for c in e.competencies)
    if comp:
        st.markdown(
            "".join(f'<span class="chip comp">{html.escape(c)} · {n}</span>' for c, n in comp.most_common(15)),
            unsafe_allow_html=True,
        )
    else:
        st.caption("경험을 분석하면 핵심 역량이 여기에 모입니다.")

    st.markdown("#### 경험 유형")
    types = Counter(e.type for e in exps)
    if types:
        st.markdown("".join(f'<span class="chip muted">{t} · {n}</span>' for t, n in types.most_common()), unsafe_allow_html=True)
    else:
        st.caption("아직 저장된 경험이 없습니다.")

    need = [e for e in exps if e.missing_info]
    if need:
        st.markdown("#### 보완하면 좋은 경험")
        for e in need[:5]:
            st.markdown(f"- {html.escape(e.title)} <span class='chip warn'>{len(e.missing_info)}개 보완</span>", unsafe_allow_html=True)
