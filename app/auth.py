"""공통 인증 모듈 — 모든 페이지에서 사용"""

import streamlit as st


def require_login():
    """비밀번호 인증이 안 되어 있으면 페이지 접근 차단."""
    try:
        correct_pw = st.secrets["APP_PASSWORD"]
    except (FileNotFoundError, KeyError):
        return  # 로컬 개발 환경 — 비밀번호 없으면 통과

    if not st.session_state.get("authenticated", False):
        st.warning("로그인이 필요합니다. 메인 페이지에서 로그인해주세요.")
        st.stop()
