"""多模型对比面板：同一提示词广播到多个 API 配置，结果并排展示。

与「一键增强」的区别：那边是选一个配置出结果，这边是把同一个提示词
同时发给多个配置，横向比较输出质量与速度，用来决定长期用哪个模型。

线程模型：`CompareRunner.run()` 是阻塞的，放进 `CompareWorker(QThread)`
执行；runner 的回调在各自的工作线程里被调用，通过 Qt 信号（跨线程自动
排队）回到 UI 线程更新界面，不直接碰控件。
"""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..compare import CompareResult, CompareRunner, diff_summary
from ..enhancer import STRATEGIES

CARD_MIN_WIDTH = 340


class CompareWorker(QThread):
    """在后台跑一轮并发对比。"""

    sig_result = Signal(int, object)      # 索引, CompareResult
    sig_delta = Signal(int, str)          # 索引, 增量文本
    sig_finished = Signal(object)         # List[CompareResult]
    sig_error = Signal(str)

    def __init__(self, runner: CompareRunner, parent=None) -> None:
        super().__init__(parent)
        self.runner = runner
        runner.on_result = lambda i, r: self.sig_result.emit(i, r)
        runner.on_delta = lambda i, c: self.sig_delta.emit(i, c)

    def request_stop(self) -> None:
        self.runner.request_stop()

    def run(self) -> None:
        try:
            results = self.runner.run()
            self.sig_finished.emit(results)
        except Exception as e:  # noqa: BLE001
            self.sig_error.emit(f"{type(e).__name__}: {e}")


