"""공통 인증 모듈 — 모든 페이지에서 사용"""

import streamlit as st


def check_auth():
    """비밀번호 인증. 인증 안 되면 로그인 폼을 보여주고 st.stop()."""
    try:
        correct_pw = st.secrets["APP_PASSWORD"]
    except (FileNotFoundError, KeyError):
        return  # 로컬 개발 환경 — 비밀번호 없으면 통과

    if st.session_state.get("authenticated", False):
        return  # 이미 인증됨

    st.title("🔒 로그인")
    password = st.text_input("비밀번호를 입력하세요", type="password", key="auth_pw")
    if st.button("로그인", key="auth_btn"):
        if password == correct_pw:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()
