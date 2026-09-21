"""OpenAI 兼容 API 客户端：支持流式（SSE）与非流式，超时/重试。"""
from __future__ import annotations

import json
import time
from typing import Callable, Iterator, Optional

import requests

from .config import ApiConfig


class LLMError(Exception):
    pass


def build_endpoint(base_url: str) -> str:
    """把 Base URL 归一化为完整的 chat completions 请求地址。"""
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


class LLMClient:
    """OpenAI 兼容接口的最小客户端，可对接任意自建网关。"""

    def __init__(self, cfg: ApiConfig, timeout: int = 120, temperature: float = 0.7,
                 max_tokens: int = 0, retries: int = 2) -> None:
        self.cfg = cfg
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries

    @property
    def endpoint(self) -> str:
        return build_endpoint(self.cfg.base_url)

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            # 强制服务端响应后关闭连接，避免部分网关 keep-alive 不关连接
            # 导致 requests 一直等待读取结束（表现为"返回文字后卡住一会"）
            "Connection": "close",
        }
        if self.cfg.api_key.strip():
            h["Authorization"] = f"Bearer {self.cfg.api_key.strip()}"
        return h

    def _payload(self, system_prompt: str, stream: bool) -> dict:
        p = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
            ],
            "temperature": self.temperature,
            "stream": stream,
        }
        if self.max_tokens > 0:
            p["max_tokens"] = self.max_tokens
        return p

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
                    raise LLMError(f"HTTP {resp.status_code}: {body}")
                # 强制按 UTF-8 解码：部分网关不返回 charset，requests 会退回
                # ISO-8859-1，导致中文全部变成乱码
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
        """按异常类型给出带完整请求地址的针对性诊断信息。

        注意：SSLError / ReadTimeout 等挂在 requests.exceptions 下，
        顶层 `requests.SSLError` 并不存在。早期实现直接引用顶层属性，
        导致这个"错误处理函数"本身在遇到 SSL 类故障时抛 AttributeError，
        用户看到的是 traceback 而不是诊断信息。
        """
        url = self.endpoint
        exc = requests.exceptions
        # SSLError 是 ConnectionError 的子类，必须先判
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
            return f"请求超时：{url}\n请适当加大「设置」页的请求超时时间。"
        return f"请求失败：{url}\n{e}"

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
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMError(
                f"响应结构异常: {json.dumps(data, ensure_ascii=False)[:300]}") from e

    def ping(self) -> str:
        """测试连接：短超时 + 非流式 + 不重试，快速失败。"""
        return self.complete("请只回复两个字：成功", timeout=30, retries=0)

    def stream(self, system_prompt: str, on_delta: Optional[Callable[[str], None]] = None,
               should_stop: Optional[Callable[[], bool]] = None) -> Iterator[str]:
        """流式调用，逐块 yield 增量文本。

        should_stop 提供协作式取消：传入一个"返回 True 表示用户已取消"
        的谓词，循环在每个 SSE 块之间检查并干净退出。这样取消不必依赖
        QThread.terminate()——强杀线程会让 requests 持有的 socket 悬空、
        finally 不执行，是间歇性崩溃与句柄泄漏的常见来源。
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
                # 检测到结束标记立即退出，避免网关不发 [DONE]/不关连接时挂起
                if finish:
                    break
        finally:
            # 正常结束、被取消、抛异常，都释放底层连接
            resp.close()
