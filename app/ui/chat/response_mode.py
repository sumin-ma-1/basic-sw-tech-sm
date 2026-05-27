"""채팅 하단: 즉시/추론 pills (thinking 지원 모델만) + chat_input."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.api.ollama import model_supports_thinking

CHAT_FILE_TYPES = ["csv", "txt", "md", "json", "xlsx", "xls"]
CHAT_INPUT_PLACEHOLDER = "메시지를 입력하세요"

RESPONSE_MODES: dict[str, str] = {
    "instant": "즉시",
    "thinking": "추론",
}


def clear_model_capabilities_cache() -> None:
    st.session_state.ollama_model_capabilities = {}


def _capabilities_cache_key(base_url: str, model: str) -> str:
    return f"{base_url.rstrip('/')}|{model}"


def cached_model_supports_thinking(base_url: str, model: str) -> bool:
    cache: dict[str, bool] = st.session_state.setdefault(
        "ollama_model_capabilities", {}
    )
    key = _capabilities_cache_key(base_url, model)
    if key not in cache:
        cache[key] = model_supports_thinking(base_url, model)
    return cache[key]


def model_uses_think_param(*, base_url: str, model: str, connected: bool) -> bool:
    return connected and cached_model_supports_thinking(base_url, model)


def _inject_bottom_toolbar_css() -> None:
    if st.session_state.get("_chat_bottom_css_v2"):
        return
    st.markdown(
        """
        <style>
        div[data-testid="stBottom"] > div {
            padding-top: 0.35rem;
        }
        div[data-testid="stBottom"] [data-testid="stVerticalBlock"] > div:first-child {
            display: flex;
            justify-content: flex-end;
            width: 100%;
            margin-bottom: 0.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state._chat_bottom_css_v2 = True


def _render_mode_toolbar(*, base_url: str, model: str) -> bool:
    options = list(RESPONSE_MODES.keys())
    default = "thinking" if st.session_state.get("ollama_think") else "instant"
    if default not in options:
        default = "instant"

    with st.container(horizontal_alignment="right"):
        selected = st.pills(
            "응답 모드",
            options,
            default=default,
            format_func=lambda key: RESPONSE_MODES[key],
            label_visibility="collapsed",
            key=f"chat_response_mode_{_capabilities_cache_key(base_url, model)}",
        )
    mode = selected if selected in options else default
    think = mode == "thinking"
    st.session_state.ollama_think = think
    return think


def render_chat_bottom_bar(settings: dict[str, Any]) -> tuple[bool, bool, Any]:
    """(think, send_think_param, chat_result), send_think_param 이면 API에 think 전달."""
    base_url = settings["base_url"]
    model = settings["model"]
    connected = settings.get("ollama_connected", False)
    send_think = model_uses_think_param(
        base_url=base_url, model=model, connected=connected
    )

    think = False
    with st.bottom:
        _inject_bottom_toolbar_css()
        if send_think:
            think = _render_mode_toolbar(base_url=base_url, model=model)
        else:
            st.session_state.ollama_think = False

        chat_result = st.chat_input(
            CHAT_INPUT_PLACEHOLDER,
            accept_file="multiple",
            file_type=CHAT_FILE_TYPES,
        )

    return think, send_think, chat_result
