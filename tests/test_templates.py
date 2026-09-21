"""templates.py 单元测试：变量提取与填充。

覆盖回归：带空白的占位符 {{ 主题 }} 早期替换不掉，会原样泄漏进
最终提示词被发给模型。
"""
from promptforge.templates import (
    Template,
    add_user_template,
    delete_user_template,
    load_all,
    load_builtin,
    load_user,
    normalize_var_name,
)


def _t(content, **kw):
    return Template(name="x", category="c", strategy="general",
                    content=content, **kw)


def test_variables_dedupe_and_order():
    t = _t("{{a}} {{b}} {{a}} {{c}}")
    assert t.variables() == ["a", "b", "c"]


def test_variables_strip_whitespace():
    t = _t("{{ 主题 }} {{主题}}  {{  主题  }}")
    assert t.variables() == ["主题"]


def test_fill_plain():
    assert _t("你好{{名字}}").fill({"名字": "石井"}) == "你好石井"


def test_fill_with_padded_placeholder():
    """回归：{{ 名字 }} 必须能填上。"""
    assert _t("你好{{ 名字 }}").fill({"名字": "石井"}) == "你好石井"


def test_fill_with_padded_key():
    assert _t("你好{{名字}}").fill({" 名字 ": "石井"}) == "你好石井"


def test_fill_both_sides_padded():
    assert _t("你好{{  名字  }}").fill({"  名字  ": "石井"}) == "你好石井"


def test_fill_preserves_unprovided_placeholder():
    out = _t("{{a}} 和 {{b}}").fill({"a": "1"})
    assert out == "1 和 {{b}}"


def test_fill_empty_values_is_noop():
    src = "{{a}} {{b}}"
    assert _t(src).fill({}) == src


def test_fill_chinese_content_realistic():
    t = _t("请帮我写一份关于{{ 主题 }}的{{文体}}，面向{{目标读者}}。")
    out = t.fill({"主题": "量子计算", "文体": "科普文章", "目标读者": "高中生"})
    assert out == "请帮我写一份关于量子计算的科普文章，面向高中生。"
    assert "{{" not in out


def test_fill_non_str_value_coerced():
    assert _t("{{n}}").fill({"n": 42}) == "42"


def test_normalize_var_name():
    assert normalize_var_name("  主题  ") == "主题"
    assert normalize_var_name("目标  读者") == "目标 读者"


# ---------- 内置/用户模板库 ----------

def test_builtin_templates_load():
    items = load_builtin()
    assert len(items) >= 8
    assert all(t.builtin for t in items)


def test_builtin_templates_all_have_required_fields():
    for t in load_builtin():
        assert t.name and t.category and t.strategy and t.content
        assert t.strategy in {"general", "coding", "drawing", "writing"}


def test_user_template_roundtrip():
    add_user_template(_t("自定义{{v}}"))
    items = load_user()
    assert len(items) == 1
    assert items[0].content == "自定义{{v}}"
    assert not items[0].builtin


def test_user_template_delete_by_name():
    add_user_template(Template(name="待删", category="c", strategy="general", content="x"))
    add_user_template(Template(name="保留", category="c", strategy="general", content="y"))
    delete_user_template("待删")
    names = [t.name for t in load_user()]
    assert names == ["保留"]


def test_load_all_includes_builtin_and_user():
    add_user_template(Template(name="我的", category="c", strategy="general", content="z"))
    all_items = load_all()
    assert any(t.builtin for t in all_items)
    assert any(t.name == "我的" for t in all_items)


def test_corrupt_user_templates_returns_empty():
    import os

    from promptforge.config import data_dir
    with open(os.path.join(data_dir(), "user_templates.json"), "w", encoding="utf-8") as f:
        f.write("not json at all")
    assert load_user() == []
