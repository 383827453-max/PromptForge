"""多模型对比面板 UI 测试（offscreen）。

覆盖：面板构造、配置勾选列表、卡片生成、结果回填、历史入库回调、取消。
不发起真实网络请求——CompareRunner 被替换成假实现。
"""
from dataclasses import dataclass, field
from typing import List

import pytest

pytest.importorskip("PySide6")

from promptforge.compare import CompareResult
from promptforge.config import ApiConfig
from promptforge.ui.compare_tab import CompareTab, ResultCard


@dataclass
class FakeSettings:
    profiles: List[ApiConfig] = field(default_factory=lambda: [
        ApiConfig(name="网关A", base_url="http://a/v1", api_key="k", model="m-a"),
        ApiConfig(name="网关B", base_url="http://b/v1", api_key="k", model="m-b"),
        ApiConfig(name="网关C", base_url="http://c/v1", api_key="k", model="m-c"),
    ])
    timeout: int = 30
    temperature: float = 0.7
    max_tokens: int = 0
    use_stream: bool = True


@pytest.fixture
def saved():
    return []


@pytest.fixture
def tab(qapp, saved):
    settings = FakeSettings()
    t = CompareTab(
        settings_provider=lambda: settings,
        save_history=lambda *a: saved.append(a),
        input_provider=lambda: "主标签的输入",
    )
    yield t
    t.stop()
    t.deleteLater()


# ---------- 构造 ----------

def test_constructs_with_profiles(tab):
    assert len(tab._profile_widgets()) == 3


def test_profile_checkboxes_show_model_and_url(tab):
    texts = [cb.text() for cb in tab._profile_widgets()]
    assert any("网关A" in t and "m-a" in t and "http://a/v1" in t for t in texts)


def test_profiles_refresh_picks_up_changes(qapp, saved):
    settings = FakeSettings()
    t = CompareTab(settings_provider=lambda: settings,
                   save_history=lambda *a: saved.append(a))
    assert len(t._profile_widgets()) == 1 or len(t._profile_widgets()) == 3
    settings.profiles.append(ApiConfig(name="新增", base_url="u", model="m"))
    t.refresh_profiles()
    assert len(t._profile_widgets()) == 4
    t.stop()


def test_refresh_does_not_duplicate_rows(tab):
    before = len(tab._profile_widgets())
    for _ in range(3):
        tab.refresh_profiles()
    assert len(tab._profile_widgets()) == before


def test_select_all_and_none(tab):
    tab._set_all_checked(False)
    assert tab._checked_indices() == []
    tab._set_all_checked(True)
    assert tab._checked_indices() == [0, 1, 2]


def test_default_checks_first_three(tab):
    assert tab._checked_indices() == [0, 1, 2]


# ---------- 校验 ----------

def test_start_without_input_warns(tab, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    hit = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: hit.setdefault("w", True))
    tab.input_edit.clear()
    tab.start()
    assert hit.get("w") is True
    assert tab.worker is None


def test_start_with_one_profile_warns(tab, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    hit = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: hit.setdefault("w", True))
    tab.input_edit.setPlainText("随便写点")
    tab._set_all_checked(False)
    tab._profile_widgets()[0].setChecked(True)
    tab.start()
    assert hit.get("w") is True


# ---------- 卡片与结果 ----------

def test_rebuild_cards_creates_one_per_profile(tab):
    profiles = FakeSettings().profiles
    tab._rebuild_cards(["A", "B", "C"], profiles)
    assert len(tab._cards) == 3
    assert all(isinstance(c, ResultCard) for c in tab._cards)


def test_rebuild_cards_does_not_accumulate(tab):
    profiles = FakeSettings().profiles
    for _ in range(3):
        tab._rebuild_cards(["A", "B"], profiles[:2])
    assert len(tab._cards) == 2


def test_on_result_fills_card(tab):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    r = CompareResult(profile_name="A", model="m-a", base_url="http://a/v1",
                      ok=True, enhanced="增强结果文本", notes="1. 说明",
                      elapsed_ms=500.0, chars=6)
    tab._on_result(0, r)
    card = tab._cards[0]
    assert card.text.toPlainText() == "增强结果文本"
    assert card.copy_btn.isEnabled()
    assert card.save_btn.isEnabled()
    assert "500ms" in card.status.text()


def test_on_result_failure_shows_error(tab):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    r = CompareResult(profile_name="A", model="m", base_url="u", ok=False,
                      error="连接超时：http://a/v1\n细节")
    tab._on_result(0, r)
    card = tab._cards[0]
    assert "失败" in card.status.text()
    assert not card.copy_btn.isEnabled()
    assert "连接超时" in card.status.toolTip()


def test_on_result_cancelled(tab):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    tab._on_result(0, CompareResult(profile_name="A", model="m", base_url="u",
                                    ok=False, cancelled=True))
    assert tab._cards[0].status.text() == "已取消"


