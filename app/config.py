from __future__ import annotations

import os
from pathlib import Path

# Defaults
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Material Symbols (rounded) — https://fonts.google.com/icons
ICON_PAGE_CHAT = ":material/chat:"
ICON_PAGE_OLLAMA = ":material/memory:"
ICON_REFRESH = ":material/refresh:"
ICON_DOWNLOAD = ":material/download:"
ICON_DELETE = ":material/delete:"

# Files / folders
REPO_ROOT = Path(__file__).resolve().parent.parent
CHAT_HISTORY_DIR = REPO_ROOT / "chat_history"
WORKSPACE_ROOT = CHAT_HISTORY_DIR / "workspaces"
CHAT_INDEX_FILE = CHAT_HISTORY_DIR / "index.json"
USER_PROFILE_FILE = CHAT_HISTORY_DIR / "user_profile.json"
APP_SETTINGS_FILE = CHAT_HISTORY_DIR / "app_settings.json"

