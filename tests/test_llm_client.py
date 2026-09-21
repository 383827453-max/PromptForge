"""llm_client.py 单元测试：端点归一化、SSE 解析、错误诊断、协作式取消。

不发真实网络请求：用假的 Response 对象替身。
"""
import json

import pytest

from promptforge.config import ApiConfig
from promptforge.llm_client import LLMClient, LLMError, build_endpoint

# ---------- build_endpoint ----------

@pytest.mark.parametrize("given,expected", [
    ("http://a", "http://a/v1/chat/completions"),
    ("http://a/", "http://a/v1/chat/completions"),
    ("http://a/v1", "http://a/v1/chat/completions"),
    ("http://a/v1/", "http://a/v1/chat/completions"),
    ("http://a/v1/chat/completions", "http://a/v1/chat/completions"),
    ("http://a/api/v1", "http://a/api/v1/chat/completions"),
    ("  http://a/v1  ", "http://a/v1/chat/completions"),
    ("https://gw.example.com/openai", "https://gw.example.com/openai/v1/chat/completions"),
])
def test_build_endpoint(given, expected):
    assert build_endpoint(given) == expected


# ---------- 假 Response ----------

class FakeResp:
    def __init__(self, lines=None, payload=None, status=200):
        self._lines = lines or []
        self._payload = payload
        self.status_code = status
        self.encoding = None
        self.text = ""
        self.closed = False

    def iter_lines(self, decode_unicode=False):
        yield from self._lines

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def close(self):
        self.closed = True


def _client():
    return LLMClient(ApiConfig(name="t", base_url="http://gw/v1",
                               api_key="k", model="m"))


def _patch_post(monkeypatch, resp):
    c = _client()
    monkeypatch.setattr(c, "_post", lambda *a, **kw: resp)
    return c


def _sse(*chunks, finish=None):
    lines = []
    for ch in chunks:
        lines.append("data: " + json.dumps(
            {"choices": [{"delta": {"content": ch}, "finish_reason": None}]}))
    lines.append("data: " + json.dumps(
        {"choices": [{"delta": {}, "finish_reason": finish or "stop"}]}))
    lines.append("data: [DONE]")
    return lines


# ---------- stream ----------

def test_stream_collects_chunks(monkeypatch):
    c = _patch_post(monkeypatch, FakeResp(lines=_sse("你", "好", "！")))
    assert "".join(c.stream("p")) == "你好！"


def test_stream_stops_on_cancel(monkeypatch):
    """回归：should_stop 为真时应立即停止消费并关闭响应。"""
    resp = FakeResp(lines=_sse("a", "b", "c", "d", "e"))
    c = _patch_post(monkeypatch, resp)

    seen = []

    def stop():
        return len(seen) >= 2

    for _chunk in c.stream("p", on_delta=seen.append, should_stop=stop):
        pass
    assert seen == ["a", "b"]
    assert resp.closed is True


def test_stream_closes_response_on_normal_end(monkeypatch):
    resp = FakeResp(lines=_sse("only"))
    c = _patch_post(monkeypatch, resp)
    list(c.stream("p"))
    assert resp.closed is True


def test_stream_skips_heartbeat_and_junk(monkeypatch):
    lines = [": keep-alive", "", "not-a-data-line", "data: {bad json",
             "data: " + json.dumps({"choices": [{"delta": {"content": "ok"}}]})]
    c = _patch_post(monkeypatch, FakeResp(lines=lines))
    assert "".join(c.stream("p")) == "ok"


def test_stream_handles_missing_choices(monkeypatch):
    lines = ["data: " + json.dumps({"usage": {}}),
             "data: " + json.dumps({"choices": []}),
             "data: " + json.dumps({"choices": [{"delta": {"content": "x"}}]})]
    c = _patch_post(monkeypatch, FakeResp(lines=lines))
    assert "".join(c.stream("p")) == "x"


# ---------- complete ----------

def test_complete_success(monkeypatch):
    resp = FakeResp(payload={"choices": [{"message": {"content": "结果"}}]})
    c = _patch_post(monkeypatch, resp)
    assert c.complete("p") == "结果"


def test_complete_non_json_raises_helpful(monkeypatch):
    c = _patch_post(monkeypatch, FakeResp(payload=None))
    with pytest.raises(LLMError) as ei:
        c.complete("p")
    assert "OpenAI 兼容" in str(ei.value)


def test_complete_bad_shape_raises(monkeypatch):
    c = _patch_post(monkeypatch, FakeResp(payload={"unexpected": True}))
    with pytest.raises(LLMError) as ei:
        c.complete("p")
    assert "响应结构异常" in str(ei.value)


def test_complete_empty_content_returns_empty(monkeypatch):
    c = _patch_post(monkeypatch, FakeResp(payload={"choices": [{"message": {"content": None}}]}))
    assert c.complete("p") == ""


# ---------- 请求构造 ----------

def test_headers_include_bearer_only_when_key_present():
    with_key = LLMClient(ApiConfig(base_url="u", model="m", api_key="  k  "))
    assert with_key._headers()["Authorization"] == "Bearer k"
    without = LLMClient(ApiConfig(base_url="u", model="m"))
    assert "Authorization" not in without._headers()
    assert with_key._headers()["Connection"] == "close"


def test_payload_omits_max_tokens_when_unlimited():
    c = LLMClient(ApiConfig(base_url="u", model="m"), max_tokens=0)
    assert "max_tokens" not in c._payload("sys", False)
    c2 = LLMClient(ApiConfig(base_url="u", model="m"), max_tokens=512)
    assert c2._payload("sys", False)["max_tokens"] == 512


def test_payload_shape():
    c = LLMClient(ApiConfig(base_url="u", model="m"), temperature=0.3)
    p = c._payload("SYS", True)
    assert p["model"] == "m"
    assert p["messages"] == [{"role": "system", "content": "SYS"}]
    assert p["stream"] is True
    assert p["temperature"] == 0.3


def test_ping_uses_short_timeout_and_no_retry(monkeypatch):
    """ping 必须快速失败：超时 30、retries 0。"""
    captured = {}
    c = _client()

    def fake_complete(prompt, timeout=None, retries=None):
        captured["timeout"] = timeout
        captured["retries"] = retries
        return "成功"

    monkeypatch.setattr(c, "complete", fake_complete)
    assert c.ping() == "成功"
    assert captured == {"timeout": 30, "retries": 0}


# ---------- 错误诊断 ----------

def test_format_error_read_timeout_mentions_url():
    import requests
    c = LLMClient(ApiConfig(base_url="http://gw/v1", model="m"))
    msg = c._format_error(requests.ReadTimeout())
    assert "http://gw/v1/chat/completions" in msg
    assert "读取超时" in msg


def test_format_error_connection_error():
    import requests
    c = LLMClient(ApiConfig(base_url="http://gw", model="m"))
    msg = c._format_error(requests.ConnectionError())
    assert "无法连接服务器" in msg


def test_format_error_unknown_exception():
    c = LLMClient(ApiConfig(base_url="http://gw", model="m"))
    assert "请求失败" in c._format_error(ValueError("boom"))
