"""AI chat page: message list and chat input loop."""

from __future__ import annotations

import urllib.error
from typing import Any

import streamlit as st

from app.services.chat_llm import build_active_context, call_ollama
from app.services.code_exec import (
    execute_python_code as code_execute_python_code,
    extract_code_explanation as code_extract_code_explanation,
    extract_python_blocks as code_extract_python_blocks,
)
from app.session import (
    append_message,
    apply_chat_files,
    build_files_for_model,
    get_chat_workspace,
    get_messages,
    patch_message,
    prepare_files_in_workspace,
    process_uploaded_file,
)
from app.ui.chat.messages import (
    render_code_execution_panel as ui_render_code_execution_panel,
    render_message as ui_render_message,
)
from app.ui.chat.response_mode import render_chat_bottom_bar
from app.ui.chat.thinking_status import run_with_thinking_status
from app.ui.components.file_preview import render_file_preview as ui_render_file_preview

CHAT_FILE_TYPES = ["csv", "txt", "md", "json", "xlsx", "xls"]
MAX_PREVIEW_ROWS = 30
MAX_FILE_PREVIEW_CHARS = 800
CODE_EXEC_TIMEOUT = 120
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2048
DEFAULT_FILE_ENCODING = "utf-8"


def render_file_preview(file_info: dict[str, Any]) -> None:
    ui_render_file_preview(
        file_info,
        max_preview_rows=MAX_PREVIEW_ROWS,
        max_preview_chars=MAX_FILE_PREVIEW_CHARS,
    )


def render_code_execution_panel(msg: dict[str, Any], msg_index: int) -> None:
    ui_render_code_execution_panel(
        msg,
        msg_index,
        extract_code_explanation=code_extract_code_explanation,
        get_chat_workspace=get_chat_workspace,
        execute_python_code=lambda code, workspace: code_execute_python_code(
            code, workspace=workspace, timeout_s=CODE_EXEC_TIMEOUT
        ),
        patch_message=patch_message,
    )


def render_message(msg: dict[str, Any], msg_index: int) -> None:
    ui_render_message(
        msg,
        msg_index,
        render_file_preview=render_file_preview,
        render_code_execution_panel_cb=render_code_execution_panel,
    )


def render_ai_chat(settings: dict[str, Any]) -> None:
    messages = get_messages()
    for idx, msg in enumerate(messages):
        render_message(msg, idx)

    think, send_think, chat_result = render_chat_bottom_bar(settings)

    if not chat_result:
        return

    text = getattr(chat_result, "text", None)
    if text is None:
        text = chat_result if isinstance(chat_result, str) else ""
    files = getattr(chat_result, "files", None) or []

    if not text.strip() and not files:
        return

    processed: list[dict[str, Any]] = []
    for uploaded in files:
        try:
            processed.append(
                process_uploaded_file(uploaded, DEFAULT_FILE_ENCODING)
            )
        except Exception as exc:  # noqa: BLE001
            processed.append(
                {
                    "name": uploaded.name,
                    "type": "error",
                    "summary": f"파일 처리 실패: {exc}",
                    "df": None,
                }
            )

    if processed:
        processed = prepare_files_in_workspace(processed)

    apply_chat_files(processed)
    files_for_model = build_files_for_model(processed)
    has_attachments = files_for_model is not None

    user_msg = {"role": "user", "content": text, "files": processed}
    append_message(user_msg)
    render_message(user_msg, len(get_messages()) - 1)

    assistant_msg: dict[str, Any] = {"role": "assistant", "content": ""}
    with st.chat_message("assistant"):
        if not settings["ollama_connected"]:
            reply = "Ollama에 연결되지 않았습니다. 서버 실행 후 모델 목록을 새로고침하세요."
            st.warning(reply)
            assistant_msg["content"] = reply
        else:
            active_df = st.session_state.df
            ctx = build_active_context(active_df)
            model = settings["model"]
            try:
                response_mode = None
                if send_think:
                    response_mode = "thinking" if think else "instant"
                result, thinking_sec = run_with_thinking_status(
                    lambda: call_ollama(
                        settings["base_url"],
                        model=model,
                        system_prompt=settings["system_prompt"],
                        data_context=ctx,
                        temperature=DEFAULT_TEMPERATURE,
                        max_tokens=DEFAULT_MAX_TOKENS,
                        attached_files=files_for_model,
                        think=think,
                        send_think=send_think,
                    ),
                    response_mode=response_mode,
                )
                assistant_msg["thinking_seconds"] = round(thinking_sec, 1)
                assistant_msg["think_enabled"] = think
                if response_mode:
                    assistant_msg["response_mode"] = response_mode
                if result.thinking:
                    assistant_msg["thinking_trace"] = result.thinking
                    with st.expander("추론 과정 (Thinking)", expanded=False):
                        st.markdown(result.thinking)
                reply = result.content
                st.markdown(reply)
                assistant_msg["content"] = reply
                if has_attachments:
                    blocks = code_extract_python_blocks(reply)
                    if blocks:
                        assistant_msg["executable_code"] = blocks[-1]
                        assistant_msg["execution_status"] = "pending"
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")
                reply = f"Ollama HTTP 오류 ({exc.code}): {body}"
                st.error(reply)
                assistant_msg["content"] = reply
            except Exception as exc:  # noqa: BLE001
                reply = f"오류: {exc}"
                st.error(reply)
                assistant_msg["content"] = reply

    append_message(assistant_msg)
    st.rerun()
