"""LLMClient 导入入口。

实现在独立项目 [llmclient](https://github.com/383827453-max/llmclient)，
作为本项目的依赖安装（见 pyproject.toml / requirements.txt）。

保留 `promptforge.llm_client` 这个导入路径是为了不破坏既有调用方；
新代码建议直接 `from llmclient import LLMClient`。
"""
from __future__ import annotations

from llmclient import LLMClient, LLMError, ProbeResult
from llmclient.endpoints import build_endpoint, build_models_endpoint

__all__ = [
    "LLMClient",
    "LLMError",
    "ProbeResult",
    "build_endpoint",
    "build_models_endpoint",
]
