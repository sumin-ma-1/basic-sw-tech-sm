from __future__ import annotations

from typing import Any

import streamlit as st


def render_file_preview(
    file_info: dict[str, Any],
    *,
    max_preview_rows: int,
    max_preview_chars: int,
) -> None:
    if file_info.get("type") == "error":
        st.error(file_info.get("summary", "파일 처리 실패"))
        return
    if file_info.get("df") is not None:
        df = file_info["df"]
        st.dataframe(df.head(max_preview_rows), use_container_width=True)
        st.caption(f"{len(df):,}행 × {len(df.columns)}열 · 상위 {max_preview_rows}행")
        return
    summary = file_info.get("summary", "")
    preview = summary[:max_preview_chars]
    if len(summary) > max_preview_chars:
        preview += "\n… (미리보기)"
    st.text(preview)