class ResultCard(QGroupBox):
    """单个配置的结果卡片。"""

    def __init__(self, title: str, subtitle: str, parent=None) -> None:
        super().__init__(title, parent)
        self.setMinimumWidth(CARD_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        lay = QVBoxLayout(self)

        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("hintLabel")
        self.subtitle.setWordWrap(True)
        lay.addWidget(self.subtitle)

        self.status = QLabel("等待中…")
        self.status.setObjectName("hintLabel")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("结果将显示在这里")
        lay.addWidget(self.text, 1)

        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setFixedHeight(88)
        self.notes.setVisible(False)
        self.notes.setPlaceholderText("增强点说明")
        lay.addWidget(self.notes)

        row = QHBoxLayout()
        self.copy_btn = QPushButton("复制")
        self.copy_btn.setEnabled(False)
        row.addWidget(self.copy_btn)
        self.save_btn = QPushButton("存入历史")
        self.save_btn.setEnabled(False)
        row.addWidget(self.save_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.result: Optional[CompareResult] = None

    def set_running(self) -> None:
        self.status.setText("请求中…")

    def set_streaming(self, length: int) -> None:
        self.status.setText(f"接收中… 已 {length} 字")

    def apply(self, r: CompareResult) -> None:
        self.result = r
        if r.cancelled:
            self.status.setText("已取消")
            return
        if not r.ok:
            self.status.setText(f"失败：{r.error.splitlines()[0] if r.error else '未知错误'}")
            self.status.setToolTip(r.error)
            return
        self.status.setText(r.summary())
        self.status.setToolTip(r.error or r.summary())
        self.text.setPlainText(r.enhanced)
        if r.notes:
            self.notes.setPlainText(r.notes)
        self.copy_btn.setEnabled(True)
        self.save_btn.setEnabled(True)


class CompareTab(QWidget):
    """对比面板。

    settings_provider / save_history 由宿主注入，避免直接依赖 MainWindow，
    便于单测时传假实现。
    """

    def __init__(self,
                 settings_provider: Callable[[], object],
                 save_history: Callable[[str, str, str, str], None],
                 input_provider: Optional[Callable[[], str]] = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._get_settings = settings_provider
        self._save_history = save_history
        self._get_main_input = input_provider
        self.worker: Optional[CompareWorker] = None
        self._cards: List[ResultCard] = []
        self._strategy = "general"
        self._original = ""
        self._build()

    # ---------- 构建 ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        title = QLabel("多模型对比")
        title.setObjectName("titleLabel")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(QLabel("策略："))
        self.strategy_combo = QComboBox()
        for s in STRATEGIES:
            self.strategy_combo.addItem(s["label"], s["key"])
        self.strategy_combo.setMinimumWidth(110)
        top.addWidget(self.strategy_combo)
        root.addLayout(top)

        pick = QGroupBox("参与对比的配置（勾选 2 个以上）")
        pl = QVBoxLayout(pick)
        prow = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_btn = QPushButton("全不选")
        self.select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        prow.addWidget(self.select_all_btn)
        prow.addWidget(self.select_none_btn)
        prow.addStretch(1)
        self.show_notes_cb = QCheckBox("显示增强点说明")
        self.show_notes_cb.toggled.connect(self._toggle_notes)
        prow.addWidget(self.show_notes_cb)
        pl.addLayout(prow)
        self.profile_box = QVBoxLayout()
        pl.addLayout(self.profile_box)
        root.addWidget(pick)

        root.addWidget(QLabel("原始提示词"))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("输入要对比的提示词，例如：帮我写一个爬虫抓取网页标题")
        self.input_edit.setFixedHeight(96)
        root.addWidget(self.input_edit)

        row = QHBoxLayout()
        self.sync_btn = QPushButton("取「一键增强」的输入")
        self.sync_btn.clicked.connect(self._sync_input)
        row.addWidget(self.sync_btn)
        self.run_btn = QPushButton("并发对比")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.clicked.connect(self.start)
        row.addWidget(self.run_btn)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("hintLabel")
        row.addWidget(self.summary_label)
        root.addLayout(row)

        self.cards_host = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.cards_host)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        root.addWidget(scroll, 1)

        self.refresh_profiles()

    # ---------- 配置列表 ----------

    def _profile_widgets(self) -> List[QCheckBox]:
        out = []
        for i in range(self.profile_box.count()):
            w = self.profile_box.itemAt(i).widget()
            if isinstance(w, QCheckBox):
                out.append(w)
        return out

    def refresh_profiles(self) -> None:
        """按当前配置档案重建勾选列表。"""
        while self.profile_box.count():
            item = self.profile_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        settings = self._get_settings()
        profiles = list(getattr(settings, "profiles", []) or [])
        for i, p in enumerate(profiles):
            name = getattr(p, "name", "") or f"配置{i + 1}"
            model = getattr(p, "model", "") or "（未填模型）"
            base = getattr(p, "base_url", "") or "（未填地址）"
            cb = QCheckBox(f"{name} — {model}  @ {base}")
            cb.setChecked(len(profiles) <= 3 or i < 3)
            self.profile_box.addWidget(cb)

    def _set_all_checked(self, checked: bool) -> None:
        for cb in self._profile_widgets():
            cb.setChecked(checked)

    def _checked_indices(self) -> List[int]:
        return [i for i, cb in enumerate(self._profile_widgets()) if cb.isChecked()]

    def _toggle_notes(self, on: bool) -> None:
        for card in self._cards:
            card.notes.setVisible(on)

    def _sync_input(self) -> None:
        if self._get_main_input is None:
            return
        text = self._get_main_input() or ""
        if text.strip():
            self.input_edit.setPlainText(text)

    # ---------- 执行 ----------

    def _rebuild_cards(self, names: List[str], profiles: List[object]) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards = []
        for i, name in enumerate(names):
            p = profiles[i] if i < len(profiles) else None
            model = getattr(p, "model", "") if p is not None else ""
            card = ResultCard(name, model or "")
            card.copy_btn.clicked.connect(lambda _=False, c=card: self._copy_card(c))
            card.save_btn.clicked.connect(lambda _=False, c=card: self._save_card(c))
            card.notes.setVisible(self.show_notes_cb.isChecked())
            self.cards_layout.addWidget(card)
            self._cards.append(card)

    def start(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        original = self.input_edit.toPlainText().strip()
        if not original:
            QMessageBox.warning(self, "提示", "请先输入原始提示词")
            return
        settings = self._get_settings()
        profiles = list(getattr(settings, "profiles", []) or [])
        idxs = self._checked_indices()
        if len(idxs) < 2:
            QMessageBox.warning(self, "提示", "请至少勾选 2 个配置才有对比意义")
            return
        chosen = [profiles[i] for i in idxs if i < len(profiles)]
        names = [getattr(p, "name", "") or f"配置{i + 1}" for i, p in enumerate(chosen)]

        self._strategy = self.strategy_combo.currentData() or "general"
        self._original = original
        self._rebuild_cards(names, chosen)

        runner = CompareRunner(
            strategy=self._strategy,
            original=original,
            extra="",
            timeout=int(getattr(settings, "timeout", 120) or 120),
            temperature=float(getattr(settings, "temperature", 0.7) or 0.7),
            max_tokens=int(getattr(settings, "max_tokens", 0) or 0),
            use_stream=bool(getattr(settings, "use_stream", True)),
        )
        for p, name in zip(chosen, names):
            runner.add(p, name)

        self.worker = CompareWorker(runner, parent=self)
        self.worker.sig_result.connect(self._on_result)
        self.worker.sig_delta.connect(self._on_delta)
        self.worker.sig_finished.connect(self._on_finished)
        self.worker.sig_error.connect(self._on_error)
        for card in self._cards:
            card.set_running()
        self._set_running(True)
        self.summary_label.setText(f"正在并发请求 {len(names)} 个配置…")
        self.worker.start()

    def cancel(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.cancel_btn.setEnabled(False)
            self.summary_label.setText("正在取消…")

    def _set_running(self, running: bool) -> None:
        self.run_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)

    # ---------- 回调 ----------

    def _on_delta(self, index: int, chunk: str) -> None:
        if 0 <= index < len(self._cards):
            card = self._cards[index]
            card.text.insertPlainText(chunk)
            card.set_streaming(len(card.text.toPlainText()))

    def _on_result(self, index: int, result: CompareResult) -> None:
        if 0 <= index < len(self._cards):
            card = self._cards[index]
            if result.ok:
                # 流式已经逐块填过文本，这里只在有出入时整体替换
                if card.text.toPlainText() != result.enhanced:
                    card.text.setPlainText(result.enhanced)
            card.apply(result)

    def _on_finished(self, results) -> None:
        self._set_running(False)
        info = diff_summary(list(results or []))
        self.summary_label.setText(f"{info['verdict']} · {info['detail']}")
        if self.worker is not None:
            self.worker.wait(1000)

    def _on_error(self, msg: str) -> None:
        self._set_running(False)
        self.summary_label.setText("对比失败")
        QMessageBox.critical(self, "对比失败", msg)

    def _copy_card(self, card: ResultCard) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(card.text.toPlainText())

    def _save_card(self, card: ResultCard) -> None:
        r = card.result
        if r is None or not r.ok:
            return
        self._save_history(self._strategy, self._original, r.enhanced, r.notes)
        self.summary_label.setText(f"已存入历史：{r.profile_name}")

    # ---------- 生命周期 ----------

    def stop(self) -> None:
        """退出时确保线程收尾。"""
        w = self.worker
        if w is not None and w.isRunning():
            w.request_stop()
            if not w.wait(3000):
                w.terminate()
                w.wait(1000)


__all__ = ["CompareTab", "CompareWorker", "ResultCard"]
