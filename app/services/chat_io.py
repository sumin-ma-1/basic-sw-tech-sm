from __future__ import annotations

import json
import re
from typing import Any

from app.utils import new_chat, now_iso


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
    if msg.get("thinking_seconds") is not None:
        out["thinking_seconds"] = msg["thinking_seconds"]
    if msg.get("think_enabled") is not None:
        out["think_enabled"] = msg["think_enabled"]
    if msg.get("response_mode"):
        out["response_mode"] = msg["response_mode"]
    if msg.get("thinking_trace"):
        out["thinking_trace"] = msg["thinking_trace"]
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


def chat_from_import_data(
    data: dict[str, Any], *, default_chat_title: str
) -> dict[str, Any]:
    chat = new_chat(data.get("title", "가져온 대화"), default_title=default_chat_title)
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
