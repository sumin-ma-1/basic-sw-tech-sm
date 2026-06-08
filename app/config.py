from __future__ import annotations

import os
from pathlib import Path

# Defaults
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_REMOTE_HOST = os.environ.get("OLLAMA_REMOTE_HOST", "").strip()
# SSH 터널 대상, hostname/GPU 자동 조회용
OLLAMA_SSH_TARGET = os.environ.get("OLLAMA_SSH", "").strip()

# Material Symbols (rounded), https://fonts.google.com/icons
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
OLLAMA_REMOTE_HOST_FILE = CHAT_HISTORY_DIR / "ollama_remote_host.txt"
OLLAMA_REMOTE_GPU_FILE = CHAT_HISTORY_DIR / "ollama_remote_gpu.txt"
OLLAMA_SSH_TARGET_FILE = CHAT_HISTORY_DIR / "ollama_ssh_target.txt"

