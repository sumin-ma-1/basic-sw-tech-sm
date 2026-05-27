from __future__ import annotations

from typing import Any, Callable

import streamlit as st


def init_session_state(
    *,
    defaults: dict[str, Any],
    load_chats_from_disk: Callable[[], dict[str, dict[str, Any]]],
    new_chat: Callable[[], dict[str, Any]],
    load_user_profile: Callable[[], dict[str, str]],
    load_app_settings: Callable[[], dict[str, Any]],
) -> None:
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "chat_histories" not in st.session_state:
        loaded = load_chats_from_disk()
        if loaded:
            st.session_state.chat_histories = loaded
        else:
            chat = new_chat()
            st.session_state.chat_histories = {chat["id"]: chat}

    if "active_chat_id" not in st.session_state:
        st.session_state.active_chat_id = next(iter(st.session_state.chat_histories))

    if st.session_state.active_chat_id not in st.session_state.chat_histories:
        st.session_state.active_chat_id = next(iter(st.session_state.chat_histories))

    if "user_profile" not in st.session_state:
        st.session_state.user_profile = load_user_profile()

    if "selected_persona_id" not in st.session_state:
        settings = load_app_settings()
        st.session_state.selected_persona_id = settings["selected_persona_id"]
        st.session_state.custom_personas = settings["custom_personas"]


def get_active_chat() -> dict[str, Any]:
    return st.session_state.chat_histories[st.session_state.active_chat_id]


def get_messages() -> list[dict[str, Any]]:
    return get_active_chat()["messages"]


def set_messages(
    messages: list[dict[str, Any]],
    *,
    now_iso: Callable[[], str],
    save_chats_to_disk: Callable[[], None],
) -> None:
    chat = get_active_chat()
    chat["messages"] = messages
    chat["updated_at"] = now_iso()
    save_chats_to_disk()


def append_message(
    msg: dict[str, Any],
    *,
    now_iso: Callable[[], str],
    save_chats_to_disk: Callable[[], None],
    default_chat_title: str,
) -> None:
    chat = get_active_chat()
    chat["messages"].append(msg)
    chat["updated_at"] = now_iso()
    if (
        chat["title"] == default_chat_title
        and msg["role"] == "user"
        and msg.get("content", "").strip()
    ):
        preview = msg["content"].strip().replace("\n", " ")
        chat["title"] = preview[:40] + ("…" if len(preview) > 40 else "")
    save_chats_to_disk()


def patch_message(
    index: int,
    *,
    now_iso: Callable[[], str],
    save_chats_to_disk: Callable[[], None],
    **fields: Any,
) -> None:
    chat = get_active_chat()
    chat["messages"][index].update(fields)
    chat["updated_at"] = now_iso()
    save_chats_to_disk()

