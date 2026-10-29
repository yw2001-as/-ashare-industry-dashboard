"""独立构建实时版式、离线快照和合成数据演示；无需Codex。"""
import json
from pathlib import Path
import re
from live_data import ROOT, DATA, CACHE, stamp, market_session, now, load_holidays


def embed(source, element, value):
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False).replace("</", "<" + chr(92) + "/")
    pattern = rf'(<script type="application/json" id="{element}">).*?(</script>)'
    source, count = re.subn(pattern, lambda m: m[1] + payload + m[2], source, flags=re.S)
    if count != 1: raise ValueError("数据容器不唯一: " + element)
    return source


def build():
    DATA.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    empty_news = {"checked_at": stamp(), "window_label": "等待真实资讯", "items": []}
    news_file = DATA / "news_snapshot.json"
    if not news_file.exists(): news_file.write_text(json.dumps(empty_news, ensure_ascii=False), encoding="utf-8")
    empty_breadth = {"scope": "沪深A股", "items": [], "missing": 0}
    path = CACHE / "live_snapshot.json"
    market = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sections": {}}
    path = DATA / "breadth_snapshot.json"
    breadth = json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty_breadth
    market.update(breadth_history=breadth, server_time=stamp(), market_session=market_session(now(), load_holidays()))
    news = market.get("sections", {}).get("news", {}).get("data") or empty_news
    source = (ROOT / "workspace/templates/dashboard.html").read_text(encoding="utf-8")
    for element, name in (("communications-panel", "communications_panel.js"), ("industry-fund-replay", "fund_replay.js"), ("industry-dashboard", "dashboard.js")):
        script = (ROOT / "workspace/scripts" / name).read_text(encoding="utf-8")
        source, count = re.subn(rf'(<script id="{element}">).*?(</script>)', lambda m: m[1] + script + m[2], source, flags=re.S)
        if count != 1: raise ValueError("脚本容器不唯一: " + element)
    cfg = json.loads((DATA / "communications_watch.json").read_text(encoding="utf-8"))
    for element, value in (("communications-config", cfg), ("industry-news-data", news), ("industry-history-data", {"dates": [], "boards": []}), ("industry-breadth-data", breadth), ("industry-market-data", market)):
        source = embed(source, element, value)
    (ROOT / "dashboard.fragment.html").write_text(source, encoding="utf-8")
    (ROOT / "index.html").write_text((ROOT / "workspace/templates/index.html").read_text(encoding="utf-8"), encoding="utf-8")
    from closing_archive import dashboard_html
    (ROOT / "snapshot.html").write_text(dashboard_html(market, "本机静态快照"), encoding="utf-8")
    # 演示只装配合成数据生成器，完全不读取本机真实行情。
    clean = (ROOT / "workspace/templates/dashboard.html").read_text(encoding="utf-8")
    for element, value in (("communications-config", cfg), ("industry-news-data", empty_news), ("industry-history-data", {"dates": [], "boards": []}), ("industry-breadth-data", empty_breadth), ("industry-market-data", {"sections": {}})):
        clean = embed(clean, element, value)
    demo = (ROOT / "workspace/scripts/demo-data.js").read_text(encoding="utf-8")
    for element, name in (("communications-panel", "communications_panel.js"), ("industry-fund-replay", "fund_replay.js"), ("industry-dashboard", "dashboard.js")):
        script = (ROOT / "workspace/scripts" / name).read_text(encoding="utf-8")
        clean = clean.replace('<script id="' + element + '"></script>', '<script id="' + element + '">' + script + '</script>')
    clean = clean.replace('<script id="communications-panel">', '<script>' + demo + '</script><script id="communications-panel">', 1)
    vendor = (ROOT / "workspace/vendor/d3.min.js").read_text(encoding="utf-8")
    clean = clean.replace('<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>', '<script>' + vendor + '</script>')
    clean += '<script>document.querySelector("footer .demo").textContent="全部为合成演示数据，不代表真实行情、资金流或投资建议。";document.querySelector(".breadth-source").textContent="合成演示数据 · 用于展示30日市场宽度版式，不代表实际市场统计。";</script>'
    document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A股产业轮动看板 · 合成数据演示</title><style>body{margin:0;background:#fcfbf8}main{max-width:1440px;margin:auto}.demo-banner{position:sticky;top:0;z-index:100;background:#fcfbf8;padding:16px 24px;border-bottom:2px solid #a51f34;font:16px "Times New Roman",SimSun,serif;color:#a51f34}</style><script>globalThis.INDUSTRY_LIVE_MODE=false;</script></head><body><main><div class="demo-banner">DEMO / 全部为合成演示数据 · 可离线交互 · 不代表真实行情</div>' + clean + '</main></body></html>'
    target = ROOT / "examples/demo.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    return ROOT / "dashboard.fragment.html"


if __name__ == "__main__":
    print(build())
