"""Ollama 호출 동안 스피너 표시 (완료 시간은 메시지 caption에 저장)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import streamlit as st

T = TypeVar("T")

FAST_RESPONSE_SEC = 2.0
LONG_RESPONSE_SEC = 15.0


def format_thinking_label(
    elapsed: float,
    *,
    finished: bool,
    response_mode: str | None = None,
) -> str:
    if not finished:
        if response_mode == "thinking":
            return "추론 중…"
        if response_mode == "instant":
            return "응답 중…"
        return "생각 중…"
    if response_mode == "thinking":
        return f"추론 · {elapsed:.1f}초"
    if response_mode == "instant":
        return f"즉시 · {elapsed:.1f}초"
    if elapsed < FAST_RESPONSE_SEC:
        return f"완료 · {elapsed:.1f}초"
    if elapsed < LONG_RESPONSE_SEC:
        return f"응답 · {elapsed:.1f}초"
    return f"응답 · {elapsed:.1f}초"


def run_with_thinking_status(
    call_fn: Callable[[], T],
    *,
    response_mode: str | None = None,
) -> tuple[T, float]:
    spinner_text = format_thinking_label(0.0, finished=False, response_mode=response_mode)
    with st.spinner(spinner_text):
        started = time.perf_counter()
        return call_fn(), time.perf_counter() - started
