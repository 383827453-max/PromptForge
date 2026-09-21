# llmclient

OpenAI 兼容接口的最小客户端。无 GUI、无框架依赖，只要 `requests`。

从 [PromptForge](https://github.com/383827453-max/PromptForge) 抽出，用于消除同一套
网关兼容逻辑在多个项目里重复维护的问题。

## 它解决什么

对接自建网关 / 中转站 / 本地推理服务时，真正耗时的不是发请求，而是处理这些坑：

| 坑 | 本库的做法 |
|---|---|
| 网关 keep-alive 不关连接，返回文字后客户端还在等读结束 | 强制 `Connection: close` |
| 响应不带 charset，requests 退回 ISO-8859-1，中文全乱码 | 强制按 UTF-8 解码 |
| 网关不发 `[DONE]` 又不关连接，流式永久挂起 | 检测 `finish_reason` 立即退出 |
| Base URL 写法五花八门（主机 / 带 `/v1` / 完整端点） | `build_endpoint()` 统一归一化 |
| 失败时只有干巴巴的 `ConnectionError` | 按异常类型给带实际地址的排查建议 |
| 想中断流式只能强杀线程（socket 悬空、句柄泄漏） | `should_stop` 谓词协作式取消 |
| 想知道哪些网关可用 / 多快 | `probe()` / `probe_models()` 带计时 |

## 安装

```bash
pip install -e .          # 本地开发
```

## 用法

本库不自带配置类：`cfg` 是鸭子类型，任何具备 `base_url` / `api_key` / `model`
三个属性的对象都能直接传。宿主项目用自己的 dataclass 或 pydantic 模型即可。

```python
from dataclasses import dataclass
from llmclient import LLMClient, LLMError, build_endpoint

@dataclass
class MyConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""

client = LLMClient(MyConfig(base_url="http://127.0.0.1:8080", api_key="sk-x",
                            model="gpt-4o"))

# 端点在请求前就能看到的实际地址
print(build_endpoint(client.base_url))   # http://127.0.0.1:8080/v1/chat/completions

# 连通性自检（短超时、不重试、快速失败）
try:
    print(client.ping())
except LLMError as e:
    print(e)          # 已是给人看的诊断文本，不是 traceback
```

### 流式

```python
import threading

cancel = threading.Event()

for chunk in client.stream("写一个快速排序", should_stop=cancel.is_set):
    print(chunk, end="", flush=True)

# 任意时刻 cancel.set() 即可干净中止（连接会被正确关闭）
```

### 探测与测速

```python
r = client.probe()            # 先试 /v1/models，不通再退回 chat 探活
print(r.ok, f"{r.elapsed_ms:.0f}ms", r.models[:5])

# 单次失败不抛异常，方便批量扫一堆网关
for cfg in many_configs:
    res = LLMClient(cfg).probe(timeout=15)
    print(cfg.name, res.summary())
```

### 模型列表

```python
try:
    models = client.list_models()
except LLMError as e:
    print("网关未实现 /v1/models：", e)
```

## 模块结构

```
llmclient/
├── __init__.py      # 公开 API 导出
├── client.py        # LLMClient、ProbeResult
├── endpoints.py     # build_endpoint / build_models_endpoint / chat_prefix
└── errors.py        # LLMError
```

## 测试

```bash
pip install -e ".[dev]"
python -m pytest tests -v
```

测试全部使用假的 Response 替身，不发真实网络请求。

## License

MIT © 2026 Liu
