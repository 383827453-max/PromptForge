"""端点归一化。

各家网关、中转站、本地推理服务的 Base URL 写法五花八门：有的填到主机，
有的带 /v1，有的直接给完整端点。这里统一归一化成可直接请求的地址。
"""
from __future__ import annotations

CHAT_SUFFIX = "/chat/completions"
MODELS_SUFFIX = "/models"


def build_endpoint(base_url: str) -> str:
    """把 Base URL 归一化为完整的 chat completions 请求地址。

    >>> build_endpoint("http://a")
    'http://a/v1/chat/completions'
    >>> build_endpoint("http://a/v1")
    'http://a/v1/chat/completions'
    >>> build_endpoint("http://a/v1/chat/completions")
    'http://a/v1/chat/completions'
    """
    base = base_url.strip().rstrip("/")
    if base.endswith(CHAT_SUFFIX):
        return base
    if base.endswith("/v1"):
        return base + CHAT_SUFFIX
    return base + "/v1" + CHAT_SUFFIX


def build_models_endpoint(base_url: str) -> str:
    """把 Base URL 归一化为模型列表地址（GET /v1/models）。

    与 build_endpoint 共用同一套归一化规则：无论用户填的是主机、
    带 /v1 的前缀，还是完整的 chat 端点，都能推出对应的 models 地址。
    """
    base = base_url.strip().rstrip("/")
    if base.endswith(MODELS_SUFFIX):
        return base
    if base.endswith(CHAT_SUFFIX):
        base = base[: -len(CHAT_SUFFIX)].rstrip("/")
    if base.endswith("/v1"):
        return base + MODELS_SUFFIX
    return base + "/v1" + MODELS_SUFFIX


def chat_prefix(base_url: str) -> str:
    """返回不含 /chat/completions 的前缀，便于推导其他同族端点。"""
    ep = build_endpoint(base_url)
    return ep[: -len(CHAT_SUFFIX)]
