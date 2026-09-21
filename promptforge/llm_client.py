"""兼容层 + 包定位：把 LLMClient 委托给独立包 llmclient。

实现已抽到本仓库的 `llmclient/` 子包（src layout，可独立安装与被其他项目复用），
这里保留原有导入路径 `promptforge.llm_client`，不破坏既有调用方。

新代码建议直接 `from llmclient import LLMClient`。
"""
from __future__ import annotations

import os
import sys


def _ensure_llmclient_importable() -> None:
    """确保 `import llmclient` 拿到的是真正的包，而不是同名目录。

    坑：仓库根有个叫 `llmclient/` 的文件夹（子包目录）。在仓库根运行脚本时
    它可能已被当作 namespace package 解析，`import llmclient` 会"成功"但
    里面没有任何属性——于是 `from llmclient import LLMClient` 抛 ImportError。
    所以这里不能只看 import 是否成功，必须验证目标符号真的存在。
    """
    pkg = None
    try:
        import llmclient as pkg  # noqa: PLC0415
    except ImportError:
        pkg = None
    if pkg is not None and hasattr(pkg, "LLMClient") and hasattr(pkg, "__file__"):
        return  # 已安装且可用

    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(os.path.dirname(here), "llmclient", "src")
    if os.path.isdir(cand):
        # 把 src 放到最前面，并丢弃之前解析到的空 namespace package，
        # 否则已缓存的 sys.modules['llmclient'] 会继续命中错误对象。
        if cand in sys.path:
            sys.path.remove(cand)
        sys.path.insert(0, cand)
        cached = sys.modules.get("llmclient")
        if cached is not None and not hasattr(cached, "LLMClient"):
            del sys.modules["llmclient"]


_ensure_llmclient_importable()

from llmclient.endpoints import build_endpoint, build_models_endpoint  # noqa: E402

from llmclient import LLMClient, LLMError, ProbeResult  # noqa: E402

__all__ = [
    "LLMClient",
    "LLMError",
    "ProbeResult",
    "build_endpoint",
    "build_models_endpoint",
]
