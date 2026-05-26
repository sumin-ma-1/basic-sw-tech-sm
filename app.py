"""Streamlit AI 대화 도구 (Ollama 로 로컬 LLM · 채팅 파일 업로드)."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import streamlit as st

DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Material Symbols (rounded) — https://fonts.google.com/icons
ICON_PAGE_CHAT = ":material/chat:"
ICON_PAGE_OLLAMA = ":material/memory:"
ICON_REFRESH = ":material/refresh:"
ICON_DOWNLOAD = ":material/download:"
ICON_DELETE = ":material/delete:"
PRESET_PREFIX = "preset:"
CUSTOM_PREFIX = "custom:"
PERSONA_PRESETS: dict[str, dict[str, str]] = {
    "data_analyst": {
        "label": "데이터 분석가",
        "prompt": (
            "당신은 데이터 분석 전문가입니다. 업로드된 데이터 요약을 바탕으로 "
            "한국어로 명확하고 실용적인 인사이트를 제공하세요. "
            "수치는 요약에 있는 것만 인용하고, 없는 통계는 추측하지 마세요."
        ),
    },
    "code_assistant": {
        "label": "코딩 어시스턴트",
        "prompt": (
            "당신은 숙련된 소프트웨어 개발 어시스턴트입니다. "
            "코드 작성, 디버깅, 리팩터링, 알고리즘 설명을 한국어로 명확히 도와주세요. "
            "가능하면 실행 가능한 예시 코드를 제시하고, 가정은 명시하세요."
        ),
    },
    "learning_mentor": {
        "label": "학습 멘토",
        "prompt": (
            "당신은 친절한 학습 멘토입니다. "
            "개념을 단계별로 쉽게 설명하고, 비유와 짧은 예시를 활용하세요. "
            "학습자 수준에 맞춰 질문을 유도하며, 한국어로 격려하는 톤을 유지하세요."
        ),
    },
}
DEFAULT_PERSONA_KEY = "data_analyst"
DEFAULT_SELECTED_PERSONA = f"{PRESET_PREFIX}{DEFAULT_PERSONA_KEY}"
FALLBACK_MODELS = ["qwen3:8b", "llama3.2", "llama3", "mistral", "gemma2"]
CHAT_FILE_TYPES = ["csv", "txt", "md", "json", "xlsx", "xls"]
MAX_TEXT_CHARS = 12_000
MAX_PREVIEW_ROWS = 30
MAX_FILE_PREVIEW_CHARS = 800
CHAT_HISTORY_DIR = Path(__file__).parent / "chat_history"
WORKSPACE_ROOT = CHAT_HISTORY_DIR / "workspaces"
CHAT_INDEX_FILE = CHAT_HISTORY_DIR / "index.json"
CODE_EXEC_TIMEOUT = 120
CODE_AGENT_INSTRUCTION = (
    "첨부 파일이 있습니다. 파일 내용을 분석한 뒤 요청에 맞게 응답하세요. "
    "데이터 처리·변환·시각화 등 실행이 필요하면 **실행 가능한 Python 코드**를 "
    "```python` 코드 블록 하나로 제공하세요.\n"
    "- 코드는 현재 작업 폴더의 첨부 파일명만 사용하세요 (절대경로 금지).\n"
    "- 결과 파일은 같은 폴더에 저장하세요 (예: `output.csv`, `chart.png`).\n"
    "- 코드는 사용자 승인 후 서버에서 실행됩니다. 실행 전 설명을 덧붙이세요."
)
USER_PROFILE_FILE = CHAT_HISTORY_DIR / "user_profile.json"
APP_SETTINGS_FILE = CHAT_HISTORY_DIR / "app_settings.json"
DEFAULT_CHAT_TITLE = "새 대화"
DEFAULT_USER_PROFILE: dict[str, str] = {
    "name": "",
    "honorific": "",
    "language": "",
    "timezone_region": "",
    "bio": "",
}
PROFILE_NONE_LABEL = "선택 안 함"
LANGUAGE_OPTIONS = [
    PROFILE_NONE_LABEL,
    "한국어",
    "English",
    "日本語",
    "中文(简体)",
    "中文(繁體)",
    "Español",
    "Français",
    "Deutsch",
]
TIMEZONE_REGION_OPTIONS = [
    PROFILE_NONE_LABEL,
    "Asia/Seoul · 대한민국",
    "Asia/Tokyo · 일본",
    "Asia/Shanghai · 중국",
    "Asia/Hong_Kong · 홍콩",
    "Asia/Singapore · 싱가포르",
    "Asia/Dubai · UAE",
    "Asia/Kolkata · 인도",
    "Europe/London · 영국",
    "Europe/Paris · 프랑스",
    "Europe/Berlin · 독일",
    "America/New_York · 미국 동부",
    "America/Chicago · 미국 중부",
    "America/Denver · 미국 산악",
    "America/Los_Angeles · 미국 서부",
    "Australia/Sydney · 호주",
    "Pacific/Auckland · 뉴질랜드",
    "UTC",
]
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2048
DEFAULT_FILE_ENCODING = "utf-8"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_chat(title: str = DEFAULT_CHAT_TITLE) -> dict[str, Any]:
    ts = now_iso()
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "created_at": ts,
        "updated_at": ts,
        "messages": [],
    }


def serialize_file_attachment(file_info: dict[str, Any]) -> dict[str, str]:
    return {
        "name": file_info["name"],
        "type": file_info["type"],
        "summary": file_info["summary"],
    }


def serialize_message(msg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "role": msg["role"],
        "content": msg.get("content", ""),
    }
    if msg.get("files"):
        out["files"] = [serialize_file_attachment(f) for f in msg["files"]]
    if msg.get("executable_code"):
        out["executable_code"] = msg["executable_code"]
        out["execution_status"] = msg.get("execution_status")
        if msg.get("execution_result") is not None:
            out["execution_result"] = msg["execution_result"]
    return out


def serialize_chat(chat: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": chat["id"],
        "title": chat["title"],
        "created_at": chat["created_at"],
        "updated_at": chat["updated_at"],
        "messages": [serialize_message(m) for m in chat["messages"]],
    }


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def chat_to_markdown(chat: dict[str, Any]) -> str:
    serialized = serialize_chat(chat)
    lines = [
        "---",
        f"title: {_yaml_quote(serialized['title'])}",
        f"created_at: {_yaml_quote(serialized['created_at'])}",
        f"updated_at: {_yaml_quote(serialized['updated_at'])}",
        "format_version: 1",
        "---",
        "",
    ]
    for msg in serialized["messages"]:
        header = "## User" if msg["role"] == "user" else "## Assistant"
        lines.extend([header, ""])
        if msg.get("content"):
            lines.extend([msg["content"], ""])
        for file_info in msg.get("files", []):
            lines.extend(
                [
                    f"### 첨부: {file_info['name']} ({file_info['type']})",
                    "",
                    "```",
                    file_info["summary"],
                    "```",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _parse_md_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, parts[2].strip()


def _parse_md_message_section(section: str) -> dict[str, Any]:
    attachment_pattern = re.compile(
        r"^### 첨부: (.+?) \((.+?)\)\s*\n+```\n(.*?)\n```",
        re.DOTALL | re.MULTILINE,
    )
    files: list[dict[str, str]] = []
    content_parts: list[str] = []
    pos = 0
    for match in attachment_pattern.finditer(section):
        content_parts.append(section[pos : match.start()].strip())
        files.append(
            {
                "name": match.group(1).strip(),
                "type": match.group(2).strip(),
                "summary": match.group(3).strip(),
            }
        )
        pos = match.end()
    content_parts.append(section[pos:].strip())
    content = "\n\n".join(part for part in content_parts if part)
    msg: dict[str, Any] = {"content": content}
    if files:
        msg["files"] = files
    return msg


def parse_chat_markdown(text: str) -> dict[str, Any]:
    meta, body = _parse_md_frontmatter(text)
    messages: list[dict[str, Any]] = []
    pattern = re.compile(r"^## (User|Assistant)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    for idx, match in enumerate(matches):
        role = "user" if match.group(1) == "User" else "assistant"
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        section = body[start:end].strip()
        if not section:
            continue
        parsed = _parse_md_message_section(section)
        messages.append({"role": role, **parsed})
    return {
        "title": meta.get("title", "가져온 대화"),
        "created_at": meta.get("created_at", now_iso()),
        "updated_at": meta.get("updated_at", now_iso()),
        "messages": messages,
    }


def chat_from_import_data(data: dict[str, Any]) -> dict[str, Any]:
    chat = new_chat(data.get("title", "가져온 대화"))
    chat["messages"] = data.get("messages", [])
    chat["created_at"] = data.get("created_at", chat["created_at"])
    chat["updated_at"] = data.get("updated_at", now_iso())
    return chat


def parse_imported_chat_file(uploaded: Any) -> dict[str, Any]:
    raw = uploaded.read().decode("utf-8")
    filename = uploaded.name.lower()
    if filename.endswith(".md"):
        return parse_chat_markdown(raw)
    data = json.loads(raw)
    if isinstance(data, dict) and "messages" in data:
        return data
    raise ValueError("지원하지 않는 JSON 형식입니다.")


def load_chats_from_disk() -> dict[str, dict[str, Any]]:
    if not CHAT_INDEX_FILE.exists():
        return {}
    try:
        data = json.loads(CHAT_INDEX_FILE.read_text(encoding="utf-8"))
        chats = data.get("chats", {})
        return {
            cid: {
                "id": cid,
                "title": c.get("title", DEFAULT_CHAT_TITLE),
                "created_at": c.get("created_at", now_iso()),
                "updated_at": c.get("updated_at", now_iso()),
                "messages": c.get("messages", []),
            }
            for cid, c in chats.items()
        }
    except (json.JSONDecodeError, OSError):
        return {}


def load_user_profile() -> dict[str, str]:
    if not USER_PROFILE_FILE.exists():
        return dict(DEFAULT_USER_PROFILE)
    try:
        data = json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8"))
        return {key: str(data.get(key, "")).strip() for key in DEFAULT_USER_PROFILE}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_USER_PROFILE)


def save_user_profile() -> None:
    CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_FILE.write_text(
        json.dumps(st.session_state.user_profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def profile_select_options(
    options: list[str], saved_value: str
) -> tuple[list[str], int]:
    if saved_value and saved_value not in options:
        options = options + [saved_value]
    display = saved_value if saved_value else PROFILE_NONE_LABEL
    return options, options.index(display)


def profile_value_from_select(selected: str) -> str:
    return "" if selected == PROFILE_NONE_LABEL else selected


def profile_button_label() -> str:
    name = st.session_state.user_profile.get("name", "").strip()
    return name if name else "프로필 설정"


def build_user_profile_context() -> str:
    profile = st.session_state.user_profile
    fields = [
        ("이름", profile.get("name", "")),
        ("호칭", profile.get("honorific", "")),
        ("사용 언어", profile.get("language", "")),
        ("시간대 / 지역", profile.get("timezone_region", "")),
        ("자기소개", profile.get("bio", "")),
    ]
    lines = [f"{label}: {value}" for label, value in fields if value]
    if not lines:
        return ""
    return (
        "--- 사용자 정보 ---\n"
        + "\n".join(lines)
        + "\n(위 정보를 참고해 사용자에게 맞춤 응답을 제공하세요.)"
    )


@st.dialog("유저 프로필", width="large")
def user_profile_dialog() -> None:
    st.caption("모든 항목은 선택 입력입니다. 저장된 정보는 모델에게 전달됩니다.")
    profile = st.session_state.user_profile

    name = st.text_input(
        "이름",
        value=profile.get("name", ""),
        placeholder="예: 홍길동 (선택)",
    )
    honorific = st.text_input(
        "호칭",
        value=profile.get("honorific", ""),
        placeholder="예: 언니, Alex (선택)",
    )
    lang_options, lang_index = profile_select_options(
        list(LANGUAGE_OPTIONS), profile.get("language", "")
    )
    language = st.selectbox("사용 언어", lang_options, index=lang_index)

    tz_options, tz_index = profile_select_options(
        list(TIMEZONE_REGION_OPTIONS), profile.get("timezone_region", "")
    )
    timezone_region = st.selectbox("시간대 / 지역", tz_options, index=tz_index)
    bio = st.text_area(
        "간단한 자기소개",
        value=profile.get("bio", ""),
        placeholder="예: 데이터 분석을 배우는 대학생입니다. (선택)",
        height=100,
    )

    col_save, col_clear = st.columns(2)
    with col_save:
        if st.button("저장", type="primary", use_container_width=True):
            st.session_state.user_profile = {
                "name": name.strip(),
                "honorific": honorific.strip(),
                "language": profile_value_from_select(language),
                "timezone_region": profile_value_from_select(timezone_region),
                "bio": bio.strip(),
            }
            save_user_profile()
            st.rerun()
    with col_clear:
        if st.button("프로필 비우기", use_container_width=True):
            st.session_state.user_profile = dict(DEFAULT_USER_PROFILE)
            save_user_profile()
            st.rerun()


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
            custom_personas[cid] = {
                "id": cid,
                "title": "커스텀",
                "prompt": legacy_prompt.strip(),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            selected = f"{CUSTOM_PREFIX}{cid}"
    if persona_key not in PERSONA_PRESETS and not selected.startswith(CUSTOM_PREFIX):
        selected = DEFAULT_SELECTED_PERSONA
    return {"selected_persona_id": selected, "custom_personas": custom_personas}


def load_app_settings() -> dict[str, Any]:
    if not APP_SETTINGS_FILE.exists():
        return migrate_app_settings({})
    try:
        data = json.loads(APP_SETTINGS_FILE.read_text(encoding="utf-8"))
        return migrate_app_settings(data)
    except (json.JSONDecodeError, OSError):
        return migrate_app_settings({})


def save_app_settings() -> None:
    CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    APP_SETTINGS_FILE.write_text(
        json.dumps(
            {
                "selected_persona_id": st.session_state.selected_persona_id,
                "custom_personas": st.session_state.custom_personas,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


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
        return PERSONA_PRESETS[key]["label"]
    cid = persona_id.removeprefix(CUSTOM_PREFIX)
    return st.session_state.custom_personas[cid]["title"]


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
    title: str, prompt: str, persona_id: str | None = None
) -> str:
    ts = now_iso()
    if persona_id is None:
        persona_id = str(uuid.uuid4())
        st.session_state.custom_personas[persona_id] = {
            "id": persona_id,
            "title": title,
            "prompt": prompt,
            "created_at": ts,
            "updated_at": ts,
        }
    else:
        existing = st.session_state.custom_personas[persona_id]
        st.session_state.custom_personas[persona_id] = {
            "id": persona_id,
            "title": title,
            "prompt": prompt,
            "created_at": existing.get("created_at", ts),
            "updated_at": ts,
        }
    return persona_id


def delete_custom_persona(persona_id: str) -> None:
    st.session_state.custom_personas.pop(persona_id, None)
    if st.session_state.selected_persona_id == f"{CUSTOM_PREFIX}{persona_id}":
        st.session_state.selected_persona_id = DEFAULT_SELECTED_PERSONA


@st.dialog("커스텀 Persona 생성", width="large")
def custom_persona_create_dialog() -> None:
    st.caption("새 커스텀 Persona를 작성하고 저장하세요.")
    title = st.text_input("이름", placeholder="예: 통계 튜터")
    prompt = st.text_area(
        "시스템 프롬프트",
        height=220,
        placeholder="모델에게 전달할 역할·지침을 작성하세요.",
    )
    if st.button("저장", type="primary", use_container_width=True):
        if not title.strip() or not prompt.strip():
            st.error("이름과 시스템 프롬프트를 모두 입력해 주세요.")
            return
        new_id = upsert_custom_persona(title.strip(), prompt.strip())
        st.session_state.selected_persona_id = f"{CUSTOM_PREFIX}{new_id}"
        save_app_settings()
        st.rerun()


@st.dialog("커스텀 Persona 관리", width="large")
def custom_persona_manage_dialog() -> None:
    customs = st.session_state.custom_personas
    if not customs:
        st.info("저장된 커스텀 Persona가 없습니다. '새로 생성하기'로 추가하세요.")
        return

    for persona in sorted(
        customs.values(), key=lambda p: p["updated_at"], reverse=True
    ):
        pid = persona["id"]
        with st.expander(f"{persona['title']} · {persona['updated_at']}"):
            edit_title = st.text_input("이름", value=persona["title"], key=f"mt_{pid}")
            edit_prompt = st.text_area(
                "시스템 프롬프트",
                value=persona["prompt"],
                height=160,
                key=f"mp_{pid}",
            )
            col_save, col_del = st.columns(2)
            with col_save:
                if st.button("저장", key=f"ms_{pid}", use_container_width=True):
                    if not edit_title.strip() or not edit_prompt.strip():
                        st.error("이름과 프롬프트를 입력해 주세요.")
                    else:
                        upsert_custom_persona(
                            edit_title.strip(), edit_prompt.strip(), pid
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
            custom_persona_manage_dialog()

    return resolve_system_prompt()


def save_chats_to_disk() -> None:
    CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "saved_at": now_iso(),
        "chats": {
            cid: serialize_chat(chat)
            for cid, chat in st.session_state.chat_histories.items()
        },
    }
    CHAT_INDEX_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def init_session_state() -> None:
    defaults = {
        "df": None,
        "df_name": None,
        "ollama_models": [],
        "ollama_base_url": DEFAULT_OLLAMA_URL,
    }
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


def set_messages(messages: list[dict[str, Any]]) -> None:
    chat = get_active_chat()
    chat["messages"] = messages
    chat["updated_at"] = now_iso()
    save_chats_to_disk()


def append_message(msg: dict[str, Any]) -> None:
    chat = get_active_chat()
    chat["messages"].append(msg)
    chat["updated_at"] = now_iso()
    if (
        chat["title"] == DEFAULT_CHAT_TITLE
        and msg["role"] == "user"
        and msg.get("content", "").strip()
    ):
        preview = msg["content"].strip().replace("\n", " ")
        chat["title"] = preview[:40] + ("…" if len(preview) > 40 else "")
    save_chats_to_disk()


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
    chat = st.session_state.chat_histories[chat_id]
    return f"{chat['title']}"


def render_chat_history_manager() -> None:
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
            active["title"] = new_title.strip() or DEFAULT_CHAT_TITLE
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


def ollama_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body:
        return {}
    return json.loads(body)


def fetch_ollama_models(base_url: str) -> list[str]:
    try:
        data = ollama_request(base_url, "/api/tags", timeout=5)
        return sorted(m["name"] for m in data.get("models", []))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return []


def fetch_ollama_version(base_url: str) -> str | None:
    try:
        data = ollama_request(base_url, "/api/version", timeout=5)
        return data.get("version")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None


def pull_ollama_model(
    base_url: str,
    name: str,
    *,
    on_update: Callable[[float | None, str], None] | None = None,
) -> tuple[bool, str]:
    model_name = name.strip()
    if not model_name:
        return False, "모델 이름을 입력하세요."

    url = f"{base_url.rstrip('/')}/api/pull"
    payload = json.dumps({"name": model_name, "stream": True}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            for raw in resp:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = str(event.get("status", ""))
                total = event.get("total")
                completed = event.get("completed")
                if on_update:
                    if isinstance(total, int) and total > 0 and isinstance(completed, int):
                        on_update(min(completed / total, 1.0), status)
                    else:
                        on_update(None, status)
                if status == "success":
                    return True, f"「{model_name}」 다운로드 완료"
        return False, "다운로드가 중단되었습니다."
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return False, f"HTTP {exc.code}: {body}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, str(exc)


def delete_ollama_model(base_url: str, name: str) -> tuple[bool, str]:
    model_name = name.strip()
    if not model_name:
        return False, "삭제할 모델을 선택하세요."
    url = f"{base_url.rstrip('/')}/api/delete"
    payload = json.dumps({"name": model_name}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
        return True, f"「{model_name}」 삭제됨"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return False, f"HTTP {exc.code}: {body}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, str(exc)


def sync_ollama_base_url(base_url: str) -> str:
    st.session_state.ollama_base_url = base_url.rstrip("/") or DEFAULT_OLLAMA_URL
    return st.session_state.ollama_base_url


def read_file_bytes(uploaded_file: Any) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        return uploaded_file.getvalue()
    data = uploaded_file.read()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    return data


def decode_text(raw: bytes, encoding: str) -> str:
    for enc in [encoding, "utf-8", "cp949", "euc-kr", "latin-1"]:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode(encoding, errors="replace")


def load_csv_bytes(raw: bytes, encoding: str) -> pd.DataFrame:
    for enc in [encoding, "utf-8", "cp949", "euc-kr", "latin-1"]:
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(raw), encoding=encoding, encoding_errors="replace")


def process_uploaded_file(uploaded_file: Any, encoding: str) -> dict[str, Any]:
    name = uploaded_file.name
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    raw = read_file_bytes(uploaded_file)

    if ext == "csv":
        df = load_csv_bytes(raw, encoding)
        return {
            "name": name,
            "type": "csv",
            "summary": build_data_summary(df),
            "df": df,
            "raw_bytes": raw,
        }
    if ext in ("xlsx", "xls"):
        df = pd.read_excel(io.BytesIO(raw))
        return {
            "name": name,
            "type": "excel",
            "summary": build_data_summary(df),
            "df": df,
            "raw_bytes": raw,
        }
    if ext in ("txt", "md", "json"):
        text = decode_text(raw, encoding)
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "\n... (이하 생략)"
        return {
            "name": name,
            "type": ext,
            "summary": text,
            "df": None,
            "raw_bytes": raw,
        }
    return {
        "name": name,
        "type": ext or "unknown",
        "summary": f"[{name}] 지원하지 않는 형식입니다.",
        "df": None,
        "raw_bytes": raw,
    }


def get_chat_workspace(chat_id: str | None = None) -> Path:
    cid = chat_id or st.session_state.active_chat_id
    workspace = WORKSPACE_ROOT / cid
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def save_bytes_to_workspace(workspace: Path, name: str, raw: bytes) -> Path:
    safe_name = Path(name).name
    path = workspace / safe_name
    path.write_bytes(raw)
    return path


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
    safe_name = Path(name).name
    if not safe_name.lower().endswith(".csv"):
        safe_name = f"{Path(safe_name).stem}.csv"
    path = workspace / safe_name
    if not path.exists():
        df.to_csv(path, index=False, encoding="utf-8-sig")
    return [
        {
            "name": name,
            "type": "csv",
            "summary": build_data_summary(df),
            "workspace_path": str(path),
        }
    ]


def prepare_files_in_workspace(
    processed: list[dict[str, Any]], chat_id: str | None = None
) -> list[dict[str, Any]]:
    workspace = get_chat_workspace(chat_id)
    for item in processed:
        raw = item.get("raw_bytes")
        if raw is not None:
            item["workspace_path"] = str(
                save_bytes_to_workspace(workspace, item["name"], raw)
            )
        elif item.get("df") is not None and item.get("type") in ("csv", "excel"):
            out_name = item["name"]
            if not out_name.lower().endswith(".csv"):
                out_name = f"{Path(out_name).stem}.csv"
            path = workspace / Path(out_name).name
            item["df"].to_csv(path, index=False, encoding="utf-8-sig")
            item["workspace_path"] = str(path)
    return processed


def build_workspace_file_context(processed: list[dict[str, Any]] | None) -> str:
    if not processed:
        return ""
    lines = ["--- 첨부 파일 (작업 폴더) ---"]
    for item in processed:
        path = item.get("workspace_path")
        if path:
            lines.append(f"- {item['name']} → `{path}`")
        else:
            lines.append(f"- {item['name']} ({item['type']})")
    return "\n".join(lines)


def extract_python_blocks(text: str) -> list[str]:
    pattern = re.compile(r"```python\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
    return [block.strip() for block in pattern.findall(text) if block.strip()]


def extract_code_explanation(content: str) -> str:
    if not content or not content.strip():
        return "첨부된 파일을 읽고, 요청하신 작업을 수행하는 코드입니다."
    text = re.sub(
        r"```python\s*\n.*?```", "", content, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"```\s*\n.*?```", "", text, flags=re.DOTALL)
    text = text.strip()
    if not text:
        return "첨부된 파일을 읽고, 요청하신 작업을 수행하는 코드입니다."
    return text


def list_workspace_files(workspace: Path) -> set[str]:
    if not workspace.exists():
        return set()
    return {
        p.name
        for p in workspace.iterdir()
        if p.is_file() and not p.name.startswith("_")
    }


def execute_python_code(code: str, workspace: Path) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    before = list_workspace_files(workspace)
    script_path = workspace / "_run_script.py"
    script_path.write_text(code, encoding="utf-8")

    try:
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=CODE_EXEC_TIMEOUT,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        returncode = completed.returncode
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"실행 시간 초과 ({CODE_EXEC_TIMEOUT}초)",
            "returncode": -1,
            "new_files": [],
        }
    finally:
        if script_path.exists():
            script_path.unlink()

    after = list_workspace_files(workspace)
    new_files = sorted(after - before)
    return {
        "success": returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "new_files": new_files,
    }


def patch_message(index: int, **fields: Any) -> None:
    chat = get_active_chat()
    chat["messages"][index].update(fields)
    chat["updated_at"] = now_iso()
    save_chats_to_disk()


def build_data_summary(df: pd.DataFrame) -> str:
    lines = [
        f"행 수: {len(df):,}",
        f"열 수: {len(df.columns)}",
        f"컬럼: {', '.join(df.columns.astype(str).tolist())}",
        "",
        "=== dtypes ===",
        df.dtypes.to_string(),
        "",
        "=== 결측치 ===",
        df.isna().sum().to_string(),
        "",
        "=== describe (수치) ===",
        df.describe(include="all").to_string(),
    ]
    return "\n".join(lines)


def format_user_message(content: str, files: list[dict[str, Any]] | None = None) -> str:
    if not files:
        return content
    parts = [content] if content.strip() else []
    for f in files:
        parts.append(f"### 첨부: {f['name']} ({f['type']})\n{f['summary']}")
    return "\n\n".join(parts) if parts else "(파일만 첨부됨)"


def build_api_messages(
    system_prompt: str,
    data_context: str,
    *,
    attached_files: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    system_parts = [system_prompt]
    profile_ctx = build_user_profile_context()
    if profile_ctx:
        system_parts.append(profile_ctx)
    system_parts.append(f"--- 활성 데이터셋 ---\n{data_context}")
    if attached_files:
        system_parts.append(CODE_AGENT_INSTRUCTION)
        file_ctx = build_workspace_file_context(attached_files)
        if file_ctx:
            system_parts.append(file_ctx)
    system = "\n\n".join(system_parts)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for msg in get_messages():
        if msg["role"] == "user":
            content = format_user_message(msg.get("content", ""), msg.get("files"))
        else:
            content = msg["content"]
        messages.append({"role": msg["role"], "content": content})
    return messages


def build_active_context(df: pd.DataFrame | None) -> str:
    if df is not None:
        return build_data_summary(df)
    return "(활성 데이터셋 없음 — 채팅에서 CSV/Excel을 첨부하세요)"


def call_ollama(
    base_url: str,
    *,
    model: str,
    system_prompt: str,
    data_context: str,
    temperature: float,
    max_tokens: int,
    attached_files: list[dict[str, Any]] | None = None,
) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": build_api_messages(
            system_prompt,
            data_context,
            attached_files=attached_files,
        ),
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data.get("message", {}).get("content", "")


def render_ollama_page() -> None:
    st.title("Ollama 관리")
    st.caption("모델 다운로드·삭제·상태 확인 · URL은 **AI 채팅** 사이드바와 공유됩니다")

    base_url = sync_ollama_base_url(
        st.text_input(
            "Ollama URL",
            value=st.session_state.ollama_base_url,
            key="ollama_page_url",
            placeholder="http://localhost:11434",
        )
    )

    if st.button(
        "연결·목록 새로고침",
        icon=ICON_REFRESH,
        help="Ollama 연결 및 설치 모델 목록 갱신",
    ):
        st.session_state.ollama_models = fetch_ollama_models(base_url)
        st.rerun()

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
        st.selectbox(
            "모델",
            models,
            key="ollama_installed_select",
            disabled=not connected,
        )
    elif connected:
        st.info("설치된 모델이 없습니다. 아래에서 받을 수 있습니다.")
    else:
        st.warning("목록을 불러올 수 없습니다.")

    st.divider()
    st.subheader("모델 받기")
    st.caption(
        "예: `qwen3:8b`, `llama3.2` · [Ollama 라이브러리](https://ollama.com/library)"
    )
    pull_name = st.text_input(
        "모델 이름",
        placeholder="qwen3:8b",
        key="ollama_pull_name",
        disabled=not connected,
    )
    if st.button(
        "다운로드 시작",
        type="primary",
        icon=ICON_DOWNLOAD,
        disabled=not connected,
    ):
        if not pull_name.strip():
            st.error("모델 이름을 입력하세요.")
        else:
            progress = st.progress(0.0, text="준비 중…")
            status_box = st.empty()

            def on_pull_update(ratio: float | None, status: str) -> None:
                label = status or "다운로드 중…"
                if ratio is not None:
                    progress.progress(ratio, text=label)
                else:
                    progress.progress(0.0, text=label)
                status_box.caption(label)

            ok, message = pull_ollama_model(
                base_url, pull_name, on_update=on_pull_update
            )
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
        if st.button(
            "선택 모델 삭제",
            icon=ICON_DELETE,
            disabled=not confirm,
        ):
            ok, message = delete_ollama_model(base_url, delete_name)
            if ok:
                st.success(message)
                st.session_state.ollama_models = fetch_ollama_models(base_url)
                st.rerun()
            else:
                st.error(message)


def render_sidebar() -> dict[str, Any]:
    with st.sidebar:
        if st.button(profile_button_label(), use_container_width=True):
            user_profile_dialog()

        st.subheader("Ollama")

        base_url = sync_ollama_base_url(
            st.text_input(
                "Ollama URL",
                value=st.session_state.ollama_base_url,
                key="chat_ollama_url",
            )
        )

        if st.button(
            "모델 목록 새로고침",
            icon=ICON_REFRESH,
            use_container_width=True,
        ):
            st.session_state.ollama_models = fetch_ollama_models(base_url)
            st.rerun()

        if not st.session_state.ollama_models:
            st.session_state.ollama_models = fetch_ollama_models(base_url)

        models = st.session_state.ollama_models or FALLBACK_MODELS
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
        render_chat_history_manager()

        st.caption("포트 **8507** · `streamlit run app.py`")

    return {
        "base_url": base_url,
        "model": model,
        "system_prompt": system_prompt,
        "ollama_connected": bool(st.session_state.ollama_models),
    }


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
            f"⬇ {fname}",
            data=data,
            file_name=fname,
            mime=mime,
            key=f"dl_{workspace.name}_{fname}",
            use_container_width=True,
        )


def render_code_execution_panel(msg: dict[str, Any], msg_index: int) -> None:
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


def render_file_preview(file_info: dict[str, Any]) -> None:
    if file_info.get("type") == "error":
        st.error(file_info.get("summary", "파일 처리 실패"))
        return
    if file_info.get("df") is not None:
        df = file_info["df"]
        st.dataframe(df.head(MAX_PREVIEW_ROWS), use_container_width=True)
        st.caption(f"{len(df):,}행 × {len(df.columns)}열 · 상위 {MAX_PREVIEW_ROWS}행")
        return
    summary = file_info.get("summary", "")
    preview = summary[:MAX_FILE_PREVIEW_CHARS]
    if len(summary) > MAX_FILE_PREVIEW_CHARS:
        preview += "\n… (미리보기)"
    st.text(preview)


def render_message(msg: dict[str, Any], msg_index: int) -> None:
    with st.chat_message(msg["role"]):
        if msg.get("content") and not msg.get("executable_code"):
            st.markdown(msg["content"])
        for f in msg.get("files", []):
            with st.expander(f"{f['name']} ({f['type']})", expanded=False):
                render_file_preview(f)
        if msg["role"] == "assistant" and msg.get("executable_code"):
            render_code_execution_panel(msg, msg_index)


def apply_chat_files(processed: list[dict[str, Any]]) -> None:
    for item in processed:
        if item.get("df") is not None:
            st.session_state.df = item["df"]
            st.session_state.df_name = item["name"]


def render_ai_chat(settings: dict[str, Any]) -> None:
    messages = get_messages()
    for idx, msg in enumerate(messages):
        render_message(msg, idx)

    chat_result = st.chat_input(
        "질문을 입력하거나 파일을 첨부하세요",
        accept_file="multiple",
        file_type=CHAT_FILE_TYPES,
    )

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
            with st.spinner(f"{settings['model']} 분석 중..."):
                try:
                    reply = call_ollama(
                        settings["base_url"],
                        model=settings["model"],
                        system_prompt=settings["system_prompt"],
                        data_context=ctx,
                        temperature=DEFAULT_TEMPERATURE,
                        max_tokens=DEFAULT_MAX_TOKENS,
                        attached_files=files_for_model,
                    )
                    st.markdown(reply)
                    assistant_msg["content"] = reply
                    if has_attachments:
                        blocks = extract_python_blocks(reply)
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


def page_chat() -> None:
    settings = render_sidebar()
    render_ai_chat(settings)


def page_ollama() -> None:
    render_ollama_page()


def main() -> None:
    favicon = Path(__file__).parent / "sm_final.png"
    st.set_page_config(
        page_title="Basic Software Technology",
        page_icon=str(favicon) if favicon.exists() else ICON_PAGE_CHAT,
        layout="wide",
    )

    init_session_state()

    chat_page = st.Page(
        page_chat, title="AI 채팅", icon=ICON_PAGE_CHAT, default=True
    )
    ollama_page = st.Page(page_ollama, title="Ollama 관리", icon=ICON_PAGE_OLLAMA)
    st.navigation([chat_page, ollama_page]).run()


if __name__ == "__main__":
    main()
