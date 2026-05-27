from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def load_chats_from_disk(
    *,
    chat_index_file: Path,
    default_chat_title: str,
    now_iso: Callable[[], str],
) -> dict[str, dict[str, Any]]:
    if not chat_index_file.exists():
        return {}
    try:
        data = json.loads(chat_index_file.read_text(encoding="utf-8"))
        chats = data.get("chats", {})
        return {
            cid: {
                "id": cid,
                "title": c.get("title", default_chat_title),
                "created_at": c.get("created_at", now_iso()),
                "updated_at": c.get("updated_at", now_iso()),
                "messages": c.get("messages", []),
            }
            for cid, c in chats.items()
        }
    except (json.JSONDecodeError, OSError):
        return {}


def save_chats_to_disk(
    *,
    chat_history_dir: Path,
    chat_index_file: Path,
    chat_histories: dict[str, dict[str, Any]],
    now_iso: Callable[[], str],
    serialize_chat: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    chat_history_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "saved_at": now_iso(),
        "chats": {cid: serialize_chat(chat) for cid, chat in chat_histories.items()},
    }
    chat_index_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_user_profile(
    *,
    user_profile_file: Path,
    default_user_profile: dict[str, str],
) -> dict[str, str]:
    if not user_profile_file.exists():
        return dict(default_user_profile)
    try:
        data = json.loads(user_profile_file.read_text(encoding="utf-8"))
        return {
            key: str(data.get(key, "")).strip() for key in default_user_profile
        }
    except (json.JSONDecodeError, OSError):
        return dict(default_user_profile)


def save_user_profile(
    *,
    chat_history_dir: Path,
    user_profile_file: Path,
    user_profile: dict[str, str],
) -> None:
    chat_history_dir.mkdir(parents=True, exist_ok=True)
    user_profile_file.write_text(
        json.dumps(user_profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_app_settings(
    *,
    app_settings_file: Path,
    migrate_app_settings: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    if not app_settings_file.exists():
        return migrate_app_settings({})
    try:
        data = json.loads(app_settings_file.read_text(encoding="utf-8"))
        return migrate_app_settings(data)
    except (json.JSONDecodeError, OSError):
        return migrate_app_settings({})


def save_app_settings(
    *,
    chat_history_dir: Path,
    app_settings_file: Path,
    selected_persona_id: str,
    custom_personas: dict[str, dict[str, str]],
) -> None:
    chat_history_dir.mkdir(parents=True, exist_ok=True)
    app_settings_file.write_text(
        json.dumps(
            {
                "selected_persona_id": selected_persona_id,
                "custom_personas": custom_personas,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

