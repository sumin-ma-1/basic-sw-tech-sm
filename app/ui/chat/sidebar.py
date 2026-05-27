from __future__ import annotations

import json
from typing import Any, Callable

import streamlit as st

from app.api.ollama import fetch_ollama_models
from app.ui.shared.persona import render_system_prompt_section
from app.ui.shared.profile import profile_button_label, user_profile_dialog


def sync_ollama_base_url(base_url: str, *, default_ollama_url: str) -> str:
    st.session_state.ollama_base_url = base_url.rstrip("/") or default_ollama_url
    return st.session_state.ollama_base_url


def render_chat_history_manager(
    *,
    default_chat_title: str,
    now_iso: Callable[[], str],
    create_new_chat: Callable[[], str],
    get_active_chat: Callable[[], dict[str, Any]],
    set_messages: Callable[[list[dict[str, Any]]], None],
    delete_chat: Callable[[str], None],
    sorted_chat_ids: Callable[[], list[str]],
    chat_label: Callable[[str], str],
    serialize_chat: Callable[[dict[str, Any]], dict[str, Any]],
    chat_to_markdown: Callable[[dict[str, Any]], str],
    parse_imported_chat_file: Callable[[Any], dict[str, Any]],
    chat_from_import_data: Callable[[dict[str, Any]], dict[str, Any]],
    save_chats_to_disk: Callable[[], None],
) -> None:
    st.subheader("채팅 히스토리")

    if st.button("＋ 새 대화", use_container_width=True, key="btn_new_chat"):
        create_new_chat()
        st.rerun()

    chat_ids = sorted_chat_ids()
    labels = [chat_label(cid) for cid in chat_ids]
    current_idx = chat_ids.index(st.session_state.active_chat_id)

    selected_label = st.selectbox(
        "대화 선택",
        labels,
        index=current_idx,
        key="chat_selector",
    )
    selected_id = chat_ids[labels.index(selected_label)]
    if selected_id != st.session_state.active_chat_id:
        st.session_state.active_chat_id = selected_id
        st.rerun()

    active = get_active_chat()
    st.caption(f"생성: {active['created_at']} · 수정: {active['updated_at']}")

    with st.expander("대화 이름 변경"):
        new_title = st.text_input("제목", value=active["title"], key="rename_title")
        if st.button("이름 저장", use_container_width=True, key="btn_rename"):
            active["title"] = new_title.strip() or default_chat_title
            active["updated_at"] = now_iso()
            save_chats_to_disk()
            st.rerun()

    col_clear, col_del = st.columns(2)
    with col_clear:
        if st.button("현재 대화 비우기", use_container_width=True, key="btn_clear"):
            set_messages([])
            st.rerun()
    with col_del:
        if st.button("대화 삭제", use_container_width=True, key="btn_delete"):
            delete_chat(st.session_state.active_chat_id)
            st.rerun()

    export_fmt = st.selectbox(
        "보내기 형식",
        ["JSON", "Markdown"],
        key="export_chat_fmt",
    )
    chat_stub = active["id"][:8]
    if export_fmt == "JSON":
        export_data = json.dumps(
            serialize_chat(active),
            ensure_ascii=False,
            indent=2,
        )
        export_name = f"chat_{chat_stub}.json"
        export_mime = "application/json"
    else:
        export_data = chat_to_markdown(active)
        export_name = f"chat_{chat_stub}.md"
        export_mime = "text/markdown"

    st.download_button(
        "현재 대화 보내기",
        data=export_data,
        file_name=export_name,
        mime=export_mime,
        use_container_width=True,
    )

    imported = st.file_uploader(
        "대화 가져오기",
        type=["json", "md"],
        key="import_chat",
        help="JSON 또는 Markdown(.md) 파일을 업로드하면 새 대화로 추가됩니다.",
    )
    if imported is not None:
        import_key = f"{imported.name}:{imported.size}"
        if st.session_state.get("last_import_key") != import_key:
            try:
                data = parse_imported_chat_file(imported)
                chat = chat_from_import_data(data)
                st.session_state.chat_histories[chat["id"]] = chat
                st.session_state.active_chat_id = chat["id"]
                st.session_state.last_import_key = import_key
                save_chats_to_disk()
                st.rerun()
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                st.error(f"가져오기 실패: {exc}")


def render_sidebar(
    *,
    default_ollama_url: str,
    fallback_models: list[str],
    icon_refresh: str,
    default_chat_title: str,
    now_iso: Callable[[], str],
    create_new_chat: Callable[[], str],
    get_active_chat: Callable[[], dict[str, Any]],
    set_messages: Callable[[list[dict[str, Any]]], None],
    delete_chat: Callable[[str], None],
    sorted_chat_ids: Callable[[], list[str]],
    chat_label: Callable[[str], str],
    serialize_chat: Callable[[dict[str, Any]], dict[str, Any]],
    chat_to_markdown: Callable[[dict[str, Any]], str],
    parse_imported_chat_file: Callable[[Any], dict[str, Any]],
    chat_from_import_data: Callable[[dict[str, Any]], dict[str, Any]],
    save_chats_to_disk: Callable[[], None],
) -> dict[str, Any]:
    with st.sidebar:
        if st.button(profile_button_label(), use_container_width=True):
            user_profile_dialog()

        st.subheader("Ollama")

        base_url = sync_ollama_base_url(
            st.text_input(
                "Ollama URL",
                value=st.session_state.ollama_base_url,
                key="chat_ollama_url",
            ),
            default_ollama_url=default_ollama_url,
        )

        if st.button(
            "모델 목록 새로고침",
            icon=icon_refresh,
            use_container_width=True,
        ):
            st.session_state.ollama_models = fetch_ollama_models(base_url)
            st.rerun()

        if not st.session_state.ollama_models:
            st.session_state.ollama_models = fetch_ollama_models(base_url)

        models = st.session_state.ollama_models or fallback_models
        if st.session_state.ollama_models:
            st.success(f"연결됨 · {len(models)}개 모델")
        else:
            st.warning("Ollama 미연결")

        st.caption("모델 받기·삭제는 사이드바 **Ollama 관리** 페이지에서")

        model = st.selectbox("모델", models)

        df = st.session_state.df
        if df is not None:
            name = st.session_state.df_name or "데이터"
            st.caption(f"활성: **{name}** ({len(df):,}행 × {len(df.columns)}열)")
            if st.button("활성 데이터 초기화", use_container_width=True):
                st.session_state.df = None
                st.session_state.df_name = None
                st.rerun()

        st.divider()
        st.subheader("시스템 프롬프트")
        system_prompt = render_system_prompt_section()

        st.divider()
        render_chat_history_manager(
            default_chat_title=default_chat_title,
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

        st.caption("포트 **8507** · `streamlit run main.py`")

    return {
        "base_url": base_url,
        "model": model,
        "system_prompt": system_prompt,
        "ollama_connected": bool(st.session_state.ollama_models),
    }
