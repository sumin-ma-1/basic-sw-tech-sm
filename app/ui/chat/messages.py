from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st

from app.config import ICON_DOWNLOAD
from app.ui.chat.thinking_status import format_thinking_label


def render_execution_downloads(workspace: Path, filenames: list[str]) -> None:
    st.markdown("**생성된 파일**")
    for fname in filenames:
        path = workspace / fname
        if not path.is_file():
            continue
        data = path.read_bytes()
        mime = "application/octet-stream"
        if fname.lower().endswith(".csv"):
            mime = "text/csv"
        elif fname.lower().endswith((".png", ".jpg", ".jpeg")):
            mime = f"image/{fname.rsplit('.', 1)[-1]}"
        st.download_button(
            fname,
            data=data,
            file_name=fname,
            mime=mime,
            key=f"dl_{workspace.name}_{fname}",
            icon=ICON_DOWNLOAD,
            use_container_width=True,
        )


def render_code_execution_panel(
    msg: dict[str, Any],
    msg_index: int,
    *,
    extract_code_explanation: Callable[[str], str],
    get_chat_workspace: Callable[[], Path],
    execute_python_code: Callable[[str, Path], dict[str, Any]],
    patch_message: Callable[..., None],
) -> None:
    status = msg.get("execution_status")
    code = msg.get("executable_code")
    if not code:
        return

    explanation = extract_code_explanation(msg.get("content", ""))
    st.markdown(explanation)
    st.markdown("**실행 코드**")
    st.code(code, language="python")

    if status == "pending":
        st.warning("코드 실행 전 내용을 확인하고 승인해 주세요.")
        col_ok, col_no = st.columns(2)
        with col_ok:
            if st.button(
                "✅ 실행 승인",
                key=f"exec_approve_{msg_index}",
                use_container_width=True,
                type="primary",
            ):
                workspace = get_chat_workspace()
                with st.spinner("코드 실행 중..."):
                    result = execute_python_code(code, workspace)
                patch_message(
                    msg_index,
                    execution_status="completed",
                    execution_result=result,
                )
                st.rerun()
        with col_no:
            if st.button(
                "❌ 실행 취소",
                key=f"exec_cancel_{msg_index}",
                use_container_width=True,
            ):
                patch_message(msg_index, execution_status="cancelled")
                st.rerun()
        return

    if status == "cancelled":
        st.info("코드 실행이 취소되었습니다.")
        return

    result = msg.get("execution_result") or {}
    if result.get("stdout") or result.get("stderr"):
        with st.expander("실행 로그", expanded=False):
            if result.get("stdout"):
                st.markdown("**실행 결과**")
                st.caption(
                    "프로그램이 만들어 낸 출력입니다. "
                    "표·숫자·완료 메시지 등이 여기에 표시됩니다."
                )
                st.code(result["stdout"])
            if result.get("stderr"):
                st.markdown("**상세 기록**")
                st.caption(
                    "실행 과정 안내, 경고, 오류 메시지입니다. "
                    "문제가 있을 때 이 내용을 확인하세요."
                )
                st.code(result["stderr"])
    if result.get("success"):
        st.success("실행이 완료되었습니다.")
    else:
        st.error(f"실행 실패 (종료 코드 {result.get('returncode', '?')})")

    new_files = result.get("new_files") or []
    if new_files:
        render_execution_downloads(get_chat_workspace(), new_files)


def render_message(
    msg: dict[str, Any],
    msg_index: int,
    *,
    render_file_preview: Callable[[dict[str, Any]], None],
    render_code_execution_panel_cb: Callable[[dict[str, Any], int], None],
) -> None:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("thinking_seconds") is not None:
            st.caption(
                format_thinking_label(
                    float(msg["thinking_seconds"]),
                    finished=True,
                    response_mode=msg.get("response_mode"),
                )
            )
        if msg["role"] == "assistant" and msg.get("thinking_trace"):
            with st.expander("추론 과정 (Thinking)", expanded=False):
                st.markdown(msg["thinking_trace"])
        if msg.get("content") and not msg.get("executable_code"):
            st.markdown(msg["content"])
        for f in msg.get("files", []):
            with st.expander(f"{f['name']} ({f['type']})", expanded=False):
                render_file_preview(f)
        if msg["role"] == "assistant" and msg.get("executable_code"):
            render_code_execution_panel_cb(msg, msg_index)

