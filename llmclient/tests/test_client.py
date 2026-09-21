"""llmclient 测试：端点归一化、传输、流式、中止、探测。"""
import json
from dataclasses import dataclass

import pytest
from llmclient.endpoints import chat_prefix

from llmclient import LLMClient, LLMError, ProbeResult, build_endpoint, build_models_endpoint


@dataclass
class Cfg:
    base_url: str = "http://gw/v1"
    api_key: str = "k"
    model: str = "m"


# ---------- 端点归一化 ----------

@pytest.mark.parametrize("given,expected", [
    ("http://a", "http://a/v1/chat/completions"),
    ("http://a/", "http://a/v1/chat/completions"),
    ("http://a/v1", "http://a/v1/chat/completions"),
    ("http://a/v1/", "http://a/v1/chat/completions"),
    ("http://a/v1/chat/completions", "http://a/v1/chat/completions"),
    ("http://a/api/v1", "http://a/api/v1/chat/completions"),
    ("  http://a/v1  ", "http://a/v1/chat/completions"),
])
def test_build_endpoint(given, expected):
    assert build_endpoint(given) == expected


@pytest.mark.parametrize("given,expected", [
    ("http://a", "http://a/v1/models"),
    ("http://a/v1", "http://a/v1/models"),
    ("http://a/v1/", "http://a/v1/models"),
    ("http://a/v1/models", "http://a/v1/models"),
    ("http://a/v1/chat/completions", "http://a/v1/models"),
    ("http://a/api/v1/chat/completions", "http://a/api/v1/models"),
])
def test_build_models_endpoint(given, expected):
    assert build_models_endpoint(given) == expected


def test_chat_prefix():
    assert chat_prefix("http://a/v1") == "http://a/v1"


# ---------- 鸭子类型配置 ----------

def test_accepts_duck_typed_config():
    c = LLMClient(Cfg(base_url="http://x", api_key="kk", model="mm"))
    assert c.endpoint == "http://x/v1/chat/completions"
    assert c.models_endpoint == "http://x/v1/models"
    assert c.model == "mm"


def test_missing_attributes_degrade_to_empty():
    class Bare:
        pass
    c = LLMClient(Bare())
    assert c.base_url == ""
    assert c.api_key == ""
    assert c.model == ""
    # 空 base_url 仍应产生一个确定的地址，而不是抛异常
    assert c.endpoint == "/v1/chat/completions"


def test_none_attributes_degrade_to_empty():
    @dataclass
    class WithNone:
        base_url: object = None
        api_key: object = None
        model: object = None
    c = LLMClient(WithNone())
    assert c.base_url == "" and c.api_key == "" and c.model == ""


# ---------- 假 Response ----------

class FakeResp:
    def __init__(self, lines=None, payload=None, status=200, text="", json_raises=False):
        self._lines = lines or []
        self._payload = payload
        self.status_code = status
        self.encoding = None
        self.text = text
        self.closed = False
        self._json_raises = json_raises

    def iter_lines(self, decode_unicode=False):
        yield from self._lines

    def json(self):
        if self._json_raises or self._payload is None:
            raise ValueError("no json")
        return self._payload

    def close(self):
        self.closed = True


def _sse(*chunks, finish="stop"):
    lines = []
    for ch in chunks:
        lines.append("data: " + json.dumps(
            {"choices": [{"delta": {"content": ch}, "finish_reason": None}]}))
    lines.append("data: " + json.dumps(
        {"choices": [{"delta": {}, "finish_reason": finish}]}))
    lines.append("data: [DONE]")
    return lines


def _client_with(monkeypatch, resp):
    c = LLMClient(Cfg())
    monkeypatch.setattr(c, "_post", lambda *a, **kw: resp)
    return c


# ---------- 请求构造 ----------

