from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable


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

