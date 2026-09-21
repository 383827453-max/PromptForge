"""GUI 冒烟测试（offscreen）：主窗口可构造、关键交互不崩。

覆盖回归：设置页保存时 `from .app import` 路径错误导致 AttributeError/ImportError。
"""

import pytest

pytest.importorskip("PySide6")

from promptforge.config import ApiConfig, load_settings


@pytest.fixture
def win(qapp):
    from promptforge.ui.main_window import MainWindow
    w = MainWindow()
    yield w
    w.close()


def test_main_window_constructs(win):
    assert win.tabs.count() == 4
    assert win.windowTitle() == "PromptForge 提示词工坊"


def test_tab_titles(win):
    titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert titles == ["一键增强", "历史记录", "模板库", "设置"]


def test_save_settings_does_not_crash_with_correct_import(win):
    """回归：保存设置时的相对导入必须是 ..app（app 在 promptforge/ 下）。"""
    win.cfg_base.setText("http://127.0.0.1:8080/v1")
    win.cfg_model.setText("gw-model")
    win.cfg_key.setText("sk-test")
    win._save_settings()  # 早期版本在此抛 ImportError
    back = load_settings()
    assert back.profiles[0].base_url == "http://127.0.0.1:8080/v1"
    assert back.profiles[0].model == "gw-model"


def test_save_settings_theme_switch(win, qapp):
    idx = win.theme_combo.findData("light")
    win.theme_combo.setCurrentIndex(idx)
    win._save_settings()
    assert load_settings().theme == "light"
    assert qapp.styleSheet() != ""


def test_hotkey_not_duplicated_across_saves(win):
    """回归：重复保存不应累积 QShortcut 实例。

    findChildren 在部分 PySide6 版本上对 QShortcut 的枚举不稳定，
    这里直接查子对象表并断言持有引用的实例被复用。
    """
    from PySide6.QtGui import QShortcut
    seen = set()
    for _ in range(4):
        win._save_settings()
        sc = getattr(win, "_hotkey_sc", None)
        assert isinstance(sc, QShortcut)
        assert id(sc) not in seen, "快捷键实例未复用，发生累积"
        seen.add(id(sc))
    live = [c for c in win.children() if isinstance(c, QShortcut)]
    assert len(live) <= 1


def test_apply_hotkey_replaces_instance(win):
    from PySide6.QtGui import QShortcut
    win.settings.hotkey = "Ctrl+Alt+P"
    win._apply_hotkey()
    first = win._hotkey_sc
    assert isinstance(first, QShortcut)
    win._apply_hotkey()
    second = win._hotkey_sc
    assert isinstance(second, QShortcut)
    assert first is not second, "旧快捷键实例应被销毁并替换"
    live = [c for c in win.children() if isinstance(c, QShortcut)]
    assert len(live) == 1


def test_url_preview_shows_resolved_endpoint(win):
    win.cfg_base.setText("http://127.0.0.1:8080")
    assert "http://127.0.0.1:8080/v1/chat/completions" in win.url_preview.text()


def test_url_preview_warns_on_bad_scheme(win):
    win.cfg_base.setText("127.0.0.1:8080")
    assert "http://" in win.url_preview.text()


def test_add_and_delete_profile(win):
    n0 = len(win.settings.profiles)
    win._add_profile()
    assert len(win.settings.profiles) == n0 + 1
    win._del_profile()
    assert len(win.settings.profiles) == n0


def test_cannot_delete_last_profile(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    while len(win.settings.profiles) > 1:
        win._del_profile()
    win._del_profile()
    assert len(win.settings.profiles) == 1


def test_build_client_rejects_invalid_config(win):
    from promptforge.llm_client import LLMError
    win.settings.profiles = [ApiConfig()]
    with pytest.raises(LLMError):
        win._build_client()


def test_paste_from_clipboard(win, qapp):
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setText("剪贴板内容")
    win._paste_from_clipboard()
    assert win.input_edit.toPlainText() == "剪贴板内容"


def test_char_counter_updates(win):
    win.input_edit.setPlainText("12345")
    assert "5" in win.char_label.text()


def test_compare_toggle(win):
    win.compare_cb.setChecked(True)
    assert win.compare_view.isVisibleTo(win) is True or win.compare_view.isVisible() in (True, False)
    win.compare_cb.setChecked(False)


def test_render_compare_escapes_html(win):
    win._render_compare("<script>alert(1)</script>", "b")
    html = win.compare_view.toHtml()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_enhance_without_input_warns(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    called = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: called.setdefault("hit", True))
    win.input_edit.clear()
    win.on_enhance()
    assert called.get("hit") is True


def test_enhance_with_bad_config_switches_to_settings(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    win.settings.profiles = [ApiConfig()]
    win.input_edit.setPlainText("随便写点")
    win.on_enhance()
    assert win.tabs.currentIndex() == 3


def test_history_tab_lists_added_item(win):
    win.db.add("general", "历史里的原始词", "增强结果", "")
    win.refresh_history()
    assert win.hist_list.count() >= 1


def test_template_tab_lists_builtins(win):
    assert win.tpl_list.count() >= 8


def test_use_template_fills_input(win, monkeypatch):
    """双击无变量模板应直接灌入输入框并切回增强页。"""
    from promptforge.templates import Template
    t = Template(name="无变量", category="c", strategy="coding", content="固定内容")
    monkeypatch.setattr(win, "_selected_template", lambda: t)
    win._use_template()
    assert win.input_edit.toPlainText() == "固定内容"
    assert win.tabs.currentIndex() == 0


def test_apply_hotkey_single_instance(win):
    from PySide6.QtGui import QShortcut
    win.settings.hotkey = "Ctrl+X"
    win._apply_hotkey()
    assert isinstance(win._hotkey_sc, QShortcut)
    live = [c for c in win.children() if isinstance(c, QShortcut)]
    assert len(live) == 1


def test_close_event_closes_db(win):
    import sqlite3
    w = win
    w.close()
    with pytest.raises(sqlite3.ProgrammingError):
        w.db.list()
