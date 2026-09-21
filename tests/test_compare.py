"""compare.py 测试：并发对比、取消、排名、结论、条目解析。"""
import threading
import time
from dataclasses import dataclass

import pytest

from promptforge.compare import CompareResult, CompareRunner, diff_summary, parse_notes_bullets


@dataclass
class Cfg:
    name: str = "cfg"
    base_url: str = "http://gw/v1"
    api_key: str = "k"
    model: str = "m"


# ---------- CompareResult ----------

def test_result_summary_ok():
    r = CompareResult(profile_name="A", model="m", base_url="u", ok=True,
                      elapsed_ms=1234.0, ttft_ms=300.0, chars=88)
    s = r.summary()
    assert "1234ms" in s and "首字 300ms" in s and "88 字" in s


def test_result_summary_without_ttft():
    r = CompareResult(profile_name="A", model="m", base_url="u", ok=True,
                      elapsed_ms=500.0, chars=10)
    assert "首字" not in r.summary()


def test_result_summary_failure_and_cancel():
    assert "失败" in CompareResult(profile_name="A", model="m", base_url="u",
                                   ok=False, error="连不上").summary()
    assert CompareResult(profile_name="A", model="m", base_url="u",
                         ok=False, cancelled=True).summary() == "已取消"


# ---------- parse_notes_bullets ----------

@pytest.mark.parametrize("raw,expected", [
    ("1. 补充了角色设定\n2. 明确了输出格式", ["补充了角色设定", "明确了输出格式"]),
    ("- 第一条\n- 第二条", ["第一条", "第二条"]),
    ("* a\n* b", ["a", "b"]),
    ("1) x\n2) y", ["x", "y"]),
    ("1、中文序号", ["中文序号"]),
    ("", []),
    ("\n\n", []),
    ("无前缀直接一行", ["无前缀直接一行"]),
    ("1. 有\n\n2. 空行分隔", ["有", "空行分隔"]),
])
def test_parse_notes_bullets(raw, expected):
    assert parse_notes_bullets(raw) == expected


# ---------- diff_summary ----------

def _ok(name, ms, chars):
    return CompareResult(profile_name=name, model="m", base_url="u", ok=True,
                         elapsed_ms=ms, chars=chars)


def test_diff_summary_picks_fastest():
    out = diff_summary([_ok("A", 900, 100), _ok("B", 300, 80)])
    assert "2/2 成功" in out["verdict"]
    assert "B" in out["detail"] and "300ms" in out["detail"]


def test_diff_summary_mentions_longest_and_spread():
    # B 字符数最多（200），故"最长"应报 B；耗时差 900-300=600
    out = diff_summary([_ok("A", 900, 50), _ok("B", 300, 200)])
    assert "B" in out["detail"] and "200 字" in out["detail"]
    assert "600ms" in out["detail"]


def test_diff_summary_lists_tied_longest_names():
    out = diff_summary([_ok("A", 100, 200), _ok("B", 200, 200)])
    assert "A/B" in out["detail"] or "B/A" in out["detail"]


def test_diff_summary_all_failed():
    out = diff_summary([CompareResult(profile_name="A", model="m", base_url="u",
                                      ok=False, error="x")])
    assert out["verdict"] == "全部失败"


def test_diff_summary_single_ok_no_spread():
    out = diff_summary([_ok("A", 500, 10)])
    assert "1/1 成功" in out["verdict"]
    assert "耗时差" not in out["detail"]


# ---------- CompareRunner ----------

class FakeClient:
    """可控的假客户端，用于替代网络调用。"""

    def __init__(self, cfg, delay=0.0, fail=False, text="RESULT", on_delta_unused=None):
        self.cfg = cfg
        self.delay = delay
        self.fail = fail
        self.text = text
        self.model = getattr(cfg, "model", "")
        self.base_url = getattr(cfg, "base_url", "")

    def _maybe_fail(self):
        if self.fail:
            from promptforge.llm_client import LLMError
            raise LLMError("模拟失败")


def _patch_runner(monkeypatch, behaviors):
    """把 CompareRunner._make_client 换成返回假客户端的实现。

    behaviors: {profile_name: dict(delay=..., fail=..., text=...)}
    """
    def fake_make_client(self, cfg):
        b = behaviors.get(getattr(cfg, "name", ""), {})
        return _BehaviorClient(cfg, **b)

    monkeypatch.setattr(CompareRunner, "_make_client", fake_make_client)


class _BehaviorClient:
    """按 behavior 配置返回可控结果的假客户端。

    必须实现 stream/complete 两个方法——_run_one 会走
    Enhancer.enhance_stream()/enhance()，它们分别调用这两个入口。
    """

    def __init__(self, cfg, delay=0.0, fail=False, text="RESULT", chunks=None,
                 ttft_delay=0.0):
        self.cfg = cfg
        self.delay = delay
        self.fail = fail
        self.text = text
        self.chunks = chunks if chunks is not None else ["RE", "SU", "LT"]
        self.ttft_delay = ttft_delay
        self.model = getattr(cfg, "model", "")
        self.base_url = getattr(cfg, "base_url", "")
        self.enhance_calls = 0

    def _guard(self):
        if self.fail:
            from promptforge.llm_client import LLMError
            raise LLMError("模拟失败")

    def complete(self, prompt, timeout=None, retries=None):
        self.enhance_calls += 1
        if self.delay:
            time.sleep(self.delay)
        self._guard()
        # 模型正常输出 <enhanced>/<notes> 结构
        return f"<enhanced>{self.text}</enhanced><notes>1. 说明一\n2. 说明二</notes>"

    def stream(self, prompt, on_delta=None, should_stop=None):
        self.enhance_calls += 1
        if self.ttft_delay:
            time.sleep(self.ttft_delay)
        for c in self.chunks:
            if should_stop is not None and should_stop():
                return
            if self.delay:
                time.sleep(self.delay / max(1, len(self.chunks)))
            if on_delta:
                on_delta(c)
            yield c
        self._guard()


