from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any


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


def execute_python_code(
    code: str,
    *,
    workspace: Path,
    timeout_s: int,
) -> dict[str, Any]:
    from app.services.workspace import list_workspace_files

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
            timeout=timeout_s,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        returncode = completed.returncode
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"실행 시간 초과 ({timeout_s}초)",
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

