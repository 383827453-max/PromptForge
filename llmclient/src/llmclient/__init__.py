"""llmclient — OpenAI 兼容接口的最小客户端。

从 PromptForge 抽出的可复用实现，解决同一套网关兼容逻辑在多个项目里
重复维护的问题。无 GUI、无框架依赖，只依赖 requests。

典型用法::

    from llmclient import LLMClient, ClientConfig

    client = LLMClient(ClientConfig(
        base_url="http://127.0.0.1:8080",   # 或 .../v1，或完整端点
        api_key="sk-xxx",                   # 网关无需鉴权时留空
        model="gpt-4o",
    ))
    print(client.ping())                    # 连通性自检
    print(client.list_models())             # 列出可用模型
    print(client.complete("写一个快排"))     # 非流式
    for chunk in client.stream("写一个快排"):  # 流式
        print(chunk, end="")

宿主项目可以传自己的配置对象（鸭子类型），不要求继承 ClientConfig::

    client = LLMClient(my_app_config)   # 具备 base_url/api_key/model 即可
"""
from __future__ import annotations

from .client import LLMClient, ProbeResult
from .endpoints import build_endpoint, build_models_endpoint
from .errors import LLMError

__version__ = "0.1.0"

__all__ = [
    "LLMClient",
    "ProbeResult",
    "LLMError",
    "build_endpoint",
    "build_models_endpoint",
    "__version__",
]
