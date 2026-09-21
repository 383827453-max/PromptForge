"""凭据加密：Windows DPAPI 优先，跨平台降级方案。

API Key 明文落在 settings.json 里，任何能读该文件的进程（其他用户账户、
同步到云的备份、误提交的仓库）都能直接拿走。这里做一层按用户的加密。

策略：
- **Windows**：`CryptProtectData` / `CryptUnprotectData`（DPAPI），
  密文绑定当前用户账户，换机器或换用户都解不开，无需自己管密钥。
- **非 Windows**：DPAPI 不存在。退回「机器绑定派生密钥 + 随机盐」的
  HMAC 混淆（`hashlib.scrypt` 派生 → XOR 流）。这**不是**强加密：
  密钥材料在本机可推导，只用于避免明文裸奔，不作为安全边界。

设计约束：**绝不能因为解密失败就丢配置**。换机器、重装系统、
用户账户变更都会让旧密文不可解，此时应退回明文并让上层决定是否
提示用户重填，而不是清空 settings。
"""
from __future__ import annotations

import base64
import hashlib
import os
import platform
import uuid

# 密文前缀：带此后缀的值视为已加密，用于区分历史明文数据
ENC_PREFIX = "enc:v1:"

_IS_WINDOWS = platform.system() == "Windows"

# ---------- Windows DPAPI ----------

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def _dpapi_available() -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        import ctypes  # noqa: F401
        import ctypes.wintypes  # noqa: F401
    except ImportError:
        return False
    return True


class _DataBlob:
    """ctypes 版的 DATA_BLOB。"""

    def __init__(self, data: bytes = b"") -> None:
        import ctypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        self._cls = BLOB
        self._buf = None
        if data:
            self._buf = ctypes.create_string_buffer(data, len(data))
            self.blob = BLOB(len(data), ctypes.cast(self._buf, ctypes.POINTER(ctypes.c_char)))
        else:
            self.blob = BLOB(0, None)


def _dpapi_encrypt(plaintext: str) -> str:
    import ctypes
    from ctypes import wintypes

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    data = plaintext.encode("utf-8")
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()

    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise OSError("CryptProtectData 失败")
    try:
        raw = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return base64.b64encode(raw).decode("ascii")


def _dpapi_decrypt(b64: str) -> str:
    import ctypes
    from ctypes import wintypes

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    raw = base64.b64decode(b64)
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob_in = BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise OSError("CryptUnprotectData 失败（换机器/换用户/配置被改动）")
    try:
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return data.decode("utf-8")


# ---------- 跨平台降级：机器绑定派生密钥 ----------

_SALT_FILE = "credential.salt"


def _machine_secret() -> bytes:
    """收集机器/用户标识作为派生材料（非密码学机密，仅防明文裸奔）。"""
    parts = [
        platform.node(),
        platform.machine(),
        str(uuid.getnode()),
        os.environ.get("USERNAME") or os.environ.get("USER") or "",
    ]
    return "|".join(parts).encode("utf-8")


def _load_or_create_salt(salt_dir: str) -> bytes:
    path = os.path.join(salt_dir, _SALT_FILE)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if len(data) >= 16:
                return data
        except OSError:
            pass
    salt = os.urandom(16)
    try:
        os.makedirs(salt_dir, exist_ok=True)
        with open(path, "wb") as f:
            f.write(salt)
    except OSError:
        pass
    return salt


def _derive_key(salt: bytes) -> bytes:
    return hashlib.scrypt(_machine_secret(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _xor_stream(data: bytes, key: bytes) -> bytes:
    out = bytearray(len(data))
    counter = 0
    offset = 0
    while offset < len(data):
        block = hashlib.sha256(key + counter.to_bytes(8, "big")).digest()
        for i, b in enumerate(block):
            if offset + i >= len(data):
                break
            out[offset + i] = data[offset + i] ^ b
        offset += len(block)
        counter += 1
    return bytes(out)


def _fallback_encrypt(plaintext: str, salt_dir: str) -> str:
    salt = _load_or_create_salt(salt_dir)
    key = _derive_key(salt)
    ct = _xor_stream(plaintext.encode("utf-8"), key)
    mac = hashlib.sha256(key + ct).digest()[:16]
    return base64.b64encode(salt + mac + ct).decode("ascii")


def _fallback_decrypt(b64: str, salt_dir: str) -> str:
    raw = base64.b64decode(b64)
    if len(raw) < 16 + 16:
        raise ValueError("密文长度不足")
    salt, mac, ct = raw[:16], raw[16:32], raw[32:]
    key = _derive_key(salt)
    if hashlib.sha256(key + ct).digest()[:16] != mac:
        raise ValueError("完整性校验失败（密文损坏或密钥不匹配）")
    return _xor_stream(ct, key).decode("utf-8")


# ---------- 对外接口 ----------

def backend_name() -> str:
    return "dpapi" if _dpapi_available() else "scrypt-local"


def encrypt_secret(plaintext: str, salt_dir: str = ".") -> str:
    """加密明文，返回带前缀的密文串。

    已是密文（带前缀）时原样返回，保证幂等——重复保存不会二次加密。
    """
    if not plaintext:
        return ""
    if is_encrypted(plaintext):
        return plaintext
    if _dpapi_available():
        try:
            return ENC_PREFIX + _dpapi_encrypt(plaintext)
        except Exception:
            # DPAPI 异常时退回降级方案，绝不因为加密失败而拒绝保存
            return ENC_PREFIX + "fb:" + _fallback_encrypt(plaintext, salt_dir)
    return ENC_PREFIX + "fb:" + _fallback_encrypt(plaintext, salt_dir)


def decrypt_secret(stored: str, salt_dir: str = ".") -> str:
    """解密。

    非密文（历史明文数据）原样返回，实现旧配置平滑迁移。
    解密失败返回空串——调用方据此提示用户重填，而不是崩溃或清空整份配置。
    """
    if not stored:
        return ""
    if not is_encrypted(stored):
        return stored  # 旧版明文，直接可用
    payload = stored[len(ENC_PREFIX):]
    try:
        if payload.startswith("fb:"):
            return _fallback_decrypt(payload[3:], salt_dir)
        return _dpapi_decrypt(payload)
    except Exception:
        return ""


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(ENC_PREFIX)
