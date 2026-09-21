"""主窗口：增强工作台 / 历史记录 / 模板库 / 设置。"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import ApiConfig, Settings, load_settings, mask_key, save_settings
from ..database import Database
from ..enhancer import STRATEGIES, Enhancer, strategy_label
from ..llm_client import LLMClient, LLMError, build_endpoint
from ..templates import Template, add_user_template, delete_user_template, load_all
from .compare_tab import CompareTab
from .dialogs import TemplateEditDialog, TemplateFillDialog
from .workers import EnhanceWorker, TestWorker

# 标签页索引：避免在代码里散落魔法数字
TAB_MAIN = 0
TAB_COMPARE = 1
TAB_HISTORY = 2
TAB_TEMPLATES = 3
TAB_SETTINGS = 4


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PromptForge 提示词工坊")
        self.resize(1080, 720)
        self.settings: Settings = load_settings()
        self.db = Database()
        self.worker: Optional[EnhanceWorker] = None
        self._test_worker: Optional[TestWorker] = None
        self._stream_buf: List[str] = []
        self._current_hist_id: Optional[int] = None

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._build_main_tab(), "一键增强")
        self.compare_tab = CompareTab(
            settings_provider=lambda: self.settings,
            save_history=self._save_compare_history,
            input_provider=lambda: self.input_edit.toPlainText(),
        )
        self.tabs.addTab(self.compare_tab, "多模型对比")
        self.tabs.addTab(self._build_history_tab(), "历史记录")
        self.tabs.addTab(self._build_templates_tab(), "模板库")
        self.tabs.addTab(self._build_settings_tab(), "设置")

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._refresh_status_profile()
        self._apply_hotkey()

    # ---------------- 一键增强 ----------------
    def _build_main_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        top = QHBoxLayout()
        title = QLabel("PromptForge 提示词工坊")
        title.setObjectName("titleLabel")
        top.addWidget(title)
        top.addStretch(1)
        self.strategy_combo = QComboBox()
        for s in STRATEGIES:
            self.strategy_combo.addItem(f"策略：{s['label']}", s["key"])
        self.strategy_combo.setMinimumWidth(130)
        top.addWidget(self.strategy_combo)
        self.paste_btn = QPushButton("从剪贴板粘贴")
        self.paste_btn.clicked.connect(self._paste_from_clipboard)
        top.addWidget(self.paste_btn)
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("原始提示词"))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("在此输入或粘贴你的原始提示词，例如：\n帮我写一个爬虫抓取网页标题")
        ll.addWidget(self.input_edit, 1)
        ll.addWidget(QLabel("附加要求（可选，如：目标模型、输出语言、风格偏好）"))
        self.extra_edit = QPlainTextEdit()
        self.extra_edit.setPlaceholderText("例如：输出为英文；面向 GPT-4o 优化")
        self.extra_edit.setFixedHeight(64)
        ll.addWidget(self.extra_edit)
        btn_row = QHBoxLayout()
        self.enhance_btn = QPushButton("一键增强")
        self.enhance_btn.setObjectName("primaryBtn")
        self.enhance_btn.clicked.connect(self.on_enhance)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(lambda: (self.input_edit.clear(), self.extra_edit.clear()))
        btn_row.addWidget(self.enhance_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        self.char_label = QLabel("0 字")
        self.char_label.setObjectName("hintLabel")
        btn_row.addWidget(self.char_label)
        ll.addLayout(btn_row)
        self.input_edit.textChanged.connect(
            lambda: self.char_label.setText(f"{len(self.input_edit.toPlainText())} 字"))
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        rl_head_label = QLabel("增强结果")
        head.addWidget(rl_head_label)
        head.addStretch(1)
        self.compare_cb = QCheckBox("对比视图")
        self.compare_cb.toggled.connect(self._toggle_compare)
        head.addWidget(self.compare_cb)
        self.copy_btn = QPushButton("复制结果")
        self.copy_btn.clicked.connect(self._copy_enhanced)
        self.copy_btn.setEnabled(False)
        head.addWidget(self.copy_btn)
        self.re_btn = QPushButton("再次增强")
        self.re_btn.clicked.connect(self._re_enhance)
        self.re_btn.setEnabled(False)
        head.addWidget(self.re_btn)
        rl.addLayout(head)

        self.compare_view = QTextEdit()
        self.compare_view.setReadOnly(True)
        self.compare_view.setVisible(False)
        rl.addWidget(self.compare_view)

        rl.addWidget(QLabel("增强后提示词"))
        self.result_edit = QPlainTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("增强结果将显示在这里")
        rl.addWidget(self.result_edit, 3)
        rl.addWidget(QLabel("增强点说明"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setReadOnly(True)
        self.notes_edit.setFixedHeight(110)
        rl.addWidget(self.notes_edit, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([480, 560])
        root.addWidget(splitter, 1)
        return w

    # ---------------- 历史记录 ----------------
    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.hist_search = QLineEdit()
        self.hist_search.setPlaceholderText("搜索历史记录…")
        self.hist_search.returnPressed.connect(self.refresh_history)
        bar.addWidget(self.hist_search, 1)
        self.hist_strategy = QComboBox()
        self.hist_strategy.addItem("全部策略", "")
        for s in STRATEGIES:
            self.hist_strategy.addItem(s["label"], s["key"])
        self.hist_strategy.currentIndexChanged.connect(self.refresh_history)
        bar.addWidget(self.hist_strategy)
        self.hist_fav_cb = QCheckBox("仅收藏")
        self.hist_fav_cb.toggled.connect(self.refresh_history)
        bar.addWidget(self.hist_fav_cb)
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.refresh_history)
        bar.addWidget(search_btn)
        clear_btn = QPushButton("清空全部")
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(self._clear_history)
        bar.addWidget(clear_btn)
        lay.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        self.hist_list = QListWidget()
        self.hist_list.currentItemChanged.connect(self._show_history_detail)
        splitter.addWidget(self.hist_list)

        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(0, 0, 0, 0)
        dbar = QHBoxLayout()
        self.fav_btn = QPushButton("收藏")
        self.fav_btn.clicked.connect(self._toggle_fav)
        dbar.addWidget(self.fav_btn)
        copy_orig = QPushButton("复制原文")
        copy_orig.clicked.connect(lambda: self._copy_text(self.hist_detail_original.toPlainText()))
        dbar.addWidget(copy_orig)
        copy_enh = QPushButton("复制增强版")
        copy_enh.clicked.connect(lambda: self._copy_text(self.hist_detail_enhanced.toPlainText()))
        dbar.addWidget(copy_enh)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(self._delete_history)
        dbar.addWidget(del_btn)
        dbar.addStretch(1)
        dl.addLayout(dbar)
        dl.addWidget(QLabel("原始提示词"))
        self.hist_detail_original = QPlainTextEdit()
        self.hist_detail_original.setReadOnly(True)
        dl.addWidget(self.hist_detail_original, 1)
        dl.addWidget(QLabel("增强结果"))
        self.hist_detail_enhanced = QPlainTextEdit()
        self.hist_detail_enhanced.setReadOnly(True)
        dl.addWidget(self.hist_detail_enhanced, 2)
        splitter.addWidget(detail)
        splitter.setSizes([360, 640])
        lay.addWidget(splitter, 1)
        return w
    # ---------------- 模板库 ----------------
    def _build_templates_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        new_btn = QPushButton("新建模板")
        new_btn.setObjectName("primaryBtn")
        new_btn.clicked.connect(self._new_template)
        bar.addWidget(new_btn)
        self.use_tpl_btn = QPushButton("使用选中模板")
        self.use_tpl_btn.clicked.connect(self._use_template)
        bar.addWidget(self.use_tpl_btn)
        del_tpl_btn = QPushButton("删除选中（仅自定义）")
        del_tpl_btn.setObjectName("dangerBtn")
        del_tpl_btn.clicked.connect(self._delete_template)
        bar.addWidget(del_tpl_btn)
        bar.addStretch(1)
        lay.addLayout(bar)
        hint = QLabel("提示：双击模板直接使用；{{变量}} 会在使用时弹窗填充；内置模板不可删除。")
        hint.setObjectName("hintLabel")
        lay.addWidget(hint)
        self.tpl_list = QListWidget()
        self.tpl_list.itemDoubleClicked.connect(lambda _: self._use_template())
        lay.addWidget(self.tpl_list, 1)
        self.refresh_templates()
        return w

    # ---------------- 设置 ----------------
    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        api_box = QGroupBox("API 配置（OpenAI 兼容接口，可对接自建网关）")
        al = QVBoxLayout(api_box)
        row0 = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(220)
        row0.addWidget(self.profile_combo)
        add_p = QPushButton("新增")
        add_p.clicked.connect(self._add_profile)
        del_p = QPushButton("删除")
        del_p.clicked.connect(self._del_profile)
        row0.addWidget(add_p)
        row0.addWidget(del_p)
        row0.addStretch(1)
        al.addLayout(row0)
        form = QFormLayout()
        self.cfg_name = QLineEdit()
        self.cfg_base = QLineEdit()
        self.cfg_base.setPlaceholderText("如 http://127.0.0.1:8080/v1 或 https://api.openai.com")
        self.cfg_key = QLineEdit()
        self.cfg_key.setEchoMode(QLineEdit.Password)
        self.cfg_model = QLineEdit()
        self.cfg_model.setPlaceholderText("如 gpt-4o / deepseek-chat / 网关模型名")
        form.addRow("配置名称", self.cfg_name)
        form.addRow("Base URL", self.cfg_base)
        self.url_preview = QLabel("")
        self.url_preview.setObjectName("hintLabel")
        self.url_preview.setWordWrap(True)
        self.cfg_base.textChanged.connect(self._update_url_preview)
        form.addRow("", self.url_preview)
        form.addRow("API Key", self.cfg_key)
        form.addRow("模型", self.cfg_model)
        al.addLayout(form)
        lay.addWidget(api_box)

        opt_box = QGroupBox("生成参数")
        of = QFormLayout(opt_box)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 9999)
        self.timeout_spin.setSuffix(" 秒")
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.maxtok_spin = QSpinBox()
        self.maxtok_spin.setRange(0, 32768)
        self.maxtok_spin.setSpecialValueText("不限制")
        self.stream_cb = QCheckBox("启用流式输出（网关不支持时关闭）")
        self.copyauto_cb = QCheckBox("增强完成后自动复制到剪贴板")
        of.addRow("请求超时", self.timeout_spin)
        of.addRow("Temperature", self.temp_spin)
        of.addRow("Max Tokens", self.maxtok_spin)
        of.addRow("", self.stream_cb)
        of.addRow("", self.copyauto_cb)
        lay.addWidget(opt_box)

        ui_box = QGroupBox("界面与快捷键")
        uf = QFormLayout(ui_box)
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("如 Ctrl+Alt+P（窗口激活时跳转输入框）")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.addItem("浅色", "light")
        uf.addRow("快捷键", self.hotkey_edit)
        uf.addRow("主题", self.theme_combo)
        lay.addWidget(ui_box)

        save_row = QHBoxLayout()
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save_settings)
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_connection)
        save_row.addWidget(save_btn)
        save_row.addWidget(test_btn)
        save_row.addStretch(1)
        lay.addLayout(save_row)
        lay.addStretch(1)

        self._load_settings_ui()
        self.profile_combo.currentIndexChanged.connect(self._load_profile_ui)
        return w
    # ---------------- 行为 ----------------
    def _apply_hotkey(self) -> None:
        """重新绑定快捷键。

        QShortcut 是 QObject，必须持有引用；旧实现每次都新建一个且不回收，
        每保存一次设置就多注册一个同键快捷键，最终触发 N 次。
        这里先销毁旧实例再建新的。
        """
        old = getattr(self, "_hotkey_sc", None)
        if old is not None:
            old.setEnabled(False)
            old.setParent(None)
            old.deleteLater()
            self._hotkey_sc = None
        seq = QKeySequence(self.settings.hotkey)
        if not seq.isEmpty():
            self._hotkey_sc = QShortcut(seq, self)
            self._hotkey_sc.activated.connect(self._focus_input)

    def _focus_input(self) -> None:
        self.tabs.setCurrentIndex(TAB_MAIN)
        self.input_edit.setFocus()

    def _paste_from_clipboard(self) -> None:
        from PySide6.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        if text:
            self.input_edit.setPlainText(text)

    def _copy_text(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self.status.showMessage("已复制到剪贴板", 2000)

    def _copy_enhanced(self) -> None:
        self._copy_text(self.result_edit.toPlainText())

    def _build_client(self) -> LLMClient:
        cfg = self.settings.active()
        if cfg is None or not cfg.is_valid():
            raise LLMError("请先在「设置」页配置 Base URL 与模型")
        return LLMClient(cfg, timeout=self.settings.timeout,
                         temperature=self.settings.temperature,
                         max_tokens=self.settings.max_tokens)

    def on_enhance(self) -> None:
        original = self.input_edit.toPlainText().strip()
        if not original:
            QMessageBox.warning(self, "提示", "请先输入原始提示词")
            return
        try:
            client = self._build_client()
        except LLMError as e:
            QMessageBox.warning(self, "配置错误", str(e))
            self.tabs.setCurrentIndex(TAB_SETTINGS)
            return
        strategy = self.strategy_combo.currentData()
        extra = self.extra_edit.toPlainText().strip()
        enhancer = Enhancer(client, use_stream=self.settings.use_stream)
        self._stream_buf = []
        self.result_edit.clear()
        self.notes_edit.clear()
        self.compare_view.clear()
        self.copy_btn.setEnabled(False)
        self.re_btn.setEnabled(False)
        self.enhance_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status.showMessage("正在增强…")
        self.worker = EnhanceWorker(enhancer, strategy, original, extra,
                                    self.settings.use_stream, parent=self)
        self.worker.sig_delta.connect(self._on_delta)
        self.worker.sig_done.connect(lambda r: self._on_done(r, strategy, original))
        self.worker.sig_error.connect(self._on_error)
        self.worker.sig_cancelled.connect(self._on_cancelled)
        self.worker.start()

    def on_cancel(self) -> None:
        """取消：协作式请求停止，不调用 terminate() 强杀线程。"""
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.cancel_btn.setEnabled(False)
            self.status.showMessage("正在取消…", 2000)

    def _on_cancelled(self) -> None:
        self._set_running(False)
        self.status.showMessage("已取消", 3000)

    def _on_delta(self, chunk: str) -> None:
        self._stream_buf.append(chunk)
        self.result_edit.setPlainText("".join(self._stream_buf))

    def _on_done(self, result, strategy: str, original: str) -> None:
        self._set_running(False)
        self.result_edit.setPlainText(result.enhanced)
        self.notes_edit.setPlainText(result.notes)
        self._render_compare(original, result.enhanced)
        self.copy_btn.setEnabled(True)
        self.re_btn.setEnabled(True)
        self.db.add(strategy, original, result.enhanced, result.notes)
        self.refresh_history()
        self.status.showMessage("增强完成", 3000)
        if self.settings.copy_on_enhance:
            self._copy_enhanced()

    def _on_error(self, msg: str) -> None:
        self._set_running(False)
        self.status.showMessage("增强失败", 3000)
        QMessageBox.critical(self, "增强失败",
                             f"{msg}\n\n请检查 Base URL / API Key / 模型名，或到设置页点击「测试连接」。")

    def _set_running(self, running: bool) -> None:
        self.enhance_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)

    def _re_enhance(self) -> None:
        cur = self.result_edit.toPlainText().strip()
        if cur:
            self.input_edit.setPlainText(cur)
            self.on_enhance()

    def _toggle_compare(self, checked: bool) -> None:
        self.compare_view.setVisible(checked)

    def _render_compare(self, original: str, enhanced: str) -> None:
        import html
        self.compare_view.setHtml(
            "<table width='100%' cellspacing='8'><tr>"
            "<th align='left'>原始提示词</th><th align='left'>增强后</th></tr>"
            "<tr><td valign='top' style='white-space:pre-wrap;'>"
            + html.escape(original)
            + "</td><td valign='top' style='white-space:pre-wrap;'>"
            + html.escape(enhanced) + "</td></tr></table>")
    # ---------------- 历史 ----------------
    def refresh_history(self) -> None:
        items = self.db.list(
            keyword=self.hist_search.text().strip(),
            strategy=self.hist_strategy.currentData() or "",
            only_favorite=self.hist_fav_cb.isChecked(),
        )
        self.hist_list.clear()
        for it in items:
            preview = it.original.replace("\n", " ")[:40]
            star = "★ " if it.favorite else ""
            text = f"{star}[{strategy_label(it.strategy)}] {it.time_str}  {preview}"
            qit = QListWidgetItem(text)
            qit.setData(Qt.UserRole, it.id)
            self.hist_list.addItem(qit)

    def _show_history_detail(self, current: QListWidgetItem, _prev) -> None:
        if current is None:
            return
        item = self.db.get(current.data(Qt.UserRole))
        if item is None:
            return
        self._current_hist_id = item.id
        self.hist_detail_original.setPlainText(item.original)
        self.hist_detail_enhanced.setPlainText(item.enhanced)
        self.fav_btn.setText("取消收藏" if item.favorite else "收藏")

    def _toggle_fav(self) -> None:
        if self._current_hist_id is None:
            return
        item = self.db.get(self._current_hist_id)
        if item:
            self.db.set_favorite(item.id, not item.favorite)
            self.refresh_history()

    def _delete_history(self) -> None:
        if self._current_hist_id is None:
            return
        self.db.delete(self._current_hist_id)
        self._current_hist_id = None
        self.hist_detail_original.clear()
        self.hist_detail_enhanced.clear()
        self.refresh_history()

    def _clear_history(self) -> None:
        if QMessageBox.question(self, "确认", "确定清空全部历史记录？") == QMessageBox.Yes:
            self.db.clear()
            self.refresh_history()

    # ---------------- 模板 ----------------
    def refresh_templates(self) -> None:
        self.tpl_list.clear()
        for t in load_all():
            tag = "内置" if t.builtin else "自定义"
            qit = QListWidgetItem(f"[{tag}][{t.category}] {t.name}")
            qit.setData(Qt.UserRole, (t.builtin, t.name))
            self.tpl_list.addItem(qit)

    def _selected_template(self) -> Optional[Template]:
        qit = self.tpl_list.currentItem()
        if qit is None:
            return None
        builtin, name = qit.data(Qt.UserRole)
        for t in load_all():
            if t.builtin == builtin and t.name == name:
                return t
        return None

    def _use_template(self) -> None:
        t = self._selected_template()
        if t is None:
            QMessageBox.information(self, "提示", "请先选择一个模板")
            return
        content = t.content
        if t.variables():
            dlg = TemplateFillDialog(t, self)
            if dlg.exec() != TemplateFillDialog.Accepted:
                return
            content = t.fill(dlg.values())
        self.input_edit.setPlainText(content)
        idx = self.strategy_combo.findData(t.strategy)
        if idx >= 0:
            self.strategy_combo.setCurrentIndex(idx)
        self.tabs.setCurrentIndex(TAB_MAIN)

    def _new_template(self) -> None:
        dlg = TemplateEditDialog(self)
        if dlg.exec() == TemplateEditDialog.Accepted:
            add_user_template(dlg.template())
            self.refresh_templates()

    def _delete_template(self) -> None:
        t = self._selected_template()
        if t is None:
            return
        if t.builtin:
            QMessageBox.information(self, "提示", "内置模板不可删除")
            return
        delete_user_template(t.name)
        self.refresh_templates()
    # ---------------- 设置 ----------------
    def _load_settings_ui(self) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in self.settings.profiles:
            self.profile_combo.addItem(p.name or "未命名")
        self.profile_combo.setCurrentIndex(self.settings.active_profile)
        self.profile_combo.blockSignals(False)
        self._load_profile_ui(self.profile_combo.currentIndex())
        self.timeout_spin.setValue(self.settings.timeout)
        self.temp_spin.setValue(self.settings.temperature)
        self.maxtok_spin.setValue(self.settings.max_tokens)
        self.stream_cb.setChecked(self.settings.use_stream)
        self.copyauto_cb.setChecked(self.settings.copy_on_enhance)
        self.hotkey_edit.setText(self.settings.hotkey)
        idx = self.theme_combo.findData(self.settings.theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

    def _update_url_preview(self, text: str) -> None:
        t = text.strip()
        if not t:
            self.url_preview.setText("")
            return
        if not t.startswith(("http://", "https://")):
            self.url_preview.setText("⚠ Base URL 需以 http:// 或 https:// 开头")
            return
        self.url_preview.setText("实际请求地址：" + build_endpoint(t))

    def _load_profile_ui(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.settings.profiles):
            return
        p = self.settings.profiles[idx]
        self.cfg_name.setText(p.name)
        self.cfg_base.setText(p.base_url)
        self.cfg_key.setText(p.api_key)
        self.cfg_model.setText(p.model)

    def _collect_profile_ui(self) -> None:
        idx = self.profile_combo.currentIndex()
        if 0 <= idx < len(self.settings.profiles):
            p = self.settings.profiles[idx]
            p.name = self.cfg_name.text().strip() or f"配置{idx + 1}"
            p.base_url = self.cfg_base.text().strip()
            p.api_key = self.cfg_key.text().strip()
            p.model = self.cfg_model.text().strip()
            self.profile_combo.setItemText(idx, p.name)

    def _add_profile(self) -> None:
        self._collect_profile_ui()
        self.settings.profiles.append(ApiConfig(name=f"配置{len(self.settings.profiles) + 1}"))
        self.settings.active_profile = len(self.settings.profiles) - 1
        self._load_settings_ui()
        self.compare_tab.refresh_profiles()

    def _del_profile(self) -> None:
        if len(self.settings.profiles) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个配置")
            return
        idx = self.profile_combo.currentIndex()
        self.settings.profiles.pop(idx)
        self.settings.active_profile = max(0, idx - 1)
        self._load_settings_ui()
        self.compare_tab.refresh_profiles()

    def _save_settings(self) -> None:
        self._collect_profile_ui()
        self.settings.active_profile = self.profile_combo.currentIndex()
        self.settings.timeout = self.timeout_spin.value()
        self.settings.temperature = self.temp_spin.value()
        self.settings.max_tokens = self.maxtok_spin.value()
        self.settings.use_stream = self.stream_cb.isChecked()
        self.settings.copy_on_enhance = self.copyauto_cb.isChecked()
        self.settings.hotkey = self.hotkey_edit.text().strip() or "Ctrl+Alt+P"
        self.settings.theme = self.theme_combo.currentData()
        save_settings(self.settings)
        from ..app import apply_current_theme
        apply_current_theme(self.settings.theme)
        self._apply_hotkey()
        self._refresh_status_profile()
        # 配置可能改了名称/地址，对比面板的勾选列表要同步
        self.compare_tab.refresh_profiles()
        self.status.showMessage("设置已保存", 2000)

    def _save_compare_history(self, strategy: str, original: str,
                              enhanced: str, notes: str) -> None:
        """对比面板选中的结果写入历史库。"""
        self.db.add(strategy, original, enhanced, notes)
        self.refresh_history()

    def _test_connection(self) -> None:
        self._collect_profile_ui()
        idx = self.profile_combo.currentIndex()
        if idx >= 0:
            self.settings.active_profile = idx
        try:
            client = self._build_client()
        except LLMError as e:
            QMessageBox.warning(self, "配置错误", str(e))
            return
        self._test_worker = TestWorker(client, self)
        self._test_worker.sig_ok.connect(self._on_test_ok)
        self._test_worker.sig_error.connect(self._on_test_error)
        self.status.showMessage("正在测试连接…（后台进行，界面不会卡顿）")
        self._test_worker.start()

    def _on_test_ok(self, reply: str) -> None:
        self.status.showMessage("连接成功", 5000)
        QMessageBox.information(self, "连接成功", f"模型返回：{reply}")

    def _on_test_error(self, msg: str) -> None:
        self.status.showMessage("连接失败", 5000)
        QMessageBox.critical(self, "连接失败", msg)

    def _refresh_status_profile(self) -> None:
        cfg = self.settings.active()
        if cfg and cfg.is_valid():
            key_info = mask_key(cfg.api_key) if cfg.api_key else "未设置Key"
            self.status.showMessage(
                f"当前配置：{cfg.name} | {cfg.base_url} | 模型：{cfg.model} | Key：{key_info}")
        else:
            self.status.showMessage("尚未配置 API，请到「设置」页填写 Base URL 与模型")

    def closeEvent(self, event) -> None:
        """退出：先请线程收尾，超时未退再兜底强杀。

        直接 terminate() 会让线程在 requests 读写 socket 的任意位置被打断，
        底层连接不会关闭。这里先协作式取消并给足收尾时间，只有线程确实
        卡死（例如网关已僵死）才退化为 terminate()。
        """
        w = self.worker
        if w is not None and w.isRunning():
            w.request_stop()
            if not w.wait(3000):
                w.terminate()
                w.wait(1000)
        t = self._test_worker
        if t is not None and t.isRunning():
            t.wait(1500)
        self.compare_tab.stop()
        self.db.close()
        event.accept()
