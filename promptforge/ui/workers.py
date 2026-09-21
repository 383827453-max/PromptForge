"""增强任务工作线程：后台调用 LLM，流式增量通过信号回传。

取消采用协作式：外部调用 `request_stop()`，线程在 SSE 块之间检查到
取消标志后自行收尾退出。不再使用 QThread.terminate()——强杀线程会让
requests 持有的连接与底层资源无法释放，并可能让 Qt 停在半初始化状态，
表现为随机崩溃或句柄泄漏。
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from ..enhancer import Enhancer


class EnhanceWorker(QThread):
    sig_delta = Signal(str)
    sig_done = Signal(object)   # EnhanceResult
    sig_error = Signal(str)
    sig_cancelled = Signal()

    def __init__(self, enhancer: Enhancer, strategy: str, original: str,
                 extra: str, stream: bool, parent=None) -> None:
        super().__init__(parent)
        self.enhancer = enhancer
        self.strategy = strategy
        self.original = original
        self.extra = extra
        self.stream = stream
        self._stop = threading.Event()

    def request_stop(self) -> None:
        """请求取消：线程会在下一个 SSE 块边界干净退出。"""
        self._stop.set()

    def is_stop_requested(self) -> bool:
        return self._stop.is_set()

    def run(self) -> None:
        try:
            if self.stream:
                result = self.enhancer.enhance_stream(
                    self.strategy, self.original, self.extra,
                    on_delta=lambda c: self.sig_delta.emit(c),
                    should_stop=self._stop.is_set,
                )
            else:
                result = self.enhancer.enhance(self.strategy, self.original, self.extra)
            if self._stop.is_set():
                self.sig_cancelled.emit()
                return
            self.sig_done.emit(result)
        except Exception as e:  # noqa: BLE001
            if self._stop.is_set():
                self.sig_cancelled.emit()
                return
            self.sig_error.emit(str(e))


class TestWorker(QThread):
    """测试连接工作线程：避免 UI 线程阻塞导致的界面卡死。"""
    sig_ok = Signal(str)
    sig_error = Signal(str)

    def __init__(self, client, parent=None) -> None:
        super().__init__(parent)
        self.client = client

    def run(self) -> None:
        try:
            reply = self.client.ping()
            self.sig_ok.emit(reply.strip()[:80])
        except Exception as e:  # noqa: BLE001
            self.sig_error.emit(str(e))
