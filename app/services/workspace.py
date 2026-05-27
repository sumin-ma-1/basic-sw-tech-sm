from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def get_chat_workspace(workspace_root: Path, *, chat_id: str) -> Path:
    workspace = workspace_root / chat_id
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def save_bytes_to_workspace(workspace: Path, name: str, raw: bytes) -> Path:
    safe_name = Path(name).name
    path = workspace / safe_name
    path.write_bytes(raw)
    return path


def list_workspace_files(workspace: Path) -> set[str]:
    if not workspace.exists():
        return set()
    return {
        p.name
        for p in workspace.iterdir()
        if p.is_file() and not p.name.startswith("_")
    }


def prepare_files_in_workspace(
    processed: list[dict[str, Any]],
    *,
    workspace: Path,
) -> list[dict[str, Any]]:
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


def ensure_df_in_workspace_as_csv(
    df: pd.DataFrame,
    *,
    df_name: str,
    workspace: Path,
    summary: str,
) -> list[dict[str, Any]]:
    safe_name = Path(df_name).name
    if not safe_name.lower().endswith(".csv"):
        safe_name = f"{Path(safe_name).stem}.csv"
    path = workspace / safe_name
    if not path.exists():
        df.to_csv(path, index=False, encoding="utf-8-sig")
    return [
        {
            "name": df_name,
            "type": "csv",
            "summary": summary,
            "workspace_path": str(path),
        }
    ]

