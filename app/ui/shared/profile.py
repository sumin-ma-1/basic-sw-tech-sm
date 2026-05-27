from __future__ import annotations

from typing import Any

import streamlit as st

from app.config import CHAT_HISTORY_DIR, USER_PROFILE_FILE
from app.services.storage import save_user_profile as storage_save_user_profile

PROFILE_NONE_LABEL = "선택 안 함"
DEFAULT_USER_PROFILE: dict[str, str] = {
    "name": "",
    "honorific": "",
    "language": "",
    "timezone_region": "",
    "bio": "",
}
LANGUAGE_OPTIONS = [
    PROFILE_NONE_LABEL,
    "한국어",
    "English",
    "日本語",
    "中文(简体)",
    "中文(繁體)",
    "Español",
    "Français",
    "Deutsch",
]
TIMEZONE_REGION_OPTIONS = [
    PROFILE_NONE_LABEL,
    "Asia/Seoul · 대한민국",
    "Asia/Tokyo · 일본",
    "Asia/Shanghai · 중국",
    "Asia/Hong_Kong · 홍콩",
    "Asia/Singapore · 싱가포르",
    "Asia/Dubai · UAE",
    "Asia/Kolkata · 인도",
    "Europe/London · 영국",
    "Europe/Paris · 프랑스",
    "Europe/Berlin · 독일",
    "America/New_York · 미국 동부",
    "America/Chicago · 미국 중부",
    "America/Denver · 미국 산악",
    "America/Los_Angeles · 미국 서부",
    "Australia/Sydney · 호주",
    "Pacific/Auckland · 뉴질랜드",
    "UTC",
]


def save_user_profile() -> None:
    storage_save_user_profile(
        chat_history_dir=CHAT_HISTORY_DIR,
        user_profile_file=USER_PROFILE_FILE,
        user_profile=st.session_state.user_profile,
    )


def profile_select_options(
    options: list[str], saved_value: str
) -> tuple[list[str], int]:
    if saved_value and saved_value not in options:
        options = options + [saved_value]
    display = saved_value if saved_value else PROFILE_NONE_LABEL
    return options, options.index(display)


def profile_value_from_select(selected: str) -> str:
    return "" if selected == PROFILE_NONE_LABEL else selected


def profile_button_label() -> str:
    name = st.session_state.user_profile.get("name", "").strip()
    return name if name else "프로필 설정"


def build_user_profile_context() -> str:
    profile = st.session_state.user_profile
    fields = [
        ("이름", profile.get("name", "")),
        ("호칭", profile.get("honorific", "")),
        ("사용 언어", profile.get("language", "")),
        ("시간대 / 지역", profile.get("timezone_region", "")),
        ("자기소개", profile.get("bio", "")),
    ]
    lines = [f"{label}: {value}" for label, value in fields if value]
    if not lines:
        return ""
    return (
        "--- 사용자 정보 ---\n"
        + "\n".join(lines)
        + "\n(위 정보를 참고해 사용자에게 맞춤 응답을 제공하세요.)"
    )


@st.dialog("유저 프로필", width="large")
def user_profile_dialog() -> None:
    st.caption("모든 항목은 선택 입력입니다. 저장된 정보는 모델에게 전달됩니다.")
    profile = st.session_state.user_profile

    name = st.text_input(
        "이름",
        value=profile.get("name", ""),
        placeholder="예: 홍길동 (선택)",
    )
    honorific = st.text_input(
        "호칭",
        value=profile.get("honorific", ""),
        placeholder="예: 언니, Alex (선택)",
    )
    lang_options, lang_index = profile_select_options(
        list(LANGUAGE_OPTIONS), profile.get("language", "")
    )
    language = st.selectbox("사용 언어", lang_options, index=lang_index)

    tz_options, tz_index = profile_select_options(
        list(TIMEZONE_REGION_OPTIONS), profile.get("timezone_region", "")
    )
    timezone_region = st.selectbox("시간대 / 지역", tz_options, index=tz_index)
    bio = st.text_area(
        "간단한 자기소개",
        value=profile.get("bio", ""),
        placeholder="예: 데이터 분석을 배우는 대학생입니다. (선택)",
        height=100,
    )

    col_save, col_clear = st.columns(2)
    with col_save:
        if st.button("저장", type="primary", use_container_width=True):
            st.session_state.user_profile = {
                "name": name.strip(),
                "honorific": honorific.strip(),
                "language": profile_value_from_select(language),
                "timezone_region": profile_value_from_select(timezone_region),
                "bio": bio.strip(),
            }
            save_user_profile()
            st.rerun()
    with col_clear:
        if st.button("프로필 비우기", use_container_width=True):
            st.session_state.user_profile = dict(DEFAULT_USER_PROFILE)
            save_user_profile()
            st.rerun()
