from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from app.config import (
    CHAT_HISTORY_DIR,
    OLLAMA_REMOTE_GPU_FILE,
    OLLAMA_REMOTE_HOST_FILE,
    OLLAMA_SSH_TARGET,
    OLLAMA_SSH_TARGET_FILE,
)

_SSH_TARGET_RE = re.compile(
    r"^(?:(?P<user>[^@]+)@)?(?P<host>[^:]+)(?::(?P<port>\d+))?$"
)

_last_ssh_error = ""


def get_ssh_probe_hint() -> str:
    err = _last_ssh_error.lower()
    if "permission denied" in err:
        return (
            "SSH 키 로그인이 필요합니다. "
            "터널은 비밀번호로 연결해도, 앱 자동 조회는 키 없이는 불가합니다."
        )
    if "could not resolve hostname" in err or "name or service not known" in err:
        return "SSH 호스트 이름을 확인하세요."
    if "connection timed out" in err or "connection refused" in err:
        return "SSH 서버에 연결할 수 없습니다. 포트·방화벽을 확인하세요."
    if _last_ssh_error:
        return _last_ssh_error
    if not find_ssh_executable():
        return "ssh.exe를 찾을 수 없습니다."
    if not get_ssh_target():
        return "SSH 대상(`ollama_ssh_target.txt`)이 비어 있습니다."
    return ""


def _sanitize_text(text: str) -> str:
    return text.replace("\x00", "").replace("\ufeff", "").strip()


def _read_text_file(path: Path, *, normalize_utf8: bool = False) -> str:
    if not path.exists():
        return ""
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""

    was_utf16 = False

    if raw.startswith(b"\xff\xfe"):
        was_utf16 = True
        for encoding in ("utf-16-le", "utf-16"):
            try:
                text = _sanitize_text(raw.decode(encoding))
                if normalize_utf8 and text:
                    _write_text_file(path, text)
                return text
            except UnicodeDecodeError:
                continue
    if raw.startswith(b"\xfe\xff"):
        was_utf16 = True
        try:
            text = _sanitize_text(raw.decode("utf-16-be"))
            if normalize_utf8 and text:
                _write_text_file(path, text)
            return text
        except UnicodeDecodeError:
            pass

    # BOM 없는 UTF-16 LE (PowerShell/CMD echo 등): s\x00u\x00m\x00...
    if len(raw) >= 4 and len(raw) % 2 == 0 and raw[1::2] == b"\x00" * (len(raw) // 2):
        was_utf16 = True
        try:
            text = _sanitize_text(raw.decode("utf-16-le"))
            if normalize_utf8 and text:
                _write_text_file(path, text)
            return text
        except UnicodeDecodeError:
            pass

    for encoding in ("utf-8-sig", "utf-8", "cp949", "latin-1"):
        try:
            text = _sanitize_text(raw.decode(encoding))
            if normalize_utf8 and was_utf16 and text:
                _write_text_file(path, text)
            return text
        except UnicodeDecodeError:
            continue
    return ""


def _write_text_file(path: Path, value: str) -> None:
    try:
        CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(value.strip(), encoding="utf-8")
    except OSError:
        pass


def get_ssh_target() -> str:
    if OLLAMA_SSH_TARGET:
        return _sanitize_text(OLLAMA_SSH_TARGET)
    return _read_text_file(OLLAMA_SSH_TARGET_FILE, normalize_utf8=True)


def parse_ssh_target(raw: str) -> tuple[str, int | None]:
    text = _sanitize_text(raw)
    if not text:
        return "", None
    match = _SSH_TARGET_RE.match(text)
    if not match:
        return text, None
    user = match.group("user")
    host = match.group("host")
    port = int(match.group("port")) if match.group("port") else None
    target = f"{user}@{host}" if user else host
    return target, port


def find_ssh_executable() -> str | None:
    for candidate in (
        shutil.which("ssh"),
        os.environ.get("OLLAMA_SSH_BIN", "").strip() or None,
        r"C:\Windows\System32\OpenSSH\ssh.exe",
        r"C:\Program Files\Git\usr\bin\ssh.exe",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def run_ssh_command(remote_command: str, *, timeout: float = 8) -> str | None:
    global _last_ssh_error
    ssh_bin = find_ssh_executable()
    target, port = parse_ssh_target(get_ssh_target())
    if not ssh_bin or not target:
        _last_ssh_error = ""
        return None

    cmd = [
        ssh_bin,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if port:
        cmd.extend(["-p", str(port)])
    cmd.extend([target, remote_command])

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _last_ssh_error = str(exc)
        return None

    if result.returncode != 0:
        _last_ssh_error = (result.stderr or result.stdout or "").strip()
        return None

    _last_ssh_error = ""
    output = result.stdout.strip()
    return output or None


def probe_remote_hostname() -> str | None:
    return run_ssh_command("hostname")


def probe_remote_gpu_names() -> list[str]:
    output = run_ssh_command(
        "nvidia-smi --query-gpu=name --format=csv,noheader",
        timeout=10,
    )
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def resolve_remote_host_hint(*, allow_ssh_probe: bool = True) -> str:
    env_host = os.environ.get("OLLAMA_REMOTE_HOST", "").strip()
    if env_host:
        return env_host

    cached = _read_text_file(OLLAMA_REMOTE_HOST_FILE)
    if cached:
        return cached

    if not allow_ssh_probe or not get_ssh_target():
        return ""

    hostname = probe_remote_hostname()
    if hostname:
        _write_text_file(OLLAMA_REMOTE_HOST_FILE, hostname)
    return hostname or ""


def resolve_remote_gpu_names(*, allow_ssh_probe: bool = True) -> list[str]:
    env_gpus = os.environ.get("OLLAMA_REMOTE_GPUS", "").strip()
    if env_gpus:
        return [g.strip() for g in env_gpus.split(",") if g.strip()]

    cached = _read_text_file(OLLAMA_REMOTE_GPU_FILE)
    if cached:
        return [g.strip() for g in cached.splitlines() if g.strip()]

    if not allow_ssh_probe or not get_ssh_target():
        return []

    gpu_names = probe_remote_gpu_names()
    if gpu_names:
        _write_text_file(OLLAMA_REMOTE_GPU_FILE, "\n".join(gpu_names))
    return gpu_names


def save_remote_host_hint(hostname: str) -> None:
    _write_text_file(OLLAMA_REMOTE_HOST_FILE, _sanitize_text(hostname))


def save_remote_gpu_names(names: list[str]) -> None:
    cleaned = [_sanitize_text(name) for name in names]
    cleaned = [name for name in cleaned if name]
    _write_text_file(OLLAMA_REMOTE_GPU_FILE, "\n".join(cleaned))
