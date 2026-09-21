"""enhancer.py 单元测试：元提示词装配与输出解析降级。"""
import os

import pytest

from promptforge.config import data_dir
from promptforge.enhancer import (
    STRATEGIES,
    Enhancer,
    EnhanceResult,
    build_meta_prompt,
    load_strategy,
    parse_output,
    strategy_label,
    strategy_path,
)

# ---------- 策略加载 ----------

def test_all_declared_strategies_have_templates():
    for s in STRATEGIES:
        content = load_strategy(s["key"])
        assert "{original_prompt}" in content, s["key"]
        assert "{extra_instructions}" in content, s["key"]


def test_strategy_label_known_and_unknown():
    assert strategy_label("coding") == "编程"
    assert strategy_label("nope") == "nope"


def test_load_unknown_strategy_raises():
    with pytest.raises(FileNotFoundError):
        load_strategy("does_not_exist")


def test_user_strategy_overrides_builtin():
    d = os.path.join(data_dir(), "strategies")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "general.md"), "w", encoding="utf-8") as f:
        f.write("USER {original_prompt} {extra_instructions}")
    assert strategy_path("general") == os.path.join(d, "general.md")
    assert load_strategy("general").startswith("USER")


# ---------- 元提示词装配 ----------

def test_build_meta_prompt_injects_original():
    meta = build_meta_prompt("general", "帮我写爬虫")
    assert "帮我写爬虫" in meta
    assert "{original_prompt}" not in meta


def test_build_meta_prompt_extra_options_block():
    meta = build_meta_prompt("general", "x", "输出为英文")
    assert "输出为英文" in meta
    assert "用户附加要求" in meta


def test_build_meta_prompt_empty_extra_leaves_no_block():
    meta = build_meta_prompt("general", "x", "   ")
    assert "用户附加要求" not in meta
    assert "{extra_instructions}" not in meta


def test_build_meta_prompt_user_braces_do_not_crash():
    """用户输入含花括号时不得触发 format 类错误。"""
    meta = build_meta_prompt("coding", 'def f(): return {"k": {1,2}}')
    assert '{"k": {1,2}}' in meta


# ---------- 输出解析 ----------

def _r(raw):
    return parse_output(raw)


def test_parse_wellformed():
    out = _r("<enhanced>增强后</enhanced><notes>改了三点</notes>")
    assert isinstance(out, EnhanceResult)
    assert out.enhanced == "增强后"
    assert out.notes == "改了三点"


def test_parse_case_insensitive_tags():
    out = _r("<ENHANCED>x</ENHANCED><NOTES>y</NOTES>")
    assert out.enhanced == "x" and out.notes == "y"


def test_parse_multiline_content():
    out = _r("<enhanced>\n第一行\n第二行\n</enhanced>\n<notes>\n备注\n</notes>")
    assert out.enhanced == "第一行\n第二行"
    assert out.notes == "备注"


def test_parse_strips_markdown_fence_in_fallback():
    out = _r("```\n裸文本结果\n```")
    assert "裸文本结果" in out.enhanced


def test_parse_no_tags_falls_back_to_raw():
    out = _r("纯文本结果")
    assert out.enhanced == "纯文本结果"
    assert "未按结构化格式输出" in out.notes


def test_parse_notes_only_still_gives_enhanced():
    out = _r("<notes>只有备注</notes>")
    assert "只有备注" not in out.enhanced
    assert out.notes == "只有备注"


def test_parse_empty_string_does_not_crash():
    out = _r("")
    assert out.enhanced == ""


def test_parse_keeps_raw_untouched():
    raw = "<enhanced>a</enhanced>"
    assert _r(raw).raw == raw


def test_parse_enhanced_only_gives_default_note():
    out = _r("<enhanced>内容</enhanced>")
    assert out.enhanced == "内容"
    assert out.notes == ""


# ---------- Enhancer ----------

class FakeClient:
    def __init__(self, reply="<enhanced>OK</enhanced><notes>N</notes>", chunks=None):
        self.reply = reply
        self.chunks = chunks if chunks is not None else ["<enhanced>", "OK", "</enhanced>"]
        self.last_meta = None
        self.last_stop = None

    def complete(self, meta, **kw):
        self.last_meta = meta
        return self.reply

    def stream(self, meta, on_delta=None, should_stop=None):
        self.last_meta = meta
        self.last_stop = should_stop
        for c in self.chunks:
            if on_delta:
                on_delta(c)
            yield c


def test_enhance_non_stream():
    c = FakeClient()
    r = Enhancer(c).enhance("general", "原始")
    assert r.enhanced == "OK"
    assert "原始" in c.last_meta


def test_enhance_stream_accumulates():
    c = FakeClient()
    got = []
    r = Enhancer(c).enhance_stream("general", "原始", "", on_delta=got.append)
    assert r.enhanced == "OK"
    assert got == ["<enhanced>", "OK", "</enhanced>"]


def test_enhance_stream_passes_should_stop_through():
    c = FakeClient()
    flag = lambda: False  # noqa: E731
    Enhancer(c).enhance_stream("general", "x", "", on_delta=lambda s: None,
                               should_stop=flag)
    assert c.last_stop is flag


def test_enhance_stream_without_should_stop_is_none():
    c = FakeClient()
    Enhancer(c).enhance_stream("general", "x", "", on_delta=lambda s: None)
    assert c.last_stop is None
