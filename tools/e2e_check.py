"""端到端验证：起本地 OpenAI 兼容 mock 网关，跑真实并发对比。

不是单测替身——真的走 HTTP、真的解析 SSE、真的测耗时与并发收益。
无需 API Key，跑完自动关闭服务。

    python tools/e2e_check.py

全部检查通过时退出码为 0。
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 输出含中文，必须显式把 stdout/stderr 设为 UTF-8。
# Windows 控制台默认码页可能是 cp1252（GitHub Actions runner 就是），
# 直接 print 中文会抛 UnicodeEncodeError: 'charmap' codec can't encode...
# errors='replace' 保证即使终端不支持也能跑完而不是中断。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(_ROOT) and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)   # 未安装时也能从仓库根跑

from promptforge.compare import CompareRunner, diff_summary  # noqa: E402
from promptforge.config import ApiConfig  # noqa: E402
from promptforge.llm_client import LLMClient  # noqa: E402

# 每个「模型」的模拟特性：首字延迟、块间隔、块数、是否报错
PROFILES = {
    "fast-model": {"ttft": 0.02, "gap": 0.005, "chunks": 8},
    "slow-model": {"ttft": 0.45, "gap": 0.03, "chunks": 8},
    "broken-model": {"error": 500},
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # 静音
        pass

    def do_GET(self):
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": k} for k in PROFILES]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw)
        except Exception:
            self.send_error(400)
            return
        model = req.get("model", "")
        spec = PROFILES.get(model)
        if spec is None:
            self.send_error(404, "unknown model")
            return
        if "error" in spec:
            body = b'{"error":"model exploded"}'
            self.send_response(spec["error"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if not req.get("stream"):
            time.sleep(spec["ttft"] + spec["gap"] * spec["chunks"])
            payload = {"choices": [{"message": {"content":
                       f"<enhanced>[{model}] 增强结果</enhanced>"
                       f"<notes>1. 说明甲\n2. 说明乙</notes>"}}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 流式
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        time.sleep(spec["ttft"])
        pieces = [f"[{model}]", " 增强", "结果", " 分段", "输出"]
        while len(pieces) < spec["chunks"]:
            pieces.append(".")
        for p in pieces:
            chunk = {"choices": [{"delta": {"content": p}, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
            time.sleep(spec["gap"])
        done = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        self.wfile.write(f"data: {json.dumps(done)}\n\n".encode())
        self.wfile.flush()


def main():
    # 必须用 ThreadingHTTPServer：单线程的 HTTPServer 会把并发请求排队，
    # 服务端串行化之后「并发是否生效」就测不出来了，排名也变成看谁先到。
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/v1"
    print(f"mock gateway: {base}\n")

    # ---- 1) 单客户端连通性 ----
    c = LLMClient(ApiConfig(base_url=base, model="fast-model"))
    print("ping:", repr(c.ping()[:40]))
    print("list_models:", c.list_models())
    probe = c.probe()
    print("probe:", probe.summary())

    # ---- 2) 流式 + 取消 ----
    got = []
    t0 = time.perf_counter()
    for _ in c.stream("hi", on_delta=got.append):
        pass
    print(f"stream: {len(got)} chunks in {(time.perf_counter()-t0)*1000:.0f}ms "
          f"-> {''.join(got)[:40]!r}")

    stop = threading.Event()
    got2 = []

    def stopper():
        time.sleep(0.03)
        stop.set()

    threading.Thread(target=stopper, daemon=True).start()
    t0 = time.perf_counter()
    for _ in c.stream("hi", on_delta=got2.append, should_stop=stop.is_set):
        pass
    print(f"cancel: stopped after {len(got2)} chunks in {(time.perf_counter()-t0)*1000:.0f}ms")

    # ---- 3) 并发对比（核心）----
    print("\n--- compare ---")
    runner = CompareRunner(strategy="general", original="写个爬虫", timeout=20,
                           use_stream=True)
    runner.add(ApiConfig(name="快网关", base_url=base, model="fast-model"), "快网关")
    runner.add(ApiConfig(name="慢网关", base_url=base, model="slow-model"), "慢网关")
    runner.add(ApiConfig(name="坏网关", base_url=base, model="broken-model"), "坏网关")

    deltas = {}
    runner.on_delta = lambda i, c_: deltas.setdefault(i, []).append(c_)

    t0 = time.perf_counter()
    results = runner.run()
    wall = (time.perf_counter() - t0) * 1000

    for r in results:
        print(f"  {r.profile_name:6} ok={r.ok!s:5} {r.summary()}")
        if r.ok:
            print(f"          -> {r.enhanced[:50]!r}")
        else:
            print(f"          -> {r.error.splitlines()[0]}")

    info = diff_summary(results)
    print(f"\n结论: {info['verdict']} · {info['detail']}")
    print(f"墙钟总耗时: {wall:.0f}ms")
    print(f"流式增量回调: {[(k, len(v)) for k, v in sorted(deltas.items())]}")

    # 并发性验证：墙钟应接近最慢的那个，而不是三者之和。
    # 慢网关单跑约 690ms，若并发生效墙钟应在 1s 以内；
    # 串行的话会是 60+690+0 ≈ 750ms 以上并且随请求数线性增长。
    ok_results = [r for r in results if r.ok]
    slowest = max(r.elapsed_ms for r in ok_results)
    print(f"最慢单请求: {slowest:.0f}ms  vs  墙钟: {wall:.0f}ms")
    assert wall < slowest * 2.0, (
        f"墙钟 {wall:.0f}ms 远超最慢单请求 {slowest:.0f}ms，并发没生效")

    # 排名验证：快网关必须比慢网关快（服务端已支持真并发，结果稳定）
    ranked = runner.ranked()
    names = [r.profile_name for r in ranked]
    print(f"排名: {names}")
    assert names[-1] == "坏网关", f"失败项应排最后：{names}"
    assert names.index("快网关") < names.index("慢网关"), f"快的应排前：{names}"

    # ---- 4) 取消整轮对比 ----
    print("\n--- cancel whole round ---")
    r2 = CompareRunner(strategy="general", original="x", timeout=20, use_stream=True)
    r2.add(ApiConfig(name="慢", base_url=base, model="slow-model"), "慢")
    threading.Thread(target=lambda: (time.sleep(0.1), r2.request_stop()),
                     daemon=True).start()
    res2 = r2.run()
    print(f"  cancelled={res2[0].cancelled} summary={res2[0].summary()}")
    assert res2[0].cancelled is True, "整轮取消未生效"

    srv.shutdown()
    print("\nALL E2E CHECKS PASSED")


if __name__ == "__main__":
    main()
