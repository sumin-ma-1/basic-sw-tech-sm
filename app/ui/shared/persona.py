from __future__ import annotations

import uuid
from typing import Any

import streamlit as st

from app.config import APP_SETTINGS_FILE, CHAT_HISTORY_DIR
from app.services.storage import save_app_settings as storage_save_app_settings
from app.utils import now_iso

PRESET_PREFIX = "preset:"
CUSTOM_PREFIX = "custom:"
PERSONA_PRESETS: dict[str, dict[str, str]] = {
    "data_analyst": {
        "label": "데이터 분석가",
        "summary": (
            "업로드·활성 데이터 **요약**을 바탕으로 인사이트를 제시합니다. "
            "한국어·실무 톤이며, **요약에 없는 수치는 추측하지 않습니다**."
        ),
        "prompt": (
            "당신은 데이터 분석 전문가입니다. 업로드된 데이터 요약을 바탕으로 "
            "한국어로 명확하고 실용적인 인사이트를 제공하세요. "
            "수치는 요약에 있는 것만 인용하고, 없는 통계는 추측하지 마세요."
        ),
    },
    "code_assistant": {
        "label": "코딩 어시스턴트",
        "summary": (
            "코드 작성·디버깅·리팩터링·알고리즘 설명에 특화됩니다. "
            "**실행 가능한 예시**를 선호하고, 가정·전제는 명시합니다."
        ),
        "prompt": (
            "당신은 숙련된 소프트웨어 개발 어시스턴트입니다. "
            "코드 작성, 디버깅, 리팩터링, 알고리즘 설명을 한국어로 명확히 도와주세요. "
            "가능하면 실행 가능한 예시 코드를 제시하고, 가정은 명시하세요."
        ),
    },
    "learning_mentor": {
        "label": "학습 멘토",
        "summary": (
            "개념을 **단계별·쉬운 말**로 설명하고, 비유·짧은 예시를 씁니다. "
            "학습자 수준에 맞춰 질문을 유도하며 **격려하는 톤**을 유지합니다."
        ),
        "prompt": (
            "당신은 친절한 학습 멘토입니다. "
            "개념을 단계별로 쉽게 설명하고, 비유와 짧은 예시를 활용하세요. "
            "학습자 수준에 맞춰 질문을 유도하며, 한국어로 격려하는 톤을 유지하세요."
        ),
    },
}
DEFAULT_PERSONA_KEY = "data_analyst"
DEFAULT_SELECTED_PERSONA = f"{PRESET_PREFIX}{DEFAULT_PERSONA_KEY}"

PERSONA_CREATE_HINT = (
    "코드 실행·첨부 파일·데이터셋 규칙은 앱이 대화 시 자동으로 추가합니다."
)


def render_in_use_badge() -> None:
    st.badge("사용 중", icon=":material/check_circle:", color="green")


def compose_persona_prompt(role: str, style: str = "", constraints: str = "") -> str:
    parts: list[str] = []
    if role.strip():
        parts.append(role.strip())
    if style.strip():
        parts.append(f"응답 방식: {style.strip()}")
    if constraints.strip():
        parts.append(f"주의사항: {constraints.strip()}")
    return "\n\n".join(parts)


def persona_field_values(persona: dict[str, str]) -> tuple[str, str, str]:
    if "role" in persona or "style" in persona or "constraints" in persona:
        return (
            persona.get("role", ""),
            persona.get("style", ""),
            persona.get("constraints", ""),
        )
    return (persona.get("prompt", ""), "", "")


def render_persona_part_fields(
    key_prefix: str,
    *,
    role: str = "",
    style: str = "",
    constraints: str = "",
    show_hint: bool = True,
) -> tuple[str, str, str]:
    if show_hint:
        st.caption(PERSONA_CREATE_HINT)
    role_val = st.text_area(
        "역할",
        value=role,
        height=100,
        placeholder="예: 당신은 통계·데이터 분석을 돕는 전문가입니다.",
        key=f"{key_prefix}_role",
    )
    style_val = st.text_area(
        "응답 방식",
        value=style,
        height=80,
        placeholder="예: 한국어로 단계별 설명, 표·요약을 활용, 초보자도 이해하기 쉽게",
        key=f"{key_prefix}_style",
    )
    constraints_val = st.text_area(
        "주의사항",
        value=constraints,
        height=80,
        placeholder="예: 요약에 없는 수치는 추측하지 말 것, 불확실하면 명시",
        key=f"{key_prefix}_constraints",
    )
    return role_val, style_val, constraints_val


