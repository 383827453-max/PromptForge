"""credential.py 测试：加密往返、迁移、容错、后端选择。"""
import json
import os

from promptforge.config import ApiConfig, Settings, data_dir, load_settings, save_settings
from promptforge.credential import (
    ENC_PREFIX,
    backend_name,
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
)


def test_encrypt_roundtrip():
    ct = encrypt_secret("sk-abc", salt_dir=str(data_dir()))
    assert is_encrypted(ct)
    assert "sk-abc" not in ct
    assert decrypt_secret(ct, salt_dir=str(data_dir())) == "sk-abc"


def test_encrypt_empty_is_empty():
    assert encrypt_secret("", salt_dir=".") == ""
    assert decrypt_secret("", salt_dir=".") == ""


def test_encrypt_is_idempotent_on_ciphertext():
    ct = encrypt_secret("sk-x", salt_dir=str(data_dir()))
    assert encrypt_secret(ct, salt_dir=str(data_dir())) == ct


def test_plaintext_passthrough_for_migration():
    """历史版本存的明文必须原样可用，否则老用户升级后配置失效。"""
    assert decrypt_secret("plain-old-key", salt_dir=".") == "plain-old-key"
    assert not is_encrypted("plain-old-key")


def test_undecryptable_returns_empty_not_raise():
    """密文损坏/换机器时应返回空串，由上层提示重填，而不是抛异常。"""
    assert decrypt_secret(ENC_PREFIX + "fb:bm90LXZhbGlkLWJhc2U2NA==", salt_dir=".") == ""


def test_corrupted_mac_detected():
    ct = encrypt_secret("sk-original", salt_dir=str(data_dir()))
    body = ct[len(ENC_PREFIX):]
    tampered = ENC_PREFIX + body[:-4] + ("AAAA" if not body.endswith("AAAA") else "BBBB")
    assert decrypt_secret(tampered, salt_dir=str(data_dir())) == ""


def test_unicode_key_roundtrip():
    key = "密钥-🔑-ünïcode"
    ct = encrypt_secret(key, salt_dir=str(data_dir()))
    assert decrypt_secret(ct, salt_dir=str(data_dir())) == key


def test_backend_name_is_reported():
    assert backend_name() in ("dpapi", "scrypt-local")


# ---------- config 层集成 ----------

def test_settings_saves_ciphertext_not_plaintext():
    save_settings(Settings(profiles=[ApiConfig(
        base_url="http://x/v1", api_key="sk-SECRET-DO-NOT-LEAK", model="m")]))
    raw = open(os.path.join(data_dir(), "settings.json"), encoding="utf-8").read()
    assert "sk-SECRET-DO-NOT-LEAK" not in raw
    assert "enc:v1:" in raw


def test_settings_roundtrip_gives_plaintext_back():
    save_settings(Settings(profiles=[ApiConfig(
        base_url="http://x/v1", api_key="sk-round", model="m")]))
    assert load_settings().profiles[0].api_key == "sk-round"


def test_settings_save_is_idempotent():
    """配置未变时重复保存不应改动文件内容（DPAPI 每次密文不同）。"""
    save_settings(Settings(profiles=[ApiConfig(
        base_url="http://x/v1", api_key="sk-stable", model="m")]))
    p = os.path.join(data_dir(), "settings.json")
    first = open(p, encoding="utf-8").read()
    save_settings(load_settings())
    assert open(p, encoding="utf-8").read() == first


def test_settings_reencrypts_when_key_changes():
    save_settings(Settings(profiles=[ApiConfig(
        base_url="http://x/v1", api_key="sk-old", model="m")]))
    p = os.path.join(data_dir(), "settings.json")
    first = open(p, encoding="utf-8").read()
    s = load_settings()
    s.profiles[0].api_key = "sk-new"
    save_settings(s)
    assert open(p, encoding="utf-8").read() != first
    assert load_settings().profiles[0].api_key == "sk-new"


def test_legacy_plaintext_settings_migrated_on_save():
    p = os.path.join(data_dir(), "settings.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"profiles": [{"name": "old", "base_url": "http://o/v1",
                                 "api_key": "LEGACY-PLAIN", "model": "m"}]}, f)
    assert load_settings().profiles[0].api_key == "LEGACY-PLAIN"
    save_settings(load_settings())
    assert "LEGACY-PLAIN" not in open(p, encoding="utf-8").read()
    assert load_settings().profiles[0].api_key == "LEGACY-PLAIN"


def test_undecryptable_key_does_not_drop_other_settings():
    """换机器后解不开 Key，其余配置必须完整保留。"""
    p = os.path.join(data_dir(), "settings.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"profiles": [{"name": "KEEP", "base_url": "http://k/v1",
                                 "api_key": "enc:v1:fb:broken", "model": "KEEP-M"}],
                   "theme": "light", "timeout": 77}, f)
    s = load_settings()
    assert s.profiles[0].api_key == ""
    assert s.profiles[0].model == "KEEP-M"
    assert s.theme == "light"
    assert s.timeout == 77


def test_multiple_profiles_all_encrypted():
    save_settings(Settings(profiles=[
        ApiConfig(name="a", base_url="http://a/v1", api_key="key-a", model="m"),
        ApiConfig(name="b", base_url="http://b/v1", api_key="key-b", model="m"),
    ]))
    raw = open(os.path.join(data_dir(), "settings.json"), encoding="utf-8").read()
    assert "key-a" not in raw and "key-b" not in raw
    back = load_settings()
    assert [p.api_key for p in back.profiles] == ["key-a", "key-b"]


def test_empty_key_profile_survives():
    save_settings(Settings(profiles=[ApiConfig(name="nokey", base_url="http://n/v1",
                                               api_key="", model="m")]))
    back = load_settings()
    assert back.profiles[0].api_key == ""
    assert back.profiles[0].name == "nokey"


def test_salt_file_created_for_fallback_backend():
    """降级后端需要盐文件；DPAPI 后端不需要，存在与否都不该报错。"""
    encrypt_secret("x", salt_dir=str(data_dir()))
    salt = os.path.join(data_dir(), "credential.salt")
    if backend_name() == "scrypt-local":
        assert os.path.exists(salt)
    assert True  # dpapi 分支下不强制要求盐文件
