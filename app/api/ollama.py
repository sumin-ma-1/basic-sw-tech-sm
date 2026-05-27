from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable


def format_bytes(num: int | float | None) -> str:
    if num is None:
        return "—"
    n = float(num)
    if n < 0:
        return "—"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def processor_split(size: int, size_vram: int) -> str:
    if size <= 0:
        return "—"
    gpu = int(min(max((size_vram / size) * 100, 0), 100))
    return f"{100 - gpu}% CPU / {gpu}% GPU"


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


def fetch_ollama_tags(base_url: str) -> list[dict[str, Any]]:
    try:
        data = ollama_request(base_url, "/api/tags", timeout=5)
        models = data.get("models", [])
        if isinstance(models, list):
            return [m for m in models if isinstance(m, dict)]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        pass
    return []


def fetch_ollama_models(base_url: str) -> list[str]:
    return sorted(m.get("name", "") for m in fetch_ollama_tags(base_url) if m.get("name"))


def fetch_ollama_ps(base_url: str) -> list[dict[str, Any]]:
    try:
        data = ollama_request(base_url, "/api/ps", timeout=5)
        models = data.get("models", [])
        if isinstance(models, list):
            return [m for m in models if isinstance(m, dict)]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        pass
    return []


def fetch_ollama_info(base_url: str) -> dict[str, Any] | None:
    try:
        return ollama_request(base_url, "/api/info", timeout=5)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    return None


def fetch_ollama_server_resources(base_url: str) -> dict[str, Any]:
    installed = fetch_ollama_tags(base_url)
    running = fetch_ollama_ps(base_url)
    info = fetch_ollama_info(base_url)

    total_memory: int | None = None
    free_memory: int | None = None
    filesystem_used: int | None = None
    gpus: list[dict[str, Any]] = []

    if info:
        models_block = info.get("models") if isinstance(info.get("models"), dict) else {}
        if isinstance(models_block.get("filesystem_used"), int):
            filesystem_used = models_block["filesystem_used"]

        compute = info.get("compute") if isinstance(info.get("compute"), dict) else {}
        system = compute.get("system_compute") or compute.get("system")
        if isinstance(system, dict):
            if isinstance(system.get("total_memory"), int):
                total_memory = system["total_memory"]
            if isinstance(system.get("free_memory"), int):
                free_memory = system["free_memory"]

        raw_gpus = compute.get("supported_gpus")
        if isinstance(raw_gpus, list):
            gpus = [g for g in raw_gpus if isinstance(g, dict)]

    installed_total = sum(int(m.get("size") or 0) for m in installed)
    if filesystem_used is None:
        filesystem_used = installed_total

    return {
        "info": info,
        "installed": installed,
        "installed_count": len(installed),
        "installed_total_bytes": installed_total,
        "filesystem_used_bytes": filesystem_used,
        "running": running,
        "running_count": len(running),
        "running_size_bytes": sum(int(m.get("size") or 0) for m in running),
        "running_vram_bytes": sum(int(m.get("size_vram") or 0) for m in running),
        "total_memory_bytes": total_memory,
        "free_memory_bytes": free_memory,
        "gpus": gpus,
    }


def fetch_model_capabilities(base_url: str, model: str) -> list[str]:
    try:
        data = ollama_request(
            base_url,
            "/api/show",
            method="POST",
            payload={"model": model},
            timeout=10,
        )
        caps = data.get("capabilities")
        if isinstance(caps, list):
            return [str(c) for c in caps]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        pass
    return []


def model_supports_thinking(base_url: str, model: str) -> bool:
    return "thinking" in fetch_model_capabilities(base_url, model)


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

