"""OpenAI 兼容 API 客户端：流式（SSE）与非流式、重试、端点探测。

设计要点（均为踩过真实网关坑之后的取舍）：
- 强制 `Connection: close`：部分网关 keep-alive 不关连接，requests 会
  一直等读结束，表现为「文字返回完了但界面还要卡一会」。
- 强制 UTF-8 解码：网关不返回 charset 时 requests 退回 ISO-8859-1，
  中文全变乱码。
- 检测 `finish_reason` 立即退出：网关不发 `[DONE]` 又不关连接时，
  只靠 `[DONE]` 判断会永久挂起。
- 协作式取消（`should_stop`）：由调用方给谓词，逐块检查后干净退出，
  避免调用方用强杀线程的方式中断（会让 socket 悬空、句柄泄漏）。
- 所有失败收敛为 `LLMError`，消息里带实际请求地址与针对性建议。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, List, Optional

import requests

from .endpoints import build_endpoint, build_models_endpoint
from .errors import LLMError

__all__ = ["LLMClient", "ProbeResult"]


@dataclass
class ProbeResult:
    """一次端点探测的结果。"""

    ok: bool
    url: str
    status: Optional[int] = None
    elapsed_ms: float = 0.0
    detail: str = ""
    models: List[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            ms = f"{self.elapsed_ms:.0f}ms"
            extra = f"，{len(self.models)} 个模型" if self.models else ""
            return f"OK {ms}{extra}"
        return f"失败：{self.detail}"


class LLMClient:
    """OpenAI 兼容接口客户端，可对接任意自建网关。

    cfg 是鸭子类型：任何具备 `base_url` / `api_key` / `model` 三个属性的
    对象都能直接用，宿主项目不必继承特定基类。
    """

    def __init__(self, cfg: Any, timeout: int = 120, temperature: float = 0.7,
                 max_tokens: int = 0, retries: int = 2) -> None:
        self.cfg = cfg
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries

    # ---------- 属性 ----------

    @property
    def base_url(self) -> str:
        return str(getattr(self.cfg, "base_url", "") or "")

    @property
    def api_key(self) -> str:
        return str(getattr(self.cfg, "api_key", "") or "")

    @property
    def model(self) -> str:
        return str(getattr(self.cfg, "model", "") or "")

    @property
    def endpoint(self) -> str:
        return build_endpoint(self.base_url)

    @property
    def models_endpoint(self) -> str:
        return build_models_endpoint(self.base_url)

    # ---------- 请求构造 ----------

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Connection": "close",
        }
        if self.api_key.strip():
            h["Authorization"] = f"Bearer {self.api_key.strip()}"
        return h

    def _payload(self, system_prompt: str, stream: bool) -> dict:
        p = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}],
            "temperature": self.temperature,
            "stream": stream,
        }
        if self.max_tokens > 0:
            p["max_tokens"] = self.max_tokens
        return p

    # ---------- 传输 ----------

    def _post(self, stream: bool, system_prompt: str, timeout: Optional[int] = None,
              retries: Optional[int] = None) -> requests.Response:
        eff_timeout = timeout if timeout is not None else self.timeout
        eff_retries = retries if retries is not None else self.retries
        last_err: Optional[Exception] = None
        for attempt in range(eff_retries + 1):
            try:
                resp = requests.post(
                    self.endpoint,
                    headers=self._headers(),
                    json=self._payload(system_prompt, stream),
                    timeout=eff_timeout,
                    stream=stream,
                )
                if resp.status_code >= 400:
                    body = resp.text[:500]
                    resp.close()
                    raise LLMError(f"HTTP {resp.status_code}: {body}")
                resp.encoding = "utf-8"
                return resp
            except LLMError:
                raise
            except requests.RequestException as e:
                last_err = e
                if attempt < eff_retries:
                    time.sleep(1.5 * (attempt + 1))
        raise LLMError(self._format_error(last_err))

    def _format_error(self, e: Optional[Exception]) -> str:
        """按异常类型给出带完整请求地址的针对性诊断。

        注意：SSLError / ReadTimeout 等挂在 requests.exceptions 下，
        顶层 `requests.SSLError` 并不存在；且 SSLError 是
        ConnectionError 的子类，必须先判，否则会被后者吃掉。
        """
        url = self.endpoint
        exc = requests.exceptions
        if isinstance(e, exc.SSLError):
            return f"SSL 证书错误：{url}\n若为自签名证书网关，请检查证书配置。"
        if isinstance(e, exc.ReadTimeout):
            return (f"读取超时：{url}\n"
                    "服务器接受了连接，但没有返回有效响应。"
                    "这通常说明该地址不是 OpenAI 兼容 API 接口"
                    "（例如误填了普通网站地址），请检查 Base URL。")
        if isinstance(e, exc.ConnectTimeout):
            return f"连接超时：{url}\n请检查 Base URL 是否正确、网络或防火墙是否拦截。"
        if isinstance(e, exc.ConnectionError):
            return f"无法连接服务器：{url}\n请检查 Base URL 是否正确、服务是否在运行。"
        if isinstance(e, exc.Timeout):
            return f"请求超时：{url}\n请适当加大请求超时时间。"
        return f"请求失败：{url}\n{e}"

    # ---------- 业务接口 ----------

    def complete(self, system_prompt: str, timeout: Optional[int] = None,
                 retries: Optional[int] = None) -> str:
        """非流式调用，返回完整文本。"""
        resp = self._post(False, system_prompt, timeout=timeout, retries=retries)
        try:
            data = resp.json()
        except ValueError as e:
            raise LLMError(
                f"响应不是合法 JSON（{self.endpoint}），"
                "请检查 Base URL 是否指向 OpenAI 兼容接口") from e
        finally:
            resp.close()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMError(
                f"响应结构异常: {json.dumps(data, ensure_ascii=False)[:300]}") from e

    def ping(self) -> str:
        """连通性自检：短超时 + 非流式 + 不重试，快速失败。"""
        return self.complete("请只回复两个字：成功", timeout=30, retries=0)

    def stream(self, system_prompt: str, on_delta: Optional[Callable[[str], None]] = None,
               should_stop: Optional[Callable[[], bool]] = None) -> Iterator[str]:
        """流式调用，逐块 yield 增量文本。

        should_stop：传入「返回 True 表示调用方希望中止」的谓词，
        循环在每个 SSE 块之间检查后干净退出。
        """
        resp = self._post(True, system_prompt)
        try:
            for raw_line in resp.iter_lines(decode_unicode=True):
                if should_stop is not None and should_stop():
                    break
                if not raw_line:
                    continue
                line = raw_line.strip()
                if line.startswith(":"):  # SSE 注释/心跳
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                try:
                    choice = obj["choices"][0]
                    delta = choice.get("delta", {}) or {}
                    chunk = delta.get("content") or ""
                    finish = choice.get("finish_reason")
                except (KeyError, IndexError):
                    continue
                if chunk:
                    if on_delta:
                        on_delta(chunk)
                    yield chunk
                if finish:
                    break
        finally:
            resp.close()

    # ---------- 端点探测（供模型检测类工具复用） ----------

    def list_models(self, timeout: Optional[int] = None) -> List[str]:
        """GET /v1/models，返回模型 id 列表。

        部分网关不实现该端点，此时抛 LLMError，由调用方决定是否降级。
        """
        eff_timeout = timeout if timeout is not None else 30
        try:
            resp = requests.get(self.models_endpoint, headers=self._headers(),
                                timeout=eff_timeout)
        except requests.RequestException as e:
            raise LLMError(self._format_error(e)) from e
        try:
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            resp.encoding = "utf-8"
            data = resp.json()
        except ValueError as e:
            raise LLMError(f"模型列表不是合法 JSON（{self.models_endpoint}）") from e
        finally:
            resp.close()
        items = data.get("data") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise LLMError("模型列表结构异常：缺少 data 数组")
        out: List[str] = []
        for it in items:
            if isinstance(it, dict):
                mid = it.get("id")
                if isinstance(mid, str) and mid:
                    out.append(mid)
            elif isinstance(it, str):
                out.append(it)
        return out

    def probe_models(self, timeout: Optional[int] = None) -> ProbeResult:
        """探测模型端点并计时，不抛异常——失败信息装进 ProbeResult。

        给「批量检测哪个网关可用/多快」的场景用；单次失败不该中断整批。
        """
        eff_timeout = timeout if timeout is not None else 30
        t0 = time.perf_counter()
        try:
            models = self.list_models(timeout=eff_timeout)
        except LLMError as e:
            return ProbeResult(ok=False, url=self.models_endpoint,
                               elapsed_ms=(time.perf_counter() - t0) * 1000,
                               detail=str(e).splitlines()[0])
        return ProbeResult(ok=True, url=self.models_endpoint, status=200,
                           elapsed_ms=(time.perf_counter() - t0) * 1000,
                           detail="OK", models=models)

    def probe_chat(self, timeout: Optional[int] = None) -> ProbeResult:
        """探测 chat 端点并计时，不抛异常。"""
        eff_timeout = timeout if timeout is not None else 30
        t0 = time.perf_counter()
        try:
            reply = self.complete("只回复：ok", timeout=eff_timeout, retries=0)
        except LLMError as e:
            return ProbeResult(ok=False, url=self.endpoint,
                               elapsed_ms=(time.perf_counter() - t0) * 1000,
                               detail=str(e).splitlines()[0])
        return ProbeResult(ok=True, url=self.endpoint, status=200,
                           elapsed_ms=(time.perf_counter() - t0) * 1000,
                           detail=reply.strip()[:60] or "OK")

    def probe(self, timeout: Optional[int] = None) -> ProbeResult:
        """完整探测：先试模型列表，不通再退回 chat 探活。"""
        r = self.probe_models(timeout=timeout)
        if r.ok:
            return r
        return self.probe_chat(timeout=timeout)
