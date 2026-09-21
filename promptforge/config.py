"""配置管理：API 配置、偏好设置，JSON 持久化。"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import asdict, dataclass, field
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


def _known_fields(cls, raw: dict) -> dict:
    """只保留 dataclass 已声明的字段。

    配置文件可能由更新（或更旧）的版本写入，含当前代码不认识的键。
    直接 `cls(**raw)` 会抛 TypeError，让整个 load_settings 落进 except
    分支返回默认配置——表现为用户的 API Key 与全部配置档案被静默清空。
    未知键一律忽略，而不是放弃整份配置。
    """
    names = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in raw.items() if k in names}


def load_settings() -> Settings:
    path = _settings_path()
    if not os.path.exists(path):
        return Settings(profiles=[ApiConfig()])
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("settings.json 根节点必须是 JSON 对象")
        profiles_raw = raw.pop("profiles", None) or []
        profiles = [
            ApiConfig(**_known_fields(ApiConfig, p))
            for p in profiles_raw if isinstance(p, dict)
        ]
        s = Settings(**_known_fields(Settings, raw))
        s.profiles = profiles or [ApiConfig()]
        if not 0 <= s.active_profile < len(s.profiles):
            s.active_profile = 0
        return s
    except Exception:
        return Settings(profiles=[ApiConfig()])


def save_settings(s: Settings) -> None:
    """原子写入：先写临时文件再替换。

    直接截断覆盖原文件时，若写入过程中断电/崩溃，配置会变成半截 JSON，
    下次启动 load_settings 只能降级为默认值，用户配置全部丢失。
    """
    path = _settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(s), f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * 6 + key[-4:]