def test_runner_empty_returns_empty():
    r = CompareRunner(strategy="general", original="x")
    assert r.run() == []


def test_runner_collects_all_results(monkeypatch):
    _patch_runner(monkeypatch, {"A": {"delay": 0.01}, "B": {"delay": 0.01}})
    r = CompareRunner(strategy="general", original="写个爬虫")
    r.add(Cfg(name="A"), "A")
    r.add(Cfg(name="B"), "B")
    results = r.run()
    assert len(results) == 2
    assert {x.profile_name for x in results} == {"A", "B"}


def test_runner_runs_concurrently_not_serially(monkeypatch):
    """两个各 0.3s 的任务并发跑，总耗时应明显小于串行的 0.6s。"""
    _patch_runner(monkeypatch, {"A": {"delay": 0.3}, "B": {"delay": 0.3}})
    r = CompareRunner(strategy="general", original="x")
    r.add(Cfg(name="A"), "A")
    r.add(Cfg(name="B"), "B")
    t0 = time.perf_counter()
    r.run()
    wall = time.perf_counter() - t0
    assert wall < 0.55, f"看起来是串行执行：{wall:.2f}s"


def test_runner_one_failure_does_not_block_others(monkeypatch):
    _patch_runner(monkeypatch, {"A": {"delay": 0.01}, "B": {"delay": 0.01, "fail": True}})
    r = CompareRunner(strategy="general", original="x")
    r.add(Cfg(name="A"), "A")
    r.add(Cfg(name="B"), "B")
    results = r.run()
    by_name = {x.profile_name: x for x in results}
    assert by_name["B"].ok is False
    assert "模拟失败" in by_name["B"].error


def test_runner_preserves_registration_order(monkeypatch):
    _patch_runner(monkeypatch, {"A": {"delay": 0.1}, "B": {"delay": 0.01}})
    r = CompareRunner(strategy="general", original="x")
    r.add(Cfg(name="A"), "A")
    r.add(Cfg(name="B"), "B")
    results = r.run()
    assert [x.profile_name for x in results] == ["A", "B"]


def test_runner_uses_cfg_name_by_default(monkeypatch):
    _patch_runner(monkeypatch, {"我的网关": {"delay": 0.01}})
    r = CompareRunner(strategy="general", original="x")
    r.add(Cfg(name="我的网关"))
    assert r.run()[0].profile_name == "我的网关"


def test_runner_ranked_orders_by_time_and_pushes_failures_last(monkeypatch):
    # 用更大的时差，避免线程调度抖动盖过真实差异
    _patch_runner(monkeypatch, {"SLOW": {"delay": 0.6}, "FAST": {"delay": 0.01},
                                "BAD": {"delay": 0.01, "fail": True}})
    r = CompareRunner(strategy="general", original="x")
    for n in ("SLOW", "FAST", "BAD"):
        r.add(Cfg(name=n), n)
    r.run()
    ranked = r.ranked()
    names = [x.profile_name for x in ranked]
    assert names[-1] == "BAD", f"失败项应排最后：{names}"
    assert names.index("FAST") < names.index("SLOW"), f"快的应排前：{names}"


def test_runner_cancel_marks_cancelled(monkeypatch):
    """取消后结果应标记为 cancelled，而不是当成普通失败。"""
    class SlowStreamClient:
        model = "m"
        base_url = "u"

        def __init__(self, cfg):
            self.cfg = cfg

        def stream(self, prompt, on_delta=None, should_stop=None):
            # 必须是生成器（含 yield），否则返回 None 会让调用方迭代失败。
            # 持续产出直到被取消，模拟长回答。
            for i in range(200):
                if should_stop is not None and should_stop():
                    return
                time.sleep(0.01)
                if on_delta:
                    on_delta(f"chunk{i}")
                yield f"chunk{i}"

    monkeypatch.setattr(CompareRunner, "_make_client",
                        lambda self, cfg: SlowStreamClient(cfg))

    r = CompareRunner(strategy="general", original="x")
    r.add(Cfg(name="A"), "A")

    def cancel_soon():
        time.sleep(0.08)
        r.request_stop()

    threading.Thread(target=cancel_soon, daemon=True).start()
    results = r.run()
    assert len(results) == 1
    assert results[0].cancelled is True, f"应标记 cancelled，实际：{results[0]}"
    assert r.is_stop_requested() is True


def test_runner_on_result_callback_fires(monkeypatch):
    _patch_runner(monkeypatch, {"A": {"delay": 0.01}})
    seen = []
    r = CompareRunner(strategy="general", original="x")
    r.add(Cfg(name="A"), "A")
    r.on_result = lambda idx, res: seen.append((idx, res.profile_name))
    r.run()
    assert seen == [(0, "A")]


def test_runner_client_construction_failure_recorded(monkeypatch):
    def boom(self, cfg):
        raise ValueError("坏的配置")
    monkeypatch.setattr(CompareRunner, "_make_client", boom)
    r = CompareRunner(strategy="general", original="x")
    r.add(Cfg(name="A"), "A")
    res = r.run()[0]
    assert res.ok is False
    assert "坏的配置" in res.error