def test_headers_bearer_only_when_key_present():
    assert LLMClient(Cfg(api_key="  k  "))._headers()["Authorization"] == "Bearer k"
    assert "Authorization" not in LLMClient(Cfg(api_key=""))._headers()
    assert LLMClient(Cfg())._headers()["Connection"] == "close"


def test_payload_max_tokens_optional():
    assert "max_tokens" not in LLMClient(Cfg(), max_tokens=0)._payload("s", False)
    assert LLMClient(Cfg(), max_tokens=9)._payload("s", False)["max_tokens"] == 9


# ---------- complete ----------

def test_complete_ok(monkeypatch):
    c = _client_with(monkeypatch, FakeResp(payload={"choices": [{"message": {"content": "hi"}}]}))
    assert c.complete("p") == "hi"


def test_complete_closes_response(monkeypatch):
    resp = FakeResp(payload={"choices": [{"message": {"content": "x"}}]})
    _client_with(monkeypatch, resp).complete("p")
    assert resp.closed is True


def test_complete_bad_json(monkeypatch):
    c = _client_with(monkeypatch, FakeResp(json_raises=True))
    with pytest.raises(LLMError) as ei:
        c.complete("p")
    assert "OpenAI 兼容" in str(ei.value)


def test_complete_bad_shape(monkeypatch):
    c = _client_with(monkeypatch, FakeResp(payload={"nope": 1}))
    with pytest.raises(LLMError) as ei:
        c.complete("p")
    assert "响应结构异常" in str(ei.value)


def test_complete_none_content_becomes_empty(monkeypatch):
    c = _client_with(monkeypatch, FakeResp(payload={"choices": [{"message": {"content": None}}]}))
    assert c.complete("p") == ""


# ---------- stream ----------

def test_stream_collects(monkeypatch):
    c = _client_with(monkeypatch, FakeResp(lines=_sse("a", "b")))
    assert "".join(c.stream("p")) == "ab"


def test_stream_closes_on_finish(monkeypatch):
    resp = FakeResp(lines=_sse("a"))
    _client_with(monkeypatch, resp)
    list(_client_with(monkeypatch, resp).stream("p"))
    assert resp.closed is True


def test_stream_stops_cooperatively(monkeypatch):
    resp = FakeResp(lines=_sse("a", "b", "c", "d", "e"))
    c = _client_with(monkeypatch, resp)
    seen = []
    for _ in c.stream("p", on_delta=seen.append, should_stop=lambda: len(seen) >= 2):
        pass
    assert seen == ["a", "b"]
    assert resp.closed is True


def test_stream_skips_junk_and_heartbeat(monkeypatch):
    lines = [": keepalive", "", "garbage", "data: {not json",
             "data: " + json.dumps({"choices": [{"delta": {"content": "ok"}}]})]
    c = _client_with(monkeypatch, FakeResp(lines=lines))
    assert "".join(c.stream("p")) == "ok"


def test_stream_tolerates_missing_choices(monkeypatch):
    lines = ["data: " + json.dumps({"usage": {}}),
             "data: " + json.dumps({"choices": []}),
             "data: " + json.dumps({"choices": [{"delta": {"content": "z"}}]})]
    c = _client_with(monkeypatch, FakeResp(lines=lines))
    assert "".join(c.stream("p")) == "z"


def test_stream_exits_on_finish_without_done(monkeypatch):
    """网关不发 [DONE] 时，靠 finish_reason 退出，不永久挂起。"""
    lines = ["data: " + json.dumps({"choices": [{"delta": {"content": "x"}}]}),
             "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
             "data: " + json.dumps({"choices": [{"delta": {"content": "SHOULD_NOT_APPEAR"}}]})]
    c = _client_with(monkeypatch, FakeResp(lines=lines))
    assert "".join(c.stream("p")) == "x"


# ---------- 错误诊断 ----------

