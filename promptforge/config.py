"""配置管理：API 配置、偏好设置，JSON 持久化。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional

APP_NAME = "PromptForge"


def data_dir() -> str:
    base = os.environ.get("PROMPTFORGE_DATA_DIR")
    if base:
        d = base
    elif os.name == "nt":
        d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    else:
        d = os.path.join(os.path.expanduser("~"), "." + APP_NAME.lower())
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class ApiConfig:
    name: str = "默认"
    base_url: str = ""
    api_key: str = ""
    model: str = ""

    def is_valid(self) -> bool:
        return bool(self.base_url.strip() and self.model.strip())


@dataclass
class Settings:
    profiles: List[ApiConfig] = field(default_factory=list)
    active_profile: int = 0
    timeout: int = 120
    temperature: float = 0.7
    max_tokens: int = 0  # 0 = 不限制
    use_stream: bool = True
    theme: str = "dark"
    hotkey: str = "Ctrl+Alt+P"
    copy_on_enhance: bool = False

    def active(self) -> Optional[ApiConfig]:
        if not self.profiles:
            return None
        self.active_profile = max(0, min(self.active_profile, len(self.profiles) - 1))
        return self.profiles[self.active_profile]


def _settings_path() -> str:
    return os.path.join(data_dir(), "settings.json")


def load_settings() -> Settings:
    path = _settings_path()
    if not os.path.exists(path):
        return Settings(profiles=[ApiConfig()])
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        profiles = [ApiConfig(**p) for p in raw.pop("profiles", [])]
        s = Settings(**raw)
        s.profiles = profiles or [ApiConfig()]
        return s
    except Exception:
        return Settings(profiles=[ApiConfig()])


def save_settings(s: Settings) -> None:
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(asdict(s), f, ensure_ascii=False, indent=2)


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * 6 + key[-4:]