"""Streamlit entry: AI chat and Ollama admin."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.bootstrap import page_chat, page_ollama
from app.config import ICON_PAGE_CHAT, ICON_PAGE_OLLAMA
from app.session import init_session_state


def main() -> None:
    favicon = Path(__file__).parent / "sm_final.png"
    st.set_page_config(
        page_title="Basic Software Technology",
        page_icon=str(favicon) if favicon.exists() else ICON_PAGE_CHAT,
        layout="wide",
    )

    init_session_state()

    chat_page = st.Page(
        page_chat, title="AI 채팅", icon=ICON_PAGE_CHAT, default=True
    )
    ollama_page = st.Page(page_ollama, title="Ollama 관리", icon=ICON_PAGE_OLLAMA)
    st.navigation([chat_page, ollama_page]).run()


if __name__ == "__main__":
    main()
