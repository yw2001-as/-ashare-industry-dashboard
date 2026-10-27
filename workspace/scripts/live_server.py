"""仅监听127.0.0.1，提供看板及同源只读数据接口。"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from urllib.parse import urlsplit

from live_data import CACHE, DashboardStore, ROOT


def live_document():
    fragment = (ROOT / "dashboard.fragment.html").read_text(encoding="utf-8")
    fragment = fragment.replace('https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js', '/assets/d3.min.js')
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>整体行业复盘 · 盘中看板</title><style>body{margin:0;background:#fcfbf8}main{max-width:1440px;margin:auto}</style>'
            '<script>globalThis.INDUSTRY_LIVE_MODE=true;</script></head><body><main>' + fragment +
            '</main><script src="/assets/live-client.js"></script></body></html>').encode("utf-8")


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, body, kind="application/json; charset=utf-8", status=200):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self.respond(live_document(), "text/html; charset=utf-8")
            elif path == "/api/health":
                self.respond(b'{"app":"industry-review-local-v1"}')
            elif path == "/api/snapshot":
                self.respond(json.dumps(store.snapshot(), ensure_ascii=False, allow_nan=False).encode("utf-8"))
            elif path in ("/assets/live-client.js", "/assets/d3.min.js"):
                file = ROOT / ("workspace/scripts/live-client.js" if path.endswith("live-client.js") else "workspace/vendor/d3.min.js")
                self.respond(file.read_bytes(), "text/javascript; charset=utf-8")
            else:
                self.respond(b'{"error":"not found"}', status=404)

        def do_POST(self):
            if self.path != "/api/refresh":
                self.respond(b'{"error":"not found"}', status=404)
                return
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.respond(b'{"error":"origin rejected"}', status=403)
                return
            # 重复点按不叠加请求，也不修改缓存的原始行情时间。
            last = getattr(store, "last_manual", 0)
            if time.monotonic() - last > 15:
                store.last_manual = time.monotonic()
                threading.Thread(target=store.refresh, daemon=True).start()
            self.respond(b'{"accepted":true}', status=202)

        def log_message(self, fmt, *args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    from build_preview import build
    build()
    store = DashboardStore()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    server.daemon_threads = True
    stop = threading.Event()

    def poll():
        while not stop.is_set():
            started = time.monotonic()
            try:
                store.refresh()
            except Exception as exc:
                CACHE.mkdir(parents=True, exist_ok=True)
                with (CACHE / "service-errors.log").open("a", encoding="utf-8") as log:
                    log.write(type(exc).__name__ + ": " + str(exc)[:180] + "\n")
            stop.wait(max(5, 60 - (time.monotonic() - started)))

    threading.Thread(target=poll, daemon=True).start()
    print(f"Local: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