def save_app_settings() -> None:
    storage_save_app_settings(
        chat_history_dir=CHAT_HISTORY_DIR,
        app_settings_file=APP_SETTINGS_FILE,
        selected_persona_id=st.session_state.selected_persona_id,
        custom_personas=st.session_state.custom_personas,
    )


def migrate_app_settings(data: dict[str, Any]) -> dict[str, Any]:
    if "selected_persona_id" in data:
        return {
            "selected_persona_id": data.get(
                "selected_persona_id", DEFAULT_SELECTED_PERSONA
            ),
            "custom_personas": data.get("custom_personas", {}),
        }
    persona_key = data.get("persona_key", DEFAULT_PERSONA_KEY)
    custom_personas: dict[str, dict[str, str]] = {}
    selected = f"{PRESET_PREFIX}{persona_key}"
    if persona_key == "custom":
        legacy_prompt = data.get("custom_system_prompt", "")
        if legacy_prompt.strip():
            cid = str(uuid.uuid4())
            legacy = legacy_prompt.strip()
            custom_personas[cid] = {
                "id": cid,
                "title": "커스텀",
                "prompt": legacy,
                "role": legacy,
                "style": "",
                "constraints": "",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            selected = f"{CUSTOM_PREFIX}{cid}"
    if persona_key not in PERSONA_PRESETS and not selected.startswith(CUSTOM_PREFIX):
        selected = DEFAULT_SELECTED_PERSONA
    return {"selected_persona_id": selected, "custom_personas": custom_personas}


def build_persona_ids() -> list[str]:
    ids = [f"{PRESET_PREFIX}{key}" for key in PERSONA_PRESETS]
    customs = sorted(
        st.session_state.custom_personas.values(),
        key=lambda p: p["updated_at"],
        reverse=True,
    )
    ids.extend(f"{CUSTOM_PREFIX}{persona['id']}" for persona in customs)
    return ids


def persona_display_label(persona_id: str) -> str:
    if persona_id.startswith(PRESET_PREFIX):
        key = persona_id.removeprefix(PRESET_PREFIX)
        return f"{PERSONA_PRESETS[key]['label']}"
    cid = persona_id.removeprefix(CUSTOM_PREFIX)
    return f"{st.session_state.custom_personas[cid]['title']}"


def ensure_valid_selected_persona() -> None:
    ids = build_persona_ids()
    if st.session_state.selected_persona_id not in ids:
        st.session_state.selected_persona_id = ids[0] if ids else DEFAULT_SELECTED_PERSONA


def resolve_system_prompt() -> str:
    selected = st.session_state.selected_persona_id
    if selected.startswith(PRESET_PREFIX):
        key = selected.removeprefix(PRESET_PREFIX)
        return PERSONA_PRESETS[key]["prompt"]
    if selected.startswith(CUSTOM_PREFIX):
        cid = selected.removeprefix(CUSTOM_PREFIX)
        persona = st.session_state.custom_personas.get(cid)
        if persona:
            return persona["prompt"]
    return PERSONA_PRESETS[DEFAULT_PERSONA_KEY]["prompt"]


def upsert_custom_persona(
    title: str,
    *,
    role: str,
    style: str = "",
    constraints: str = "",
    persona_id: str | None = None,
) -> str:
    prompt = compose_persona_prompt(role, style, constraints)
    ts = now_iso()
    record = {
        "id": "",
        "title": title,
        "prompt": prompt,
        "role": role.strip(),
        "style": style.strip(),
        "constraints": constraints.strip(),
    }
    if persona_id is None:
        persona_id = str(uuid.uuid4())
        record["id"] = persona_id
        record["created_at"] = ts
        record["updated_at"] = ts
        st.session_state.custom_personas[persona_id] = record
    else:
        existing = st.session_state.custom_personas[persona_id]
        record["id"] = persona_id
        record["created_at"] = existing.get("created_at", ts)
        record["updated_at"] = ts
        st.session_state.custom_personas[persona_id] = record
    return persona_id


def delete_custom_persona(persona_id: str) -> None:
    st.session_state.custom_personas.pop(persona_id, None)
    if st.session_state.selected_persona_id == f"{CUSTOM_PREFIX}{persona_id}":
        st.session_state.selected_persona_id = DEFAULT_SELECTED_PERSONA


@st.dialog("커스텀 Persona 생성", width="large")
def custom_persona_create_dialog() -> None:
    st.caption("역할·응답 방식·주의사항을 나눠 작성하면 저장 시 하나의 시스템 프롬프트로 합쳐집니다.")
    title = st.text_input("이름", placeholder="예: 통계 튜터", key="persona_create_title")
    role, style, constraints = render_persona_part_fields("persona_create")
    if st.button("저장", type="primary", use_container_width=True):
        if not title.strip():
            st.error("이름을 입력해 주세요.")
            return
        if not role.strip():
            st.error("역할을 입력해 주세요.")
            return
        new_id = upsert_custom_persona(
            title.strip(),
            role=role,
            style=style,
            constraints=constraints,
        )
        st.session_state.selected_persona_id = f"{CUSTOM_PREFIX}{new_id}"
        save_app_settings()
        st.rerun()


@st.dialog("시스템 프롬프트 관리", width="large")
def system_prompt_manage_dialog() -> None:
    st.markdown("##### 프리셋")
    st.caption("기본 제공 Persona입니다.")
    for key, meta in PERSONA_PRESETS.items():
        persona_id = f"{PRESET_PREFIX}{key}"
        is_active = st.session_state.selected_persona_id == persona_id
        with st.container(border=True):
            if is_active:
                render_in_use_badge()
            with st.expander(meta["label"], expanded=is_active):
                st.markdown(meta["summary"])
                if st.button(
                    "이 Persona 사용",
                    key=f"use_preset_{key}",
                    use_container_width=True,
                    disabled=is_active,
                ):
                    st.session_state.selected_persona_id = persona_id
                    save_app_settings()
                    st.rerun()

    st.divider()
    st.markdown("##### 커스텀")
    customs = st.session_state.custom_personas
    if not customs:
        st.info("저장된 커스텀 Persona가 없습니다. '새로 생성하기'로 추가하세요.")
        return

    for persona in sorted(
        customs.values(), key=lambda p: p["updated_at"], reverse=True
    ):
        pid = persona["id"]
        persona_id = f"{CUSTOM_PREFIX}{pid}"
        is_active = st.session_state.selected_persona_id == persona_id
        with st.container(border=True):
            if is_active:
                render_in_use_badge()
            with st.expander(persona["title"], expanded=is_active):
                st.caption(persona["updated_at"])
                if st.button(
                    "이 Persona 사용",
                    key=f"use_custom_{pid}",
                    use_container_width=True,
                    disabled=is_active,
                ):
                    st.session_state.selected_persona_id = persona_id
                    save_app_settings()
                    st.rerun()
                edit_title = st.text_input("이름", value=persona["title"], key=f"mt_{pid}")
                leg_role, leg_style, leg_constraints = persona_field_values(persona)
                edit_role, edit_style, edit_constraints = render_persona_part_fields(
                    f"persona_edit_{pid}",
                    role=leg_role,
                    style=leg_style,
                    constraints=leg_constraints,
                    show_hint=False,
                )
                col_save, col_del = st.columns(2)
                with col_save:
                    if st.button("저장", key=f"ms_{pid}", use_container_width=True):
                        if not edit_title.strip():
                            st.error("이름을 입력해 주세요.")
                        elif not edit_role.strip():
                            st.error("역할을 입력해 주세요.")
                        else:
                            upsert_custom_persona(
                                edit_title.strip(),
                                role=edit_role,
                                style=edit_style,
                                constraints=edit_constraints,
                                persona_id=pid,
                            )
                            save_app_settings()
                            st.rerun()
                with col_del:
                    if st.button("삭제", key=f"md_{pid}", use_container_width=True):
                        delete_custom_persona(pid)
                        save_app_settings()
                        st.rerun()


def render_system_prompt_section() -> str:
    ensure_valid_selected_persona()
    ids = build_persona_ids()
    current_index = ids.index(st.session_state.selected_persona_id)

    selected_id = st.selectbox(
        "Persona",
        ids,
        index=current_index,
        format_func=persona_display_label,
        label_visibility="collapsed",
    )
    if selected_id != st.session_state.selected_persona_id:
        st.session_state.selected_persona_id = selected_id
        save_app_settings()

    col_new, col_manage = st.columns(2)
    with col_new:
        if st.button("새로 생성하기", use_container_width=True):
            custom_persona_create_dialog()
    with col_manage:
        if st.button("관리", use_container_width=True):
            system_prompt_manage_dialog()

    return resolve_system_prompt()
