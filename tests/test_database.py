"""database.py 单元测试：历史记录增删改查、筛选、排序。"""
import time

import pytest

from promptforge.database import Database, HistoryItem


@pytest.fixture
def db():
    d = Database()
    yield d
    d.close()


def test_add_returns_increasing_ids(db):
    a = db.add("general", "o1", "e1", "n1")
    b = db.add("coding", "o2", "e2", "n2")
    assert b > a


def test_get_roundtrip(db):
    i = db.add("coding", "原始", "增强", "备注")
    item = db.get(i)
    assert isinstance(item, HistoryItem)
    assert (item.strategy, item.original, item.enhanced, item.notes) == \
        ("coding", "原始", "增强", "备注")
    assert item.favorite == 0


def test_get_missing_returns_none(db):
    assert db.get(999999) is None


def test_list_newest_first(db):
    db.add("general", "older", "e", "")
    time.sleep(0.01)
    db.add("general", "newer", "e", "")
    items = db.list()
    assert items[0].original == "newer"


def test_search_matches_original_and_enhanced(db):
    db.add("general", "爬虫需求", "x", "")
    db.add("general", "y", "包含爬虫的增强结果", "")
    db.add("general", "无关", "无关", "")
    assert len(db.list(keyword="爬虫")) == 2


def test_filter_by_strategy(db):
    db.add("coding", "a", "e", "")
    db.add("writing", "b", "e", "")
    assert len(db.list(strategy="coding")) == 1


def test_filter_only_favorite(db):
    a = db.add("general", "a", "e", "")
    db.add("general", "b", "e", "")
    db.set_favorite(a, True)
    favs = db.list(only_favorite=True)
    assert len(favs) == 1 and favs[0].id == a


def test_toggle_favorite(db):
    a = db.add("general", "a", "e", "")
    db.set_favorite(a, True)
    assert db.get(a).favorite == 1
    db.set_favorite(a, False)
    assert db.get(a).favorite == 0


def test_delete_one(db):
    a = db.add("general", "a", "e", "")
    b = db.add("general", "b", "e", "")
    db.delete(a)
    assert db.get(a) is None
    assert db.get(b) is not None


def test_clear_all(db):
    for i in range(5):
        db.add("general", f"o{i}", "e", "")
    db.clear()
    assert db.list() == []


def test_limit_respected(db):
    for i in range(10):
        db.add("general", f"o{i}", "e", "")
    assert len(db.list(limit=3)) == 3


def test_time_str_format(db):
    i = db.add("general", "a", "e", "")
    s = db.get(i).time_str
    assert len(s) == 19 and s[4] == "-" and s[13] == ":"


def test_search_wildcard_is_escaped_as_data(db):
    """关键词里的 % 应按字面量处理，不应匹配任意内容。"""
    db.add("general", "正常内容", "e", "")
    assert db.list(keyword="%") == []


def test_persistence_across_connections():
    d1 = Database()
    d1.add("general", "persisted", "e", "")
    d1.close()
    d2 = Database()
    assert any(i.original == "persisted" for i in d2.list())
    d2.close()


def test_unicode_roundtrip(db):
    db.add("general", "中文🎯emoji", "增强🎨", "备注📝")
    item = db.list()[0]
    assert item.original == "中文🎯emoji"
    assert item.enhanced == "增强🎨"
