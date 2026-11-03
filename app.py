"""AI 취업 서류 비서: Streamlit 진입점."""
import streamlit as st

from core import ui

st.set_page_config(page_title="AI 취업 서류 비서", page_icon="📝", layout="wide")

# 상태 유지·테마는 각 페이지의 ui.bootstrap()에서 처리한다.

pages = [
    st.Page("views/0_홈.py", title="홈", icon=":material/home:", default=True),
    st.Page("views/1_경험_저장소.py", title="경험 저장소", icon=":material/inventory_2:"),
    st.Page("views/2_자기소개서_작성.py", title="자기소개서 작성", icon=":material/edit_note:"),
    st.Page("views/3_이력서_작성.py", title="이력서 작성", icon=":material/badge:"),
    st.Page("views/5_면접_준비.py", title="면접 준비", icon=":material/record_voice_over:"),
    st.Page("views/4_작성_이력.py", title="지원 이력", icon=":material/history:"),
]
pg = st.navigation(pages)
pg.run()
