"""多模型并发对比：同一提示词广播到多个 API 配置，收集结果与耗时。

与 GUI 解耦（只用 threading + 回调），便于单测，也便于将来在 CLI
或批处理里复用。

设计要点：
- 每个配置一个线程，互不阻塞；单个失败不影响其他结果。
- 协作式取消：所有线程共享一个 stop 谓词，点取消后各线程在流式块边界退出。
- 首字延迟（TTFT）与总耗时分开记录：网关慢在首字还是慢在生成，是两类问题。
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from .enhancer import Enhancer
from .llm_client import LLMClient, LLMError

# 行首列表标记：`- ` `* ` `• ` 或 `1.` `1)` `1、` `1）`（空格可有可无）
_BULLET_RE = re.compile(r"^(?:[-*•]\s+|\d+\s*[.)、）]\s*)")


@dataclass
class CompareResult:
    """单个配置的一次对比结果。"""

    profile_name: str
    model: str
    base_url: str
    ok: bool
    enhanced: str = ""
    notes: str = ""
    error: str = ""
    elapsed_ms: float = 0.0
    ttft_ms: Optional[float] = None      # 首字延迟，非流式为 None
    chars: int = 0
    cancelled: bool = False

    def summary(self) -> str:
        if self.cancelled:
            return "已取消"
        if not self.ok:
            return f"失败：{self.error}"
        parts = [f"{self.elapsed_ms:.0f}ms"]
        if self.ttft_ms is not None:
            parts.append(f"首字 {self.ttft_ms:.0f}ms")
        parts.append(f"{self.chars} 字")
        return " · ".join(parts)


def _run_one(client: LLMClient, strategy: str, original: str, extra: str,
             use_stream: bool, profile_name: str, index: int,
             should_stop: Optional[Callable[[], bool]],
             on_delta: Optional[Callable[[int, str], None]],
             out: List[Optional[CompareResult]]) -> None:
    """执行单个配置的增强，结果写入 out[index]。"""
    t0 = time.perf_counter()
    ttft: Optional[float] = None
    buf: List[str] = []

    def _delta(chunk: str) -> None:
        nonlocal ttft
        if ttft is None:
            ttft = (time.perf_counter() - t0) * 1000
        if on_delta is not None:
            on_delta(index, chunk)
        buf.append(chunk)

    enhancer = Enhancer(client, use_stream=use_stream)
    common = dict(profile_name=profile_name, model=client.model,
                  base_url=client.base_url)
    try:
        if use_stream:
            result = enhancer.enhance_stream(strategy, original, extra,
                                             on_delta=_delta,
                                             should_stop=should_stop)
            if should_stop is not None and should_stop():
                out[index] = CompareResult(ok=False, cancelled=True, **common)
                return
        else:
            result = enhancer.enhance(strategy, original, extra)
            if should_stop is not None and should_stop():
                out[index] = CompareResult(ok=False, cancelled=True, **common)
                return
        out[index] = CompareResult(
            ok=True, enhanced=result.enhanced, notes=result.notes,
            elapsed_ms=(time.perf_counter() - t0) * 1000, ttft_ms=ttft,
            chars=len(result.enhanced), **common)
    except LLMError as e:
        out[index] = CompareResult(
            ok=False, error=str(e), elapsed_ms=(time.perf_counter() - t0) * 1000,
            ttft_ms=ttft, **common)
    except Exception as e:  # noqa: BLE001
        out[index] = CompareResult(
            ok=False, error=f"{type(e).__name__}: {e}",
            elapsed_ms=(time.perf_counter() - t0) * 1000, ttft_ms=ttft, **common)


class CompareRunner:
    """把同一提示词并发发往多个配置。

    用法::

        runner = CompareRunner(strategy="general", original="写个爬虫")
        for cfg in configs:
            runner.add(cfg, "配置A")
        results = runner.run()          # 阻塞直到全部完成
        for r in results:
            print(r.profile_name, r.summary())
    """

    def __init__(self, strategy: str, original: str, extra: str = "",
                 timeout: int = 120, temperature: float = 0.7,
                 max_tokens: int = 0, use_stream: bool = True) -> None:
        self.strategy = strategy
        self.original = original
        self.extra = extra
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_stream = use_stream
        self._jobs: List[tuple] = []
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._results: List[Optional[CompareResult]] = []
        self.on_delta: Optional[Callable[[int, str], None]] = None
        self.on_result: Optional[Callable[[int, CompareResult], None]] = None

    def add(self, cfg, profile_name: str = "") -> int:
        """登记一个待对比配置，返回它的索引。"""
        idx = len(self._jobs)
        name = profile_name or getattr(cfg, "name", "") or f"配置{idx + 1}"
        self._jobs.append((cfg, name))
        self._results.append(None)
        return idx

    def request_stop(self) -> None:
        """请求取消全部在跑的任务。"""
        self._stop.set()

    def is_stop_requested(self) -> bool:
        return self._stop.is_set()

    def _make_client(self, cfg) -> LLMClient:
        return LLMClient(cfg, timeout=self.timeout,
                         temperature=self.temperature,
                         max_tokens=self.max_tokens)

    def run(self) -> List[CompareResult]:
        """并发执行，阻塞到全部完成（或被取消），返回按登记顺序排列的结果。"""
        if not self._jobs:
            return []
        self._results = [None] * len(self._jobs)

        def worker(idx: int, cfg, name: str) -> None:
            try:
                client = self._make_client(cfg)
            except Exception as e:  # noqa: BLE001
                self._results[idx] = CompareResult(
                    profile_name=name, model=getattr(cfg, "model", ""),
                    base_url=getattr(cfg, "base_url", ""), ok=False,
                    error=f"{type(e).__name__}: {e}")
            else:
                _run_one(client, self.strategy, self.original, self.extra,
                         self.use_stream, name, idx, self._stop.is_set,
                         self.on_delta, self._results)
            r = self._results[idx]
            if r is not None and self.on_result is not None:
                self.on_result(idx, r)

        self._threads = []
        for i, (cfg, name) in enumerate(self._jobs):
            t = threading.Thread(target=worker, args=(i, cfg, name),
                                 name=f"cmp-{i}", daemon=True)
            self._threads.append(t)
        for t in self._threads:
            t.start()
        for t in self._threads:
            t.join()
        return [r for r in self._results if r is not None]

    def ranked(self) -> List[CompareResult]:
        """按总耗时升序排列成功结果；失败的排在最后。"""
        results = [r for r in self._results if r is not None]
        ok = [r for r in results if r.ok and not r.cancelled]
        bad = [r for r in results if not r.ok]
        ok.sort(key=lambda r: r.elapsed_ms)
        return ok + bad


def parse_notes_bullets(notes: str) -> List[str]:
    """把增强点说明拆成条目列表，供对比面板逐行展示。

    支持的序号/符号前缀：`1.` `1)` `1、` `1）` `-` `*` `•`。
    注意「1、中文序号」这类没有空格分隔的写法：按空白切分会切不开，
    必须先用正则剥掉序号本身，而不是靠 split。
    """
    out: List[str] = []
    for raw in (notes or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = _BULLET_RE.sub("", line, count=1).strip()
        if line:
            out.append(line)
    return out


def diff_summary(results: Sequence[CompareResult]) -> Dict[str, str]:
    """给出一句话级别的对比结论，用于结果区顶部提示。"""
    total = len(results)
    ok = [r for r in results if r.ok and not r.cancelled]
    if not ok:
        return {"verdict": "全部失败", "detail": "没有一个配置返回成功结果。"}
    fastest = min(ok, key=lambda r: r.elapsed_ms)
    detail = f"最快：{fastest.profile_name}（{fastest.elapsed_ms:.0f}ms）"
    if len(ok) > 1:
        # 长度可能并列，全部列出而不是只报一个
        longest_n = max(r.chars for r in ok)
        longest = [r.profile_name for r in ok if r.chars == longest_n]
        detail += f"；最长：{'/'.join(longest)}（{longest_n} 字）"
        spread = max(r.elapsed_ms for r in ok) - min(r.elapsed_ms for r in ok)
        detail += f"；耗时差 {spread:.0f}ms"
    return {"verdict": f"{len(ok)}/{total} 成功", "detail": detail}
