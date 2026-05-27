"""Ollama chat API: message assembly and HTTP call."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.session import build_data_summary, get_messages
from app.ui.shared.profile import build_user_profile_context

@dataclass(frozen=True)
class OllamaChatResult:
    content: str
    thinking: str | None = None


CODE_AGENT_INSTRUCTION = (
    "첨부 파일이 있습니다. 파일 내용을 분석한 뒤 요청에 맞게 응답하세요. "
    "데이터 처리·변환·시각화 등 실행이 필요하면 **실행 가능한 Python 코드**를 "
    "```python` 코드 블록 하나로 제공하세요.\n"
    "- 코드는 현재 작업 폴더의 첨부 파일명만 사용하세요 (절대경로 금지).\n"
    "- 결과 파일은 같은 폴더에 저장하세요 (예: `output.csv`, `chart.png`).\n"
    "- 코드는 사용자 승인 후 서버에서 실행됩니다. 실행 전 설명을 덧붙이세요."
)


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
    return "(활성 데이터셋 없음, 채팅에서 CSV/Excel을 첨부하세요)"


def call_ollama(
    base_url: str,
    *,
    model: str,
    system_prompt: str,
    data_context: str,
    temperature: float,
    max_tokens: int,
    attached_files: list[dict[str, Any]] | None = None,
    think: bool = False,
    send_think: bool = False,
) -> OllamaChatResult:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": build_api_messages(
            system_prompt,
            data_context,
            attached_files=attached_files,
        ),
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if send_think:
        payload["think"] = think
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    message = data.get("message", {})
    thinking = message.get("thinking")
    return OllamaChatResult(
        content=message.get("content", ""),
        thinking=thinking if thinking and str(thinking).strip() else None,
    )
