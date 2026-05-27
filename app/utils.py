from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_chat(title: str, *, default_title: str) -> dict[str, Any]:
    ts = now_iso()
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "created_at": ts,
        "updated_at": ts,
        "messages": [],
    }
