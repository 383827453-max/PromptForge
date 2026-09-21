"""配置管理：API 配置、偏好设置，JSON 持久化。"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .credential import decrypt_secret, encrypt_secret, is_encrypted

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
    """读取配置。落盘的 api_key 是密文，这里解密成明文供运行时使用。

    迁移与容错：
    - 历史版本写的是明文 Key，`decrypt_secret` 原样返回，实现平滑升级；
    - 换机器/换用户导致旧密文解不开时，该 profile 的 key 置空（用户重填），
      其余配置项全部保留，绝不因为一个字段解不开就丢掉整份配置。
    """
    path = _settings_path()
    if not os.path.exists(path):
        return Settings(profiles=[ApiConfig()])
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("settings.json 根节点必须是 JSON 对象")
        profiles_raw = raw.pop("profiles", None) or []
        d = data_dir()
        profiles = []
        for p in profiles_raw:
            if not isinstance(p, dict):
                continue
            cfg = ApiConfig(**_known_fields(ApiConfig, p))
            cfg.api_key = decrypt_secret(cfg.api_key, salt_dir=d)
            profiles.append(cfg)
        s = Settings(**_known_fields(Settings, raw))
        s.profiles = profiles or [ApiConfig()]
        if not 0 <= s.active_profile < len(s.profiles):
            s.active_profile = 0
        return s
    except Exception:
        return Settings(profiles=[ApiConfig()])


def _existing_stored_keys() -> dict:
    """读出当前落盘的密文（profile 索引 → 密文），用于复用已加密值。"""
    path = _settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
    except Exception:
        return {}
    out = {}
    for i, p in enumerate(raw.get("profiles") or []):
        if isinstance(p, dict):
            out[i] = str(p.get("api_key", "") or "")
    return out


def save_settings(s: Settings) -> None:
    """原子写入：先写临时文件再替换，api_key 加密后落盘。

    直接截断覆盖原文件时，若写入过程中断电/崩溃，配置会变成半截 JSON，
    下次启动 load_settings 只能降级为默认值，用户配置全部丢失。

    密文复用：DPAPI 每次加密同一明文得到的密文都不同（内部带随机 IV）。
    如果每次保存都重新加密，即使配置没变文件内容也会变——对用户表现为
    「设置里点一下保存，文件就变了」，也让 git/备份 diff 全是噪音。
    因此先解密已有密文比对：明文未变就沿用原密文，实现幂等保存。

    注意必须同时要求 `is_encrypted(old_stored)`：历史版本落盘的是明文，
    明文经 decrypt_secret 会原样返回，看起来"没变"，若不检查就会一直
    沿用旧明文，迁移永远不生效（Key 永远以明文躺在磁盘上）。
    """
    path = _settings_path()
    d = data_dir()
    data = asdict(s)
    prev = _existing_stored_keys()
    for i, p in enumerate(data.get("profiles", [])):
        if not isinstance(p, dict):
            continue
        plain = p.get("api_key", "") or ""
        old_stored = prev.get(i, "")
        if (plain and is_encrypted(old_stored)
                and decrypt_secret(old_stored, salt_dir=d) == plain):
            p["api_key"] = old_stored      # 明文没变，沿用原密文
        else:
            p["api_key"] = encrypt_secret(plain, salt_dir=d)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _restrict_permissions(path)


def _restrict_permissions(path: str) -> None:
    """尽力把配置文件权限收紧到仅当前用户可读写。

    Windows 上依赖 ACL 继承（用户目录默认已隔离）；POSIX 上显式 chmod 0600。
    失败不影响功能——加密已经是主要防线，这里只是纵深防御。
    """
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * 6 + key[-4:]
