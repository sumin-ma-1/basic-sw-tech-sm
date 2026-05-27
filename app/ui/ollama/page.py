from __future__ import annotations

import streamlit as st

from app.api.ollama import (
    delete_ollama_model,
    fetch_ollama_models,
    fetch_ollama_version,
    pull_ollama_model,
)


def render_ollama_page(
    *,
    default_base_url: str,
    icon_refresh: str,
    icon_download: str,
    icon_delete: str,
) -> None:
    st.title("Ollama 관리")
    st.caption("모델 다운로드·삭제·상태 확인 · URL은 **AI 채팅** 사이드바와 공유됩니다")

    if "ollama_base_url" not in st.session_state:
        st.session_state.ollama_base_url = default_base_url

    base_url = (
        st.text_input(
            "Ollama URL",
            value=st.session_state.ollama_base_url,
            key="ollama_page_url",
            placeholder="http://localhost:11434",
        )
        .rstrip("/")
        or default_base_url
    )
    st.session_state.ollama_base_url = base_url

    if st.button(
        "연결·목록 새로고침",
        icon=icon_refresh,
        help="Ollama 연결 및 설치 모델 목록 갱신",
    ):
        st.session_state.ollama_models = fetch_ollama_models(base_url)
        st.rerun()

    if "ollama_models" not in st.session_state:
        st.session_state.ollama_models = []

    connected = bool(st.session_state.ollama_models)
    if not connected:
        st.session_state.ollama_models = fetch_ollama_models(base_url)
        connected = bool(st.session_state.ollama_models)

    models = st.session_state.ollama_models or []
    version = fetch_ollama_version(base_url) if connected else None

    if connected:
        label = f"연결됨 · {len(models)}개 모델"
        if version:
            label += f" · v{version}"
        st.success(label)
    else:
        st.warning("미연결 — URL · SSH 터널 · `ollama serve` 확인")

    st.divider()
    st.subheader("설치된 모델")
    if models:
        st.selectbox("모델", models, key="ollama_installed_select", disabled=not connected)
    elif connected:
        st.info("설치된 모델이 없습니다. 아래에서 받을 수 있습니다.")
    else:
        st.warning("목록을 불러올 수 없습니다.")

    st.divider()
    st.subheader("모델 받기")
    st.caption("예: `qwen3:8b`, `llama3.2` · [Ollama 라이브러리](https://ollama.com/library)")
    pull_name = st.text_input(
        "모델 이름",
        placeholder="qwen3:8b",
        key="ollama_pull_name",
        disabled=not connected,
    )
    if st.button("다운로드 시작", type="primary", icon=icon_download, disabled=not connected):
        if not pull_name.strip():
            st.error("모델 이름을 입력하세요.")
        else:
            progress = st.progress(0.0, text="준비 중…")
            status_box = st.empty()

            def on_pull_update(ratio: float | None, status: str) -> None:
                label2 = status or "다운로드 중…"
                if ratio is not None:
                    progress.progress(ratio, text=label2)
                else:
                    progress.progress(0.0, text=label2)
                status_box.caption(label2)

            ok, message = pull_ollama_model(base_url, pull_name, on_update=on_pull_update)
            progress.empty()
            status_box.empty()
            if ok:
                st.success(message)
                st.session_state.ollama_models = fetch_ollama_models(base_url)
                st.rerun()
            else:
                st.error(message)

    st.divider()
    st.subheader("모델 삭제")
    if not connected or not models:
        st.caption("연결되고 모델이 있을 때 삭제할 수 있습니다.")
    else:
        delete_name = st.session_state.get("ollama_installed_select", models[0])
        st.caption(f"삭제 대상: **{delete_name}** (위 목록에서 선택)")
        confirm = st.checkbox("삭제 확인", key="ollama_delete_confirm")
        if st.button("선택 모델 삭제", icon=icon_delete, disabled=not confirm):
            ok, message = delete_ollama_model(base_url, delete_name)
            if ok:
                st.success(message)
                st.session_state.ollama_models = fetch_ollama_models(base_url)
                st.rerun()
            else:
                st.error(message)

