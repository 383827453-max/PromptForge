"""增强任务工作线程：后台调用 LLM，流式增量通过信号回传。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..enhancer import Enhancer, EnhanceResult


class EnhanceWorker(QThread):
    sig_delta = Signal(str)
    sig_done = Signal(object)   # EnhanceResult
    sig_error = Signal(str)

    def __init__(self, enhancer: Enhancer, strategy: str, original: str,
                 extra: str, stream: bool, parent=None) -> None:
        super().__init__(parent)
        self.enhancer = enhancer
        self.strategy = strategy
        self.original = original
        self.extra = extra
        self.stream = stream

    def run(self) -> None:
        try:
            if self.stream:
                result = self.enhancer.enhance_stream(
                    self.strategy, self.original, self.extra,
                    on_delta=lambda c: self.sig_delta.emit(c),
                )
            else:
                result = self.enhancer.enhance(self.strategy, self.original, self.extra)
            self.sig_done.emit(result)
        except Exception as e:  # noqa: BLE001
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