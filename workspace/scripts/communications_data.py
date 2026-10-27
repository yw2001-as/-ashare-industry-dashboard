"""固定通信观察池：与每日涨幅Top10独立；所有计算保留原始日期及缺测。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
import re
import time

from live_data import CACHE, DATA, TZ, atomic_json, get, load_holidays, market_session, now, number, parse_fund_lines, stamp

FIELDS = (("main", "f62"), ("xl", "f66"), ("lg", "f72"), ("md", "f78"), ("sm", "f84"))


def config():
    return json.loads((DATA / "communications_watch.json").read_text(encoding="utf-8"))


def parse_quotes(payload, requested):
    rows = (payload.get("data") or {}).get("diff") or []
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    result = {}
    for row in rows:
        code = row.get("f12")
        if code not in requested or row.get("f14") != requested[code]:
            continue
        ts, pct = number(row.get("f124")), number(row.get("f3"))
        if ts is None or pct is None:
            continue
        result[code] = {"id": code, "pct": pct, "as_of": datetime.fromtimestamp(ts, TZ).isoformat(),
                        "latest": {key: None if number(row.get(field)) is None else number(row[field]) / 1e8 for key, field in FIELDS}}
    return result


def fetch_history(code):
    path = CACHE / "communications" / (code + "-history.json")
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if old.get("days") and path.exists() and time.time() - path.stat().st_mtime < 900:
        return old.get("days", [])
    days, error = {}, False
    try:
        payload = get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get", {
            "secid": "90." + code, "lmt": 10, "klt": 101, "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63"}).json()
        if (payload.get("data") or {}).get("code") != code:
            raise ValueError("历史资金板块代码不一致")
        days = {r["date"]: r for r in parse_fund_lines(payload["data"].get("klines", []), daily=True)}
    except Exception:
        error = True
    if not days or any(v.get("pct_change") is None for v in days.values()):
        try:
            payload = get("https://91.push2his.eastmoney.com/api/qt/stock/kline/get", {
                "secid": "90." + code, "lmt": 10, "klt": 101, "fqt": 0, "end": "20500101",
                "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}).json()
            if (payload.get("data") or {}).get("code") != code:
                raise ValueError("历史日K板块代码不一致")
            for line in payload["data"].get("klines", []):
                fields = line.split(",")
                if len(fields) > 8 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields[0]) and number(fields[8]) is not None:
                    row = days.setdefault(fields[0], {"date": fields[0], "main_net_inflow_yi": None})
                    row["pct_change"] = number(fields[8])
        except Exception:
            error = True
    # 独立字段合并，失败或较短响应不抹去先前成功获取的历史。
    merged = {r["date"]: dict(r) for r in old.get("days", [])}
    for day, row in days.items():
        previous = merged.setdefault(day, {"date": day})
        previous.update({k: v for k, v in row.items() if v is not None})
    result = [merged[k] for k in sorted(merged)][-20:]
    atomic_json(path, {"id": code, "days": result, "checked_at": stamp(), "partial": error})
    return result


def parse_stocks(text, codes):
    result = {}
    for _, body in re.findall(r'v_(\w+)="([^"]*)"', text):
        f = body.split("~")
        if len(f) < 35 or f[2] not in codes or not re.fullmatch(r"\d{14}", f[30]):
            continue
        price, pct = number(f[3]), number(f[32])
        if price is None or price <= 0 or pct is None:
            continue
        result[f[2]] = {"code": f[2], "name": f[1], "price": price, "pct": pct,
                          "as_of": datetime.strptime(f[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ).isoformat()}
    return result


def window_stats(days):
    pcts = [number(r.get("pct_change")) for r in days]
    flows = [number(r.get("main_net_inflow_yi")) for r in days]
    full_pct = len(days) == 5 and all(p is not None for p in pcts)
    full_flow = len(days) == 5 and all(f is not None for f in flows)
    return {"pct_5d": (math.prod(1 + p / 100 for p in pcts) - 1) * 100 if full_pct else None,
            "flow_5d": sum(flows) if full_flow else None,
            "inflow_days": sum(f > 0 for f in flows) if full_flow else None,
            "pct_coverage": sum(p is not None for p in pcts), "flow_coverage": sum(f is not None for f in flows)}


def assessment(row, target):
    pct, flow = number(row.get("pct")), number((row.get("latest") or {}).get("main"))
    if not row.get("as_of", "").startswith(target or "INVALID"):
        return {"label": "日期待更新", "tone": "muted", "reason": "板块行情不是目标交易日，保留原时间，暂不判断强弱。"}
    if pct is None or flow is None:
        return {"label": "等待资金数据", "tone": "muted", "reason": "当前价格或资金缺测，不据此判断持续性。"}
    label = "单日价资同向" if pct > 0 and flow > 0 else "上涨·资金流出" if pct > 0 and flow < 0 else "资金流入·价未强" if flow > 0 else "单日偏弱" if pct < 0 and flow < 0 else "单日信号中性"
    stats = row["stats"]
    if stats["flow_coverage"] < 5 or stats["pct_coverage"] < 5:
        reason = f"近5日资金仅{stats['flow_coverage']}/5日可用、涨幅{stats['pct_coverage']}/5日可用，持续性待核验。"
    else:
        reason = f"近5日累计涨幅{stats['pct_5d']:+.2f}%，主力净额{stats['flow_5d']:+.2f}亿元，{stats['inflow_days']}/5日净流入。"
        if stats["pct_5d"] < 0 and stats["flow_5d"] < 0:
            reason += "5日价格与资金仍偏弱，单日回流不足以确认持续趋势。"
        elif stats["pct_5d"] > 0 and stats["flow_5d"] > 0:
            reason += "5日价格与资金同向改善，仍需结合产业兑现与介入位置。"
        else:
            reason += "5日价格与资金尚未同步，继续核实承接。"
    return {"label": label, "tone": "positive" if pct > 0 and flow > 0 else "negative", "reason": reason}


def fetch_communications(calendar):
    settings = config()
    target = market_session(now(), load_holidays()).get("expected_date")
    dates = sorted({d for d in [*calendar, target] if d and d <= (target or "")})[-5:]
    path = CACHE / "communications" / "quotes.json"
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"boards": {}, "stocks": {}}
    archive_path = CACHE / "communications" / "observed-closes.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {}
    boards, stocks = dict(cached.get("boards", {})), dict(cached.get("stocks", {}))
    requested = {r["id"]: r["provider_name"] for r in settings["items"]}
    fresh = {}
    try:
        fresh = parse_quotes(get("https://push2.eastmoney.com/api/qt/ulist.np/get", {
            "secids": ",".join("90." + c for c in requested), "fltt": 2, "invt": 2,
            "fields": "f12,f14,f3,f62,f66,f72,f78,f84,f124", "ut": "bd1d9ddb04089700cf9c27f6f7426281"}).json(), requested)
        for code, row in fresh.items():
            if row["as_of"] >= boards.get(code, {}).get("as_of", ""):
                boards[code] = row
    except Exception:
        pass
    stock_codes = {s["code"] for item in settings["items"] for s in item["stocks"]}
    try:
        response = get("https://qt.gtimg.cn/q=" + ",".join(("sh" if c.startswith("6") else "sz") + c for c in sorted(stock_codes)))
        response.encoding = "gbk"
        for code, quote in parse_stocks(response.text, stock_codes).items():
            if quote["as_of"] >= stocks.get(code, {}).get("as_of", ""):
                stocks[code] = quote
    except Exception:
        pass
    with ThreadPoolExecutor(max_workers=3) as pool:
        histories = dict(zip(requested, pool.map(fetch_history, requested)))
    items = []
    for setting in settings["items"]:
        quote = boards.get(setting["id"], {})
        row = {**setting, **quote, "name": setting["name"], "quote_status": "ok" if setting["id"] in fresh else "cached" if quote else "unavailable"}
        daily = {r["date"]: dict(r) for r in histories[setting["id"]]}
        for archived in archive.get(setting["id"], {}).values():
            previous = daily.setdefault(archived["date"], dict(archived))
            for key in ("pct_change", "main_net_inflow_yi"):
                if previous.get(key) is None:
                    previous[key] = archived.get(key)
        # 只更新其自身行情日期；旧缓存绝不反填今天。
        if quote.get("as_of"):
            day = quote["as_of"][:10]
            daily[day] = {"date": day, "pct_change": quote["pct"], "main_net_inflow_yi": quote["latest"]["main"], "as_of": quote["as_of"]}
            if quote["as_of"][11:16] >= "15:00":
                archive.setdefault(setting["id"], {})[day] = {**daily[day], "source": "本机收盘行情归档"}
        row["days"] = [daily.get(day, {"date": day, "pct_change": None, "main_net_inflow_yi": None}) for day in dates]
        row["stats"] = window_stats(row["days"])
        row["assessment"] = assessment(row, target)
        row["stocks"] = [{**s, **stocks.get(s["code"], {})} for s in setting["stocks"]]
        items.append(row)
    atomic_json(path, {"boards": boards, "stocks": stocks})
    atomic_json(archive_path, archive)
    times = [r["as_of"] for r in items if r.get("as_of")]
    return {"items": items, "dates": dates, "target_date": target, "classification": settings["classification"],
            "fresh_boards": len(fresh), "checked_at": stamp()}, min(times) if times else None, "东方财富固定概念行情及历史；腾讯代表股报价；公司披露用于产业观察说明"