def test_format_error_ssl_before_connection_error():
    """SSLError 是 ConnectionError 子类，必须先被识别为 SSL 问题。"""
    import requests
    c = LLMClient(Cfg())
    msg = c._format_error(requests.exceptions.SSLError("bad cert"))
    assert "SSL" in msg
    assert "无法连接服务器" not in msg


def test_format_error_types():
    import requests
    c = LLMClient(Cfg())
    assert "读取超时" in c._format_error(requests.exceptions.ReadTimeout())
    assert "连接超时" in c._format_error(requests.exceptions.ConnectTimeout())
    assert "无法连接服务器" in c._format_error(requests.exceptions.ConnectionError())
    assert "请求失败" in c._format_error(ValueError("x"))


def test_format_error_includes_url():
    import requests
    c = LLMClient(Cfg(base_url="http://gw"))
    assert "http://gw/v1/chat/completions" in c._format_error(requests.exceptions.ReadTimeout())


def test_http_error_raises_with_body(monkeypatch):
    c = LLMClient(Cfg(), retries=0)
    resp = FakeResp(status=401, text="unauthorized")
    monkeypatch.setattr("requests.post", lambda *a, **kw: resp)
    with pytest.raises(LLMError) as ei:
        c.complete("p")
    assert "401" in str(ei.value)


# ---------- 探测 ----------

def test_probe_result_summary_ok():
    r = ProbeResult(ok=True, url="u", elapsed_ms=1234.0, models=["a", "b"])
    assert "OK" in r.summary() and "1234ms" in r.summary() and "2 个模型" in r.summary()


def test_probe_result_summary_fail():
    r = ProbeResult(ok=False, url="u", detail="连不上")
    assert "失败" in r.summary() and "连不上" in r.summary()


def test_probe_models_success(monkeypatch):
    payload = {"data": [{"id": "gpt-4o"}, {"id": "deepseek-chat"}, {"no_id": 1}]}
    c = LLMClient(Cfg())
    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp(payload=payload))
    r = c.probe_models()
    assert r.ok and r.models == ["gpt-4o", "deepseek-chat"]
    assert r.elapsed_ms >= 0


def test_probe_models_does_not_raise_on_failure(monkeypatch):
    import requests
    c = LLMClient(Cfg())
    def boom(*a, **kw):
        raise requests.exceptions.ConnectionError("nope")
    monkeypatch.setattr("requests.get", boom)
    r = c.probe_models()
    assert r.ok is False
    assert "无法连接服务器" in r.detail


def test_probe_chat_success(monkeypatch):
    c = LLMClient(Cfg())
    monkeypatch.setattr(c, "complete", lambda *a, **kw: "ok")
    r = c.probe_chat()
    assert r.ok and r.detail == "ok"


def test_probe_falls_back_to_chat(monkeypatch):
    """models 端点不通时应退回 chat 探活。"""
    c = LLMClient(Cfg())
    monkeypatch.setattr(c, "probe_models",
                        lambda timeout=None: ProbeResult(ok=False, url="m", detail="404"))
    monkeypatch.setattr(c, "probe_chat",
                        lambda timeout=None: ProbeResult(ok=True, url="c", detail="ok"))
    r = c.probe()
    assert r.ok and r.url == "c"


def test_list_models_string_items(monkeypatch):
    c = LLMClient(Cfg())
    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp(payload=["m1", "m2"]))
    assert c.list_models() == ["m1", "m2"]


def test_list_models_bad_shape_raises(monkeypatch):
    c = LLMClient(Cfg())
    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp(payload={"weird": 1}))
    with pytest.raises(LLMError):
        c.list_models()


def test_ping_uses_short_timeout_no_retry(monkeypatch):
    captured = {}
    c = LLMClient(Cfg())
    def fake_complete(prompt, timeout=None, retries=None):
        captured.update(timeout=timeout, retries=retries)
        return "成功"
    monkeypatch.setattr(c, "complete", fake_complete)
    assert c.ping() == "成功"
    assert captured == {"timeout": 30, "retries": 0}
