from __future__ import annotations

import io
from typing import Any

import pandas as pd


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


def process_uploaded_file(
    uploaded_file: Any,
    *,
    encoding: str,
    max_text_chars: int,
) -> dict[str, Any]:
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
        if len(text) > max_text_chars:
            text = text[:max_text_chars] + "\n... (이하 생략)"
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

