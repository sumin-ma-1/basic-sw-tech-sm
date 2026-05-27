"""Session state, chat persistence, and workspace helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from app.config import (
    APP_SETTINGS_FILE,
    CHAT_HISTORY_DIR,
    CHAT_INDEX_FILE,
    DEFAULT_OLLAMA_URL,
    USER_PROFILE_FILE,
    WORKSPACE_ROOT,
)
from app.services.chat_io import (
    chat_from_import_data as chat_io_from_import_data,
    serialize_chat,
)
from app.services.chat_state import (
    append_message as state_append_message,
    get_active_chat as state_get_active_chat,
    get_messages as state_get_messages,
    init_session_state as state_init_session_state,
    patch_message as state_patch_message,
    set_messages as state_set_messages,
)
from app.services.storage import (
    load_app_settings as storage_load_app_settings,
    load_chats_from_disk as storage_load_chats_from_disk,
    load_user_profile as storage_load_user_profile,
    save_chats_to_disk as storage_save_chats_to_disk,
)
from app.services.uploads import (
    build_data_summary as uploads_build_data_summary,
    process_uploaded_file as uploads_process_uploaded_file,
)
from app.services.workspace import (
    ensure_df_in_workspace_as_csv,
    get_chat_workspace as ws_get_chat_workspace,
    prepare_files_in_workspace as ws_prepare_files_in_workspace,
)
from app.ui.shared.persona import migrate_app_settings
from app.ui.shared.profile import DEFAULT_USER_PROFILE
from app.utils import new_chat as utils_new_chat, now_iso

DEFAULT_CHAT_TITLE = "새 대화"
MAX_TEXT_CHARS = 12_000


def new_chat(title: str = DEFAULT_CHAT_TITLE) -> dict[str, Any]:
    return utils_new_chat(title, default_title=DEFAULT_CHAT_TITLE)


def load_chats_from_disk() -> dict[str, dict[str, Any]]:
    return storage_load_chats_from_disk(
        chat_index_file=CHAT_INDEX_FILE,
        default_chat_title=DEFAULT_CHAT_TITLE,
        now_iso=now_iso,
    )


def load_user_profile() -> dict[str, str]:
    return storage_load_user_profile(
        user_profile_file=USER_PROFILE_FILE,
        default_user_profile=DEFAULT_USER_PROFILE,
    )


def load_app_settings() -> dict[str, Any]:
    return storage_load_app_settings(
        app_settings_file=APP_SETTINGS_FILE,
        migrate_app_settings=migrate_app_settings,
    )


def save_chats_to_disk() -> None:
    storage_save_chats_to_disk(
        chat_history_dir=CHAT_HISTORY_DIR,
        chat_index_file=CHAT_INDEX_FILE,
        chat_histories=st.session_state.chat_histories,
        now_iso=now_iso,
        serialize_chat=serialize_chat,
    )


def init_session_state() -> None:
    defaults = {
        "df": None,
        "df_name": None,
        "ollama_models": [],
        "ollama_base_url": DEFAULT_OLLAMA_URL,
    }
    state_init_session_state(
        defaults=defaults,
        load_chats_from_disk=load_chats_from_disk,
        new_chat=new_chat,
        load_user_profile=load_user_profile,
        load_app_settings=load_app_settings,
    )


def get_active_chat() -> dict[str, Any]:
    return state_get_active_chat()


def get_messages() -> list[dict[str, Any]]:
    return state_get_messages()


def set_messages(messages: list[dict[str, Any]]) -> None:
    state_set_messages(messages, now_iso=now_iso, save_chats_to_disk=save_chats_to_disk)


def append_message(msg: dict[str, Any]) -> None:
    state_append_message(
        msg,
        now_iso=now_iso,
        save_chats_to_disk=save_chats_to_disk,
        default_chat_title=DEFAULT_CHAT_TITLE,
    )


def patch_message(index: int, **fields: Any) -> None:
    state_patch_message(
        index, now_iso=now_iso, save_chats_to_disk=save_chats_to_disk, **fields
    )


def create_new_chat(title: str = DEFAULT_CHAT_TITLE) -> str:
    chat = new_chat(title)
    st.session_state.chat_histories[chat["id"]] = chat
    st.session_state.active_chat_id = chat["id"]
    save_chats_to_disk()
    return chat["id"]


def delete_chat(chat_id: str) -> None:
    if chat_id not in st.session_state.chat_histories:
        return
    del st.session_state.chat_histories[chat_id]
    if not st.session_state.chat_histories:
        create_new_chat()
    elif st.session_state.active_chat_id == chat_id:
        st.session_state.active_chat_id = next(iter(st.session_state.chat_histories))
    save_chats_to_disk()


def sorted_chat_ids() -> list[str]:
    chats = st.session_state.chat_histories
    return sorted(
        chats.keys(),
        key=lambda cid: chats[cid]["updated_at"],
        reverse=True,
    )


def chat_label(chat_id: str) -> str:
    return st.session_state.chat_histories[chat_id]["title"]


def chat_from_import_data(data: dict[str, Any]) -> dict[str, Any]:
    return chat_io_from_import_data(data, default_chat_title=DEFAULT_CHAT_TITLE)


def get_chat_workspace(chat_id: str | None = None) -> Path:
    cid = chat_id or st.session_state.active_chat_id
    return ws_get_chat_workspace(WORKSPACE_ROOT, chat_id=cid)


def build_data_summary(df: pd.DataFrame) -> str:
    return uploads_build_data_summary(df)


def process_uploaded_file(uploaded_file: Any, encoding: str) -> dict[str, Any]:
    return uploads_process_uploaded_file(
        uploaded_file,
        encoding=encoding,
        max_text_chars=MAX_TEXT_CHARS,
    )


def build_files_for_model(
    processed: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    if processed:
        return processed
    df = st.session_state.df
    name = st.session_state.df_name
    if df is None or not name:
        return None
    workspace = get_chat_workspace()
    return ensure_df_in_workspace_as_csv(
        df,
        df_name=name,
        workspace=workspace,
        summary=build_data_summary(df),
    )


def prepare_files_in_workspace(
    processed: list[dict[str, Any]], chat_id: str | None = None
) -> list[dict[str, Any]]:
    workspace = get_chat_workspace(chat_id)
    return ws_prepare_files_in_workspace(processed, workspace=workspace)


def apply_chat_files(processed: list[dict[str, Any]]) -> None:
    for item in processed:
        if item.get("df") is not None:
            st.session_state.df = item["df"]
            st.session_state.df_name = item["name"]