def test_on_result_out_of_range_is_safe(tab):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    tab._on_result(99, CompareResult(profile_name="X", model="m", base_url="u", ok=True))
    tab._on_result(-1, CompareResult(profile_name="X", model="m", base_url="u", ok=True))


def test_on_delta_appends_text(tab):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    tab._on_delta(0, "第一段")
    tab._on_delta(0, "第二段")
    assert tab._cards[0].text.toPlainText() == "第一段第二段"
    assert "接收中" in tab._cards[0].status.text()


def test_on_delta_out_of_range_is_safe(tab):
    tab._on_delta(5, "x")


def test_on_finished_shows_summary(tab):
    tab._rebuild_cards(["A", "B"], FakeSettings().profiles[:2])
    results = [
        CompareResult(profile_name="A", model="m", base_url="u", ok=True,
                      elapsed_ms=900, chars=50),
        CompareResult(profile_name="B", model="m", base_url="u", ok=True,
                      elapsed_ms=300, chars=200),
    ]
    tab._on_finished(results)
    text = tab.summary_label.text()
    assert "2/2 成功" in text and "B" in text
    assert tab.run_btn.isEnabled()


def test_on_error_shows_dialog(tab, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    hit = {}
    monkeypatch.setattr(QMessageBox, "critical",
                        lambda *a, **k: hit.setdefault("e", True))
    tab._on_error("boom")
    assert hit.get("e") is True
    assert tab.run_btn.isEnabled()


# ---------- 历史入库 ----------

def test_save_card_writes_history(tab, saved):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    tab._strategy = "coding"
    tab._original = "原始"
    tab._on_result(0, CompareResult(profile_name="A", model="m", base_url="u",
                                    ok=True, enhanced="E", notes="N",
                                    elapsed_ms=1.0, chars=1))
    tab._save_card(tab._cards[0])
    assert saved == [("coding", "原始", "E", "N")]


def test_save_card_ignores_failed(tab, saved):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    tab._on_result(0, CompareResult(profile_name="A", model="m", base_url="u",
                                    ok=False, error="x"))
    tab._save_card(tab._cards[0])
    assert saved == []


def test_copy_card_puts_text_on_clipboard(tab, qapp):
    from PySide6.QtWidgets import QApplication
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    tab._on_result(0, CompareResult(profile_name="A", model="m", base_url="u",
                                    ok=True, enhanced="复制我", elapsed_ms=1.0,
                                    chars=3))
    tab._copy_card(tab._cards[0])
    assert QApplication.clipboard().text() == "复制我"


# ---------- 输入同步 ----------

def test_sync_input_from_main_tab(tab):
    tab.input_edit.clear()
    tab._sync_input()
    assert tab.input_edit.toPlainText() == "主标签的输入"


def test_sync_input_without_provider_is_noop(qapp, saved):
    t = CompareTab(settings_provider=lambda: FakeSettings(),
                   save_history=lambda *a: saved.append(a))
    t._sync_input()   # 不应抛异常
    t.stop()


def test_sync_input_ignores_empty_main_input(qapp, saved):
    t = CompareTab(settings_provider=lambda: FakeSettings(),
                   save_history=lambda *a: saved.append(a),
                   input_provider=lambda: "   ")
    t.input_edit.setPlainText("已有内容")
    t._sync_input()
    assert t.input_edit.toPlainText() == "已有内容"
    t.stop()


# ---------- 取消与收尾 ----------

def test_cancel_without_worker_is_safe(tab):
    tab.cancel()


def test_stop_without_worker_is_safe(tab):
    tab.stop()


def test_notes_toggle(tab):
    tab._rebuild_cards(["A"], FakeSettings().profiles[:1])
    tab.show_notes_cb.setChecked(True)
    assert tab._cards[0].notes.isVisible() or tab._cards[0].notes.isVisibleTo(tab)


def test_start_uses_real_settings_values(tab, monkeypatch):
    """start() 应把设置里的超时/温度等传给 runner。"""
    captured = {}

    class FakeRunner:
        def __init__(self, **kw):
            captured.update(kw)
            self.jobs = []
        def add(self, cfg, name):
            self.jobs.append(name)
            return len(self.jobs) - 1
        def request_stop(self):
            pass
        def run(self):
            return []

    monkeypatch.setattr("promptforge.ui.compare_tab.CompareRunner", FakeRunner)
    tab.input_edit.setPlainText("测试输入")
    tab._set_all_checked(True)
    tab.start()
    assert captured["timeout"] == 30
    assert captured["temperature"] == 0.7
    assert captured["original"] == "测试输入"
    assert captured["use_stream"] is True
    if tab.worker is not None:
        tab.worker.wait(2000)
