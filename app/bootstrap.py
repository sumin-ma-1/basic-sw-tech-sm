"""Page wiring for Streamlit navigation."""

from __future__ import annotations

import streamlit as st

from app.config import (
    DEFAULT_OLLAMA_URL,
    ICON_DELETE,
    ICON_DOWNLOAD,
    ICON_REFRESH,
)
from app.services.chat_io import (
    chat_to_markdown,
    parse_imported_chat_file,
    serialize_chat,
)
from app.session import (
    DEFAULT_CHAT_TITLE,
    chat_from_import_data,
    chat_label,
    create_new_chat,
    delete_chat,
    get_active_chat,
    save_chats_to_disk,
    set_messages,
    sorted_chat_ids,
)
from app.ui.chat.page import render_ai_chat
from app.ui.chat.sidebar import render_sidebar
from app.ui.ollama.page import render_ollama_page
from app.utils import now_iso

FALLBACK_MODELS = ["qwen3:8b", "llama3.2", "llama3", "mistral", "gemma2"]


def page_chat() -> None:
    settings = render_sidebar(
        default_ollama_url=DEFAULT_OLLAMA_URL,
        fallback_models=FALLBACK_MODELS,
        icon_refresh=ICON_REFRESH,
        default_chat_title=DEFAULT_CHAT_TITLE,
        now_iso=now_iso,
        create_new_chat=create_new_chat,
        get_active_chat=get_active_chat,
        set_messages=set_messages,
        delete_chat=delete_chat,
        sorted_chat_ids=sorted_chat_ids,
        chat_label=chat_label,
        serialize_chat=serialize_chat,
        chat_to_markdown=chat_to_markdown,
        parse_imported_chat_file=parse_imported_chat_file,
        chat_from_import_data=chat_from_import_data,
        save_chats_to_disk=save_chats_to_disk,
    )
    render_ai_chat(settings)


def page_ollama() -> None:
    render_ollama_page(
        default_base_url=DEFAULT_OLLAMA_URL,
        icon_refresh=ICON_REFRESH,
        icon_download=ICON_DOWNLOAD,
        icon_delete=ICON_DELETE,
    )
