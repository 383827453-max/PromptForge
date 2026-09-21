"""config.py 单元测试：配置读写、容错、脱敏。

覆盖回归：配置文件含未知键时，早期实现会抛 TypeError → 落进 except
→ 返回默认 Settings，导致用户 API Key 与全部配置档案被静默清空。
"""
import json
import os

import pytest

from promptforge.config import ApiConfig, Settings, data_dir, load_settings, mask_key, save_settings


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def test_data_dir_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMPTFORGE_DATA_DIR", str(tmp_path / "custom"))
    assert data_dir() == str(tmp_path / "custom")
    assert os.path.isdir(data_dir())


def test_load_default_when_missing():
    s = load_settings()
    assert len(s.profiles) == 1
    assert s.theme == "dark"


def test_roundtrip_preserves_api_key():
    s = Settings(profiles=[ApiConfig(name="网关", base_url="http://x/v1",
                                     api_key="sk-secret-123", model="m1")],
                 theme="light", timeout=99)
    save_settings(s)
    back = load_settings()
    assert back.profiles[0].api_key == "sk-secret-123"
    assert back.profiles[0].name == "网关"
    assert back.theme == "light"
    assert back.timeout == 99


def test_unknown_top_level_key_is_ignored():
    """回归：顶层未知键不得导致整份配置被丢弃。"""
    p = os.path.join(data_dir(), "settings.json")
    _write(p, {"profiles": [{"name": "A", "base_url": "http://x/v1",
                             "api_key": "KEEP", "model": "m"}],
               "theme": "light", "future_feature_flag": {"nested": 1}})
    s = load_settings()
    assert s.profiles[0].api_key == "KEEP"
    assert s.profiles[0].name == "A"
    assert s.theme == "light"


def test_unknown_profile_key_is_ignored():
    """回归：profile 内未知键不得清空该 profile。"""
    p = os.path.join(data_dir(), "settings.json")
    _write(p, {"profiles": [{"name": "A", "base_url": "http://x/v1",
                             "api_key": "KEEP", "model": "m",
                             "proxy": "http://127.0.0.1:7890"}]})
    s = load_settings()
    assert s.profiles[0].api_key == "KEEP"
    assert s.profiles[0].name == "A"


def test_broken_json_falls_back_to_default():
    p = os.path.join(data_dir(), "settings.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    s = load_settings()
    assert len(s.profiles) == 1


def test_non_dict_root_falls_back():
    p = os.path.join(data_dir(), "settings.json")
    _write(p, ["unexpected", "list"])
    s = load_settings()
    assert len(s.profiles) == 1


def test_active_profile_clamped_when_out_of_range():
    p = os.path.join(data_dir(), "settings.json")
    _write(p, {"profiles": [{"name": "only", "base_url": "u", "model": "m"}],
               "active_profile": 7})
    s = load_settings()
    assert s.active_profile == 0
    assert s.active().name == "only"


def test_empty_profiles_list_gets_one_default():
    p = os.path.join(data_dir(), "settings.json")
    _write(p, {"profiles": []})
    s = load_settings()
    assert len(s.profiles) == 1


def test_non_dict_profile_entries_are_skipped():
    p = os.path.join(data_dir(), "settings.json")
    _write(p, {"profiles": ["junk", 42, {"name": "ok", "base_url": "u", "model": "m"}]})
    s = load_settings()
    assert len(s.profiles) == 1
    assert s.profiles[0].name == "ok"


def test_save_settings_is_atomic_no_tmp_left():
    save_settings(Settings(profiles=[ApiConfig()]))
    d = data_dir()
    assert os.path.exists(os.path.join(d, "settings.json"))
    assert not os.path.exists(os.path.join(d, "settings.json.tmp"))


def test_save_settings_overwrites_cleanly():
    save_settings(Settings(profiles=[ApiConfig(name="first")], timeout=11))
    save_settings(Settings(profiles=[ApiConfig(name="second")], timeout=22))
    back = load_settings()
    assert back.profiles[0].name == "second"
    assert back.timeout == 22


@pytest.mark.parametrize("key,expected", [
    ("", ""),
    ("abcd", "****"),
    ("abcd1234", "********"),
    ("abcd12345", "abcd******2345"),
])
def test_mask_key(key, expected):
    assert mask_key(key) == expected


def test_mask_key_never_leaks_middle():
    body = "SUPERSECRETMIDDLE"
    masked = mask_key("sk-" + body + "-tail")
    assert body not in masked


def test_is_valid_requires_base_url_and_model():
    assert not ApiConfig().is_valid()
    assert not ApiConfig(base_url="http://x/v1").is_valid()
    assert not ApiConfig(model="m").is_valid()
    assert ApiConfig(base_url="http://x/v1", model="m").is_valid()
    assert not ApiConfig(base_url="   ", model="m").is_valid()
