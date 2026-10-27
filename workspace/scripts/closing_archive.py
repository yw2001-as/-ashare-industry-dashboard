"""每日收盘独立归档；缺测写状态，不把盘中缓存伪装为收盘。"""
from copy import deepcopy
import json
from pathlib import Path
import re
from html import escape

from live_data import ROOT, atomic_json, stamp

ARCHIVE = ROOT / "收盘数据"
REQUIRED = ("indices", "breadth", "concepts", "fund_concepts", "communications")


def dashboard_html(snapshot, label="收盘看板"):
    """数据、版式、D3全部内嵌；不加载实时客户端，不依赖本机服务。"""
    source = (ROOT / "dashboard.fragment.html").read_text(encoding="utf-8")
    breadth = snapshot.get("breadth_history") or {"items": [], "missing": 0}
    news = snapshot.get("sections", {}).get("news", {}).get("data") or {"items": [], "checked_at": snapshot.get("server_time", "")}
    for name, value in (("industry-market-data", snapshot), ("industry-breadth-data", breadth),
                        ("industry-news-data", news), ("industry-history-data", {"dates": [], "boards": []})):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
        source, count = re.subn(rf'(<script type="application/json" id="{name}">).*?(</script>)', lambda m: m[1] + payload + m[2], source, flags=re.S)
        if count != 1:
            raise ValueError("快照数据容器缺失: " + name)
    vendor = (ROOT / "workspace/vendor/d3.min.js").read_text(encoding="utf-8")
    source, count = re.subn(r'<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>', lambda _: '<script>' + vendor + '</script>', source)
    if count != 1:
        raise ValueError("图表依赖未成功内嵌")
    date = snapshot.get("market_session", {}).get("expected_date", "")
    captured = snapshot.get("server_time", "")
    title = escape(f"{date} · {label}")
    banner = escape(f"{label} · 保存时点 {captured.replace('T', ' ')[:19]} · 数据及版式已固定，打开后不自动更新。各区块保留原始行情时间。")
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + title + '</title><style>body{margin:0;background:#fcfbf8}main{max-width:1440px;margin:auto}.archive-banner{padding:14px 24px;border-bottom:2px solid #a51f34;font:15px "Times New Roman",SimSun,serif;color:#a51f34}</style>'
            '<script>globalThis.INDUSTRY_LIVE_MODE=false;</script></head><body><main><div class="archive-banner">' + banner + '</div>' + source + '</main></body></html>')


def freeze_dashboard(snapshot, destination=None):
    date = snapshot.get("market_session", {}).get("expected_date")
    captured = snapshot.get("server_time") or ""
    # 只截取本交易日15:00后的首个快照；周末或次日打开不改写历史界面。
    if not date or not captured.startswith(date + "T") or captured[11:16] < "15:00":
        return None
    folder = Path(destination or ARCHIVE) / date
    path = folder / "收盘看板.html"
    if path.exists():
        return path
    html = dashboard_html(snapshot)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as output:
            output.write(html)
    except FileExistsError:
        pass
    return path


def is_close(value, date):
    return bool(value and value.startswith(date + "T") and value[11:16] >= "15:00")


def valid_section(name, section, date):
    if not section.get("data") or not is_close(section.get("as_of"), date):
        return False
    if name in ("indices", "concepts", "fund_concepts", "communications"):
        items = section["data"].get("items", [])
        count = {"indices": 6, "concepts": 10, "fund_concepts": 10, "communications": 6}[name]
        if len(items) != count or not all(is_close(r.get("as_of"), date) for r in items):
            return False
        if name != "indices":
            return all(is_close(r.get("quote_as_of") or r.get("as_of"), date) and r.get("pct") is not None and all(r.get("latest", {}).get(k) is not None for k in ("main", "xl", "lg", "md", "sm")) for r in items)
    return True


def save_close(snapshot, destination=None):
    html_path = freeze_dashboard(snapshot, destination)
    session = snapshot.get("market_session", {})
    date = session.get("expected_date")
    if not date or session.get("phase") not in ("closed", "closed_today", "preopen"):
        return {"date": date, "status": "html_saved", "html_path": str(html_path), "missing_sections": []} if html_path else None
    folder = Path(destination or ARCHIVE) / date
    path = folder / "收盘快照.json"
    prior = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    sections = prior.get("sections", {})
    for name in REQUIRED:
        candidate = snapshot.get("sections", {}).get(name, {})
        if valid_section(name, candidate, date):
            if candidate.get("as_of", "") >= sections.get(name, {}).get("as_of", ""):
                sections[name] = deepcopy(candidate)
    missing = [k for k in REQUIRED if not valid_section(k, sections.get(k, {}), date)]
    result = {"date": date, "status": "partial" if missing else "complete", "missing_sections": missing,
              "sections": sections, "checked_at": stamp(), "fund_unit": "亿元",
              "note": "仅纳入该交易日15:00及之后的源行情；未齐区块继续重试，不用盘中值填充。"}
    # 新闻不属于收盘报价，独立保留它自己的发布时间和获取时间。
    result["news_snapshot"] = deepcopy(snapshot.get("sections", {}).get("news", {}))
    atomic_json(path, result)
    result["html_path"] = str(html_path) if html_path else None
    return result


if __name__ == "__main__":
    from build_preview import build
    build()
    # 优先复用运行中的服务，避免多个采集器同时改写缓存。
    import time
    import requests
    from live_data import DashboardStore
    try:
        session = requests.Session()
        session.trust_env = False
        base = "http://127.0.0.1:8765"
        session.get(base + "/api/health", timeout=3).raise_for_status()
        # 先固定此刻已呈现的看板，再触发数据补查；不让补查改写HTML。
        freeze_dashboard(session.get(base + "/api/snapshot", timeout=5).json())
        session.post(base + "/api/refresh", timeout=5).raise_for_status()
        for _ in range(90):
            snapshot = session.get(base + "/api/snapshot", timeout=5).json()
            if not snapshot.get("refreshing"):
                break
            time.sleep(2)
    except requests.RequestException:
        store = DashboardStore()
        store.refresh()
        snapshot = store.snapshot()
    result = save_close(snapshot)
    print(json.dumps({"archive": str(ARCHIVE), "date": (result or {}).get("date"),
                      "status": (result or {}).get("status", "market_not_closed"),
                      "html_path": (result or {}).get("html_path"),
                      "missing_sections": (result or {}).get("missing_sections", [])}, ensure_ascii=False))
