"""双击入口：复用本机服务，未运行时隐身启动，然后打开浏览器。"""
import argparse
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import json
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:8765"


def healthy():
    try:
        with build_opener(ProxyHandler({})).open(URL + "/api/health", timeout=1) as response:
            return json.loads(response.read()).get("app") == "industry-review-local-v1"
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    from build_preview import build
    build()
    if not healthy():
        log_dir = ROOT / "workspace/cache"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "service.log").open("ab") as log:
            subprocess.Popen([sys.executable, str(Path(__file__).with_name("live_server.py"))],
                             cwd=ROOT, stdout=log, stderr=log,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(40):
            if healthy():
                break
            time.sleep(.25)
        else:
            raise RuntimeError("看板未能启动，请查看 workspace/cache/service.log，确认8765端口可用。")
    if not args.no_browser:
        webbrowser.open(URL)
    print(URL)


if __name__ == "__main__":
    main()
