from __future__ import annotations

import platform
import subprocess
from urllib.parse import urlparse

import streamlit as st

from app.api.ollama import (
    delete_ollama_model,
    fetch_ollama_models,
    fetch_ollama_server_resources,
    fetch_ollama_version,
    format_bytes,
    processor_split,
    pull_ollama_model,
)
from app.remote_ssh import (
    get_ssh_probe_hint,
    get_ssh_target,
    resolve_remote_gpu_names,
    resolve_remote_host_hint,
    save_remote_gpu_names,
    save_remote_host_hint,
)
from app.ui.chat.response_mode import clear_model_capabilities_cache


def _load_ollama_resources(base_url: str) -> dict:
    return fetch_ollama_server_resources(base_url)


def _load_remote_host_hint() -> str:
    key = "_ollama_remote_host_hint"
    if key not in st.session_state:
        st.session_state[key] = resolve_remote_host_hint()
    return st.session_state[key]


def _load_remote_gpu_names() -> list[str]:
    key = "_ollama_remote_gpu_names"
    if key not in st.session_state:
        st.session_state[key] = resolve_remote_gpu_names()
    return st.session_state[key]


def _detect_local_linux_host_and_gpu() -> tuple[str, list[str]]:
    """리눅스에서 앱을 직접 실행할 때 hostname/GPU 이름을 자동 수집."""
    if platform.system().lower() != "linux":
        return "", []

    host = ""
    gpu_names: list[str] = []
    try:
        host = (
            subprocess.run(
                ["hostname"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        host = ""

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
        gpu_names = [line.strip() for line in out.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        gpu_names = []

    return host, gpu_names


@st.dialog("모델 삭제 확인", width="large")
def _confirm_delete_ollama_model_dialog(
    *,
    base_url: str,
    model_name: str,
    icon_delete: str,
) -> None:
    st.warning(f"정말 `{model_name}` 모델을 삭제할까요? (디스크에서 제거됩니다.)")
    st.caption("취소하면 아무 작업도 하지 않습니다.")
    col_del, col_cancel = st.columns(2)
    with col_del:
        if st.button(
            "삭제",
            type="primary",
            icon=icon_delete,
            use_container_width=True,
        ):
            ok, message = delete_ollama_model(base_url, model_name)
            if ok:
                st.success(message)
                st.session_state.ollama_models = fetch_ollama_models(base_url)
                st.session_state.ollama_resources = _load_ollama_resources(base_url)
                st.session_state.ollama_resources_url = base_url
                clear_model_capabilities_cache()
            else:
                st.error(message)
            st.rerun()
    with col_cancel:
        if st.button("취소", use_container_width=True):
            st.rerun()


def _render_remote_server_manual_setup(
    *,
    remote_hint: str,
    gpu_names: list[str],
    is_tunnel: bool,
) -> None:
    if not is_tunnel:
        return
    need_manual = not remote_hint or not gpu_names
    if not need_manual and not get_ssh_target():
        return

    with st.expander("원격 서버 정보 (수동 입력)", expanded=need_manual and not remote_hint):
        st.caption(
            "SSH 터널은 **비밀번호**로 연결해도 됩니다. "
            "다만 hostname·GPU **자동 조회**는 SSH **키**가 등록되어 있어야 합니다."
        )
        probe_hint = get_ssh_probe_hint()
        if probe_hint and need_manual:
            st.warning(probe_hint)

        host_value = remote_hint or ""
        gpu_value = ", ".join(gpu_names)
        manual_host = st.text_input(
            "원격 hostname",
            value=host_value,
            placeholder="spark-005c",
            key="manual_remote_host_input",
        )
        manual_gpu = st.text_input(
            "GPU 이름",
            value=gpu_value,
            placeholder="NVIDIA GB10",
            key="manual_remote_gpu_input",
        )
        st.caption("원격 SSH 세션에서 `hostname`, `nvidia-smi --query-gpu=name --format=csv,noheader` 결과를 입력하세요.")
        if st.button("저장", key="save_manual_remote_server"):
            save_remote_host_hint(manual_host)
            save_remote_gpu_names([g.strip() for g in manual_gpu.split(",") if g.strip()])
            st.session_state.pop("_ollama_remote_host_hint", None)
            st.session_state.pop("_ollama_remote_gpu_names", None)
            st.rerun()


def render_server_resources(resources: dict, *, base_url: str) -> None:
    st.subheader("서버 리소스")
    parsed = urlparse(base_url)
    host = parsed.hostname or base_url
    is_tunnel = host in {"localhost", "127.0.0.1"}
    remote_hint = _load_remote_host_hint()
    local_linux_host, local_linux_gpu_names = _detect_local_linux_host_and_gpu()
    if is_tunnel:
        if remote_hint:
            st.caption(f"서버 식별: localhost (SSH 터널) → 원격 `{remote_hint}`")
        elif local_linux_host:
            st.caption(f"서버 식별: 로컬 리눅스 `{local_linux_host}`")
        elif get_ssh_target():
            probe_hint = get_ssh_probe_hint()
            st.caption(
                "서버 식별: localhost (SSH 터널) · 원격 hostname 자동 조회 실패"
                + (f" — {probe_hint}" if probe_hint else "")
            )
        else:
            st.caption(
                "서버 식별: localhost (SSH 터널) · "
                "`chat_history/ollama_ssh_target.txt` 또는 환경 변수 `OLLAMA_SSH`로 자동 조회 가능"
            )
    else:
        st.caption(f"서버 식별: {host}")

    has_system_ram = resources.get("total_memory_bytes") is not None
    has_gpu_vram_api = bool(resources.get("gpus"))

    installed_count = int(resources.get("installed_count") or 0)
    running_count = int(resources.get("running_count") or 0)

    # 표/카드에서 사용할 "로드된 모델"을 모델명 기준으로 중복 제거
    running = resources.get("running") or []
    gpus = resources.get("gpus") or []

    running_rows: list[dict[str, str]] = []
    for model in running:
        name = model.get("name") or model.get("model") or "?"
        size = int(model.get("size") or 0)
        size_vram = int(model.get("size_vram") or 0)
        expires_at = model.get("expires_at") or model.get("until") or ""
        ctx_len = model.get("context_length") or ""

        row: dict[str, str] = {
            "모델": str(name),
            "크기(디스크)": format_bytes(size),
            "VRAM(로드)": format_bytes(size_vram),
            "CPU/GPU 대략": processor_split(size, size_vram),
        }
        if ctx_len != "":
            row["context_len"] = str(ctx_len)
        if expires_at:
            row["expires"] = str(expires_at)
        running_rows.append(row)

    seen_model_names: set[str] = set()
    running_rows_unique: list[dict[str, str]] = []
    for r in running_rows:
        model_name = str(r.get("모델", "?")).strip() or "?"
        if model_name in seen_model_names:
            continue
        seen_model_names.add(model_name)
        running_rows_unique.append(r)
    running_rows = running_rows_unique

    api_running_count = int(resources.get("running_count") or 0)
    if api_running_count and len(running_rows) > api_running_count:
        running_rows = running_rows[:api_running_count]

    running_count = len(running_rows)

    # 연결된 GPU 이름(가능한 경우)
    gpu_names = []
    for g in gpus:
        if not isinstance(g, dict):
            continue
        name = str(g.get("name") or "").strip()
        if name:
            gpu_names.append(name)
    if not gpu_names and local_linux_gpu_names:
        gpu_names = local_linux_gpu_names
    if not gpu_names:
        gpu_names = _load_remote_gpu_names()
    if gpu_names:
        st.info(f"연결된 GPU: **{', '.join(gpu_names)}**")

    _render_remote_server_manual_setup(
        remote_hint=remote_hint,
        gpu_names=gpu_names,
        is_tunnel=is_tunnel,
    )

    st.markdown("**Ollama 모델 리소스**")
    st.caption(
        "아래 카드·표는 **설치·로드된 모델** 기준(`/api/tags`, `/api/ps`)입니다. "
        "서버 RAM·GPU 전체 용량과는 다를 수 있습니다."
    )

    col_disk, col_loaded, col_vram = st.columns(3)
    with col_disk:
        with st.container(border=True):
            st.caption("모델 저장 (디스크)")
            disk_value = format_bytes(resources.get("filesystem_used_bytes"))
            st.write(disk_value)
            st.badge(f"{installed_count}개 설치", color="gray")
    with col_loaded:
        with st.container(border=True):
            st.caption("로드 RAM 합계")
            mem_value = format_bytes(resources.get("running_size_bytes"))
            st.write(mem_value)
            st.badge(f"{running_count}개 실행 중", color="gray")
    with col_vram:
        with st.container(border=True):
            st.caption("로드 VRAM 합계")
            vram_value = format_bytes(resources.get("running_vram_bytes"))
            st.write(vram_value)
            st.badge(f"{running_count}개 모델", color="gray")

    # GPU 메모리 임계치 배너(가능할 때만)
    vram_threshold = 0.90
    if gpus:
        total_vram_sum = sum(int(g.get("total_memory") or 0) for g in gpus)
        free_vram_sum = sum(int(g.get("free_memory") or 0) for g in gpus)
        used_vram_sum = max(total_vram_sum - free_vram_sum, 0)
        if total_vram_sum:
            used_ratio = used_vram_sum / total_vram_sum
            if used_ratio >= vram_threshold:
                st.error(
                    f"메모리 임계치 초과: VRAM {format_bytes(used_vram_sum)} / "
                    f"{format_bytes(total_vram_sum)} ({used_ratio*100:.0f}%)"
                )

    if not has_system_ram and not has_gpu_vram_api:
        st.info(
            "서버 **전체** RAM·GPU VRAM은 이 Ollama 버전에서 `/api/info`로 제공되지 않아 "
            "별도 패널을 표시하지 않습니다. OS 수치는 서버에서 `free -h`, `nvidia-smi`로 확인하세요. "
            "(Ollama 업그레이드 시 자동 표시 가능)"
        )

    if has_system_ram:
        with st.expander("시스템 RAM (서버 전체)", expanded=False):
            total = int(resources["total_memory_bytes"])
            free = int(resources.get("free_memory_bytes") or 0)
            used = max(total - free, 0)
            st.markdown(
                f"**시스템 RAM** · 사용 {format_bytes(used)} / 전체 {format_bytes(total)}"
            )
            st.progress(min(used / total, 1.0) if total else 0.0)

    if has_gpu_vram_api:
        with st.expander("GPU / VRAM (서버 전체)", expanded=False):
            st.markdown("**GPU별 VRAM 여유**")
            for gpu in gpus:
                name = gpu.get("name") or gpu.get("gpu_id") or "GPU"
                total_vram = int(gpu.get("total_memory") or 0)
                free_vram = int(gpu.get("free_memory") or 0)
                used_vram = max(total_vram - free_vram, 0)
                st.caption(
                    f"{name} · VRAM {format_bytes(used_vram)} / {format_bytes(total_vram)} "
                    f"(여유 {format_bytes(free_vram)})"
                )
                if total_vram:
                    st.progress(min(used_vram / total_vram, 1.0))

    with st.expander("로드된 모델 (`ollama ps`)", expanded=True):
        st.markdown("**현재 메모리에 로드된 모델**")
        if running_count and not running:
            st.caption("`ollama ps` 응답을 불러오는 중 문제가 있었습니다.")
        elif running_rows:
            # row = 모델, column = 측정 항목 (모델 개수와 무관하게 표 형태를 고정)
            has_expires = any("expires" in r for r in running_rows)
            has_context_len = any("context_len" in r for r in running_rows)

            columns = ["모델", "크기(디스크)", "VRAM(로드)", "CPU/GPU 대략"]
            if has_expires:
                columns.append("expires")
            if has_context_len:
                columns.append("context_len")

            table_rows: list[dict[str, str]] = []
            for r in running_rows:
                table_rows.append({c: r.get(c, "") for c in columns})

            row_count = len(table_rows)
            # Streamlit DataFrame은 고정 height에서 내부적으로 빈 행이 보일 수 있어,
            # row 수에 맞춰 높이를 동적으로 조절합니다.
            dynamic_height = int(min(max(120, 36 * (row_count + 1) + 20), 420))
            st.dataframe(
                table_rows,
                use_container_width=True,
                hide_index=True,
                height=dynamic_height,
            )

            # 컬럼 의미(짧게)
            if has_expires:
                st.caption("`expires`: Ollama에서 해당 모델을 메모리에서 내릴 시각(keep_alive 만료 시점)입니다.")
            if has_context_len:
                st.caption("`context_len`: 모델이 한 번에 처리할 수 있는 입력+출력 컨텍스트 길이(토큰 상한)입니다.")
        elif installed_count:
            st.info("현재 메모리에 로드된 모델이 없습니다.")
        else:
            st.caption("설치된 모델이 없습니다.")

    with st.expander("운영 팁", expanded=False):
        st.warning(
            "모델 **pull**은 디스크 공간을, **실행·채팅**은 RAM/VRAM을 사용합니다. "
            "용량이 부족하면 다운로드·로드가 실패합니다 (`ollama stop` · 불필요 모델 삭제)."
        )
        st.caption("추가로, `ollama ps`에 떠 있는 모델은 메모리에 올라와 있는 상태입니다.")


def render_ollama_page(
    *,
    default_base_url: str,
    icon_refresh: str,
    icon_download: str,
    icon_delete: str,
) -> None:
    st.title("Ollama 관리")
    st.caption("모델 다운로드·삭제·상태 확인·URL은 **AI 채팅** 사이드바와 공유됩니다")

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
        st.session_state.pop("_ollama_remote_host_hint", None)
        st.session_state.pop("_ollama_remote_gpu_names", None)
        st.session_state.ollama_models = fetch_ollama_models(base_url)
        st.session_state.ollama_resources = _load_ollama_resources(base_url)
        st.session_state.ollama_resources_url = base_url
        clear_model_capabilities_cache()
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
            label += f" · Ollama v{version}"
        st.success(label)
        if "ollama_resources" not in st.session_state or st.session_state.get(
            "ollama_resources_url"
        ) != base_url:
            st.session_state.ollama_resources = _load_ollama_resources(base_url)
            st.session_state.ollama_resources_url = base_url
        render_server_resources(st.session_state.ollama_resources, base_url=base_url)
    else:
        st.warning("미연결, URL · SSH 터널 · `ollama serve` 확인")
        st.session_state.pop("ollama_resources", None)

    st.divider()
    st.subheader("설치된 모델")
    if models:
        resources = st.session_state.get("ollama_resources") or {}
        size_by_name = {
            m.get("name"): int(m.get("size") or 0)
            for m in (resources.get("installed") or [])
            if m.get("name")
        }
        st.selectbox(
            "모델",
            models,
            format_func=lambda name: (
                f"{name} ({format_bytes(size_by_name.get(name))})"
                if size_by_name.get(name)
                else name
            ),
            key="ollama_installed_select",
            disabled=not connected,
        )
    elif connected:
        st.info("설치된 모델이 없습니다. 아래에서 받을 수 있습니다.")
    else:
        st.warning("목록을 불러올 수 없습니다.")

    st.divider()
    st.subheader("모델 받기")
    resources = st.session_state.get("ollama_resources") or {}
    st.caption(
        f"현재 설치 {resources.get('installed_count', len(models))}개 · "
        f"디스크 약 {format_bytes(resources.get('filesystem_used_bytes'))} · "
        f"로드 중 {format_bytes(resources.get('running_size_bytes'))}"
    )
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
                st.session_state.ollama_resources = _load_ollama_resources(base_url)
                st.session_state.ollama_resources_url = base_url
                clear_model_capabilities_cache()
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
        if st.button("선택 모델 삭제", icon=icon_delete, disabled=not connected):
            _confirm_delete_ollama_model_dialog(
                base_url=base_url,
                model_name=delete_name,
                icon_delete=icon_delete,
            )

