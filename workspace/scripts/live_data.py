"""本机看板的公开数据适配及缓存。失败保留原时间，缺测不填零。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html import unescape
import json
import math
from pathlib import Path
import re
import threading
import time
import uuid

from bs4 import BeautifulSoup
import requests

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "workspace/data"
CACHE = ROOT / "workspace/cache"
TZ = timezone(timedelta(hours=8))
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
FUND_CACHE_LOCK = threading.RLock()
INDEX_CODES = ["sh000001", "sz399001", "sz399006", "sh000300", "sh000852", "sh000688"]
EXCLUDED = ("昨日", "融资融券", "沪股通", "深股通", "MSCI", "富时", "标普", "ST板块", "转债", "沪深300", "上证50", "中证500", "中证1000", "AH股", "B股", "破净股", "低价股", "高价股", "百元股", "机构重仓", "基金重仓", "社保重仓", "QFII重仓", "预盈预增", "预亏预减")
EXCLUDED += ("ST股", "标准普尔", "HS300", "上证", "深成", "深证100", "创业成份", "创业板综", "央视50", "中证", "大盘", "小盘", "中盘", "微盘", "价值股", "成长股", "权重股", "市净率", "股权分散", "股权集中", "行业龙头", "题材股", "周期股", "风格", "次新股", "近期", "历史新高", "百日新高", "最近多板", "重仓", "新进", "减仓", "增仓", "预增", "预减", "首亏", "扭亏", "破发", "破增发", "破净", "密集调研", "证金持股", "股权激励", "大基金持股", "反转股", "超跌股", "趋势股", "高换手", "高振幅", "东方财富热股")
# 概念目录也包含选股组合、风格及泛受益标签，不属于产业/技术/业务细分。
EXCLUDED += ("金股", "茅指数", "宁组合", "红利股", "IPO受益", "贬值受益", "股权转让")


def now():
    return datetime.now(TZ)


def stamp():
    return now().isoformat(timespec="seconds")


def parse_exchange_holidays(html, year):
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    marker = re.search(rf"{year}\s*年休市安排", text)
    if not marker:
        raise ValueError("交易所尚未返回该年度休市表")
    text = text[marker.end():].split("相关公告")[0]
    intervals = []
    for month, start, end_month, end in re.findall(r"(\d{1,2})月(\d{1,2})日[（(]星期.[）)]至(?:(\d{1,2})月)?(\d{1,2})日", text):
        begin = f"{year}-{int(month):02}-{int(start):02}"
        finish = f"{year}-{int(end_month or month):02}-{int(end):02}"
        intervals.append([begin, finish])
    if len(intervals) < 6:
        raise ValueError("交易所年度休市区间未完整返回")
    return {"year": year, "source": "上海证券交易所年度休市安排", "url": "https://www.sse.com.cn/disclosure/dealinstruc/closed/", "closed_ranges": intervals}


def load_holidays():
    path = DATA / "exchange_holidays.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value["year"] != now().year:
        try:
            value = parse_exchange_holidays(get("https://www.sse.com.cn/disclosure/dealinstruc/closed/").text, now().year)
            atomic_json(path, value)
        except Exception:
            pass  # 不把未核实的未来年份工作日自动当作交易日。
    return value


def market_session(at, holidays):
    at = at.astimezone(TZ)
    known = at.year == holidays["year"]

    def closed(day):
        iso = day.isoformat()
        return day.weekday() >= 5 or any(start <= iso <= end for start, end in holidays["closed_ranges"])

    day, hm = at.date(), at.strftime("%H:%M")
    if not known and day.weekday() < 5:
        return {"phase": "unknown", "label": "年度交易日历待核验", "expected_date": None}
    if closed(day):
        phase, label = "closed", "休市"
    elif hm < "09:30":
        phase, label = "preopen", "开盘前"
    elif hm <= "11:30" or "13:00" <= hm <= "15:00":
        phase, label = "trading", "盘中"
    elif hm < "13:00":
        phase, label = "lunch", "午间休市"
    else:
        phase, label = "closed_today", "已收盘"
    target = day
    if phase in ("closed", "preopen"):
        target -= timedelta(days=1)
        while closed(target):
            target -= timedelta(days=1)
    return {"phase": phase, "label": label, "expected_date": target.isoformat() if known else None}


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def get(url, params=None):
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=(4, 9))
        response.raise_for_status()
    except requests.RequestException:
        # 代理通道会对公开行情返回502/证书错误；直连仍保持HTTPS证书验证。
        with requests.Session() as direct:
            direct.trust_env = False
            response = direct.get(url, params=params, timeout=(4, 9))
            response.raise_for_status()
    return response


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def trading_minute(hhmm):
    text = hhmm.replace(":", "")
    minute = int(text[:2]) * 60 + int(text[2:4])
    return min(240, max(0, minute - 570 if minute <= 690 else minute - 780 + 120))


def parse_qq(text):
    records = []
    for code, body in re.findall(r'v_(\w+)="([^"]*)"', text):
        fields = body.split("~")
        if len(fields) < 38 or not re.fullmatch(r"\d{14}", fields[30]):
            continue
        price, previous, pct = number(fields[3]), number(fields[4]), number(fields[32])
        if price is None or previous is None or previous <= 0 or pct is None:
            continue
        records.append({"id": code, "name": fields[1], "price": price, "previous": previous,
                        "pct": pct, "as_of": datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ).isoformat(),
                        "amount_yi": None if number(fields[37]) is None else number(fields[37]) / 10000,
                        "points": []})
    if not records:
        raise ValueError("指数返回空行情或缺少行情日期")
    return records


def index_minutes(record):
    payload = get("https://web.ifzq.gtimg.cn/appstock/app/minute/query", {"code": record["id"]}).json()
    data = payload["data"][record["id"]]["data"]
    date = str(data.get("date", "")).replace("-", "")
    if date != record["as_of"][:10].replace("-", ""):
        raise ValueError("指数分时和快照日期不同")
    points = []
    for line in data.get("data", []):
        parts = line.split()
        price = number(parts[1]) if len(parts) > 1 else None
        if price is not None:
            points.append({"t": trading_minute(parts[0]), "v": (price / record["previous"] - 1) * 100})
    return points


def fetch_indices():
    response = get("https://qt.gtimg.cn/q=" + ",".join(INDEX_CODES + ["sz399106"]))
    response.encoding = "gbk"
    records = parse_qq(response.text)
    lookup = {r["id"]: r for r in records}
    visible = [lookup[c] for c in INDEX_CODES if c in lookup]
    if len(visible) != 6:
        raise ValueError("六个指数未完整返回")
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(index_minutes, r): r for r in visible}
        for future in as_completed(futures):
            try:
                futures[future]["points"] = future.result()
            except Exception:
                pass  # 没有分时就留空，不绘制合成分时。
    turnover = None
    a, b = lookup.get("sh000001"), lookup.get("sz399106")
    if a and b and a["as_of"][:10] == b["as_of"][:10] and a["amount_yi"] is not None and b["amount_yi"] is not None:
        turnover = a["amount_yi"] + b["amount_yi"]
    return {"items": visible, "turnover_yi": turnover}, min(r["as_of"] for r in visible), "腾讯公开指数行情"


def parse_breadth(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("涨跌家数表未返回")
    pairs = {}
    for row in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        for i in range(0, len(cells) - 1, 2):
            pairs[cells[i]] = cells[i + 1].replace(",", "")
    date_node = soup.select_one(".market-activity-time") or soup.select_one(".market-activity-meta")
    found = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", date_node.get_text(" ", strip=True) if date_node else "")
    if not found:
        raise ValueError("涨跌家数缺少统计时间")
    values = {}
    for key, label in (("up", "上涨"), ("down", "下跌"), ("flat", "平盘"), ("paused", "停牌"), ("limit_up", "涨停"), ("limit_down", "跌停")):
        value = number(pairs.get(label))
        values[key] = int(value) if value is not None and value >= 0 and value.is_integer() else None
    if values["up"] is None or values["down"] is None or values["up"] + values["down"] < 100:
        raise ValueError("涨跌家数未完整返回")
    as_of = datetime.strptime(found[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ).isoformat()
    values.update(date=as_of[:10], observed_at=as_of, source="乐咕乐股", scope="沪深A股", provisional=as_of[11:16] < "15:00")
    return values, as_of, "乐咕乐股赚钱效应统计"


def fetch_breadth():
    return parse_breadth(get("https://legulegu.com/stockdata/market-activity").text)


def fetch_calendar():
    payload = get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", {"param": "sh000001,day,,,60,qfq"}).json()
    days = payload["data"]["sh000001"]["day"]
    result = sorted({row[0] for row in days if re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0])})
    if len(result) < 30:
        raise ValueError("交易日历不足30日")
    return result


def seed_archived_breadth():
    """独立保存本项目采集的历史；首次启动允许为空，不读取其他项目。"""
    path = DATA / "breadth_history.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    result = {"scope": "沪深A股", "items": saved.get("items", []), "calendar": saved.get("calendar", [])}
    atomic_json(path, result)
    return result


def parse_fund_lines(lines, daily=False):
    result = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        vals = [number(p) for p in parts[1:6]]
        if any(v is None for v in vals):
            continue
        main, small, middle, large, extra = (v / 1e8 for v in vals)
        if daily:
            result.append({"date": parts[0], "pct_change": number(parts[12]) if len(parts) > 12 else None,
                           "main_net_inflow_yi": main})
        else:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", parts[0]):
                continue
            result.append({"t": trading_minute(parts[0][11:]), "as_of": parts[0].replace(" ", "T") + ":00+08:00",
                           "main": main, "sm": small, "md": middle, "lg": large, "xl": extra})
    return result


def fetch_board_series(code):
    params = {"secid": "90." + code, "lmt": 0, "klt": 1, "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56"}
    error = None
    for host in ("push2.eastmoney.com", "79.push2.eastmoney.com"):
        try:
            intraday = get("https://" + host + "/api/qt/stock/fflow/kline/get", params).json()
            if (intraday.get("data") or {}).get("code") != code:
                raise ValueError("返回的资金轨迹代码与请求板块不同")
            values = parse_fund_lines((intraday.get("data") or {}).get("klines", []))
            if not values:
                raise ValueError("资金分时未返回")
            return values
        except Exception as exc:
            error = exc
    raise error


def repair_fund_series(sections, target):
    """榜单失败时独立恢复当前名单分时；相同板块仅请求一次，两榜共享实测记录。"""
    requested = {}
    for name in ("concepts", "fund_concepts"):
        section = sections.get(name, {})
        if section.get("status") in ("ok", "cached_close"):
            continue  # 成功榜单本轮已经提取分时，不重复发请求。
        for board in section.get("data", {}).get("items", []):
            if re.fullmatch(r"BK\d+", board.get("id", "")) and (board.get("as_of") or "").startswith(target or "INVALID"):
                requested[board["id"]] = board
    if not requested:
        return
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_board_series, code): code for code in requested}
        for job in as_completed(jobs):
            code = jobs[job]
            try:
                values = job.result()
                if values and all((r.get("as_of") or "").startswith(target + "T") for r in values):
                    results[code] = values
            except Exception:
                pass
    for name in ("concepts", "fund_concepts"):
        section = sections.get(name, {})
        for board in section.get("data", {}).get("items", []):
            if board.get("id") not in requested or not (board.get("as_of") or "").startswith(target):
                continue
            board["values"] = [*board.get("values", []), *results.get(board["id"], [])]
            retain_board_funds(board)
            minutes = [r for r in board["values"] if r.get("kind", "series") == "series"]
            board["series_as_of"] = max((r["as_of"] for r in minutes), default=None)
        if requested:
            section["funds_checked_at"] = stamp()


def retain_board_funds(board):
    """按交易日和板块保留真实分时及报价采样；接口失败不删除旧记录。"""
    code, as_of = board.get("id", ""), board.get("as_of") or ""
    day = as_of[:10]
    if not re.fullmatch(r"BK\d+", code) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return
    path = CACHE / "funds" / day / (code + ".json")
    with FUND_CACHE_LOCK:
        existing = {}
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
        rows = existing.get("values", []) if existing.get("id") == code and existing.get("date") == day else []
        rows = [*rows, *board.get("values", [])]
        latest = board.get("latest", {})
        if number(latest.get("main")) is not None and as_of[11:16] >= "09:30":
            clock = int(as_of[11:13]) * 60 + int(as_of[14:16]) + int(as_of[17:19] or 0) / 60
            raw = clock - 570 if clock <= 690 else 120 if clock < 780 else clock - 780 + 120
            rows.append({**latest, "t": min(240, raw), "rawMinute": raw, "as_of": as_of, "kind": "quote"})
        valid = {}
        for row in rows:
            ts = row.get("as_of", "")
            t = number(row.get("t"))
            if not ts.startswith(day + "T") or t is None or not 0 <= t <= 240 or number(row.get("main")) is None:
                continue
            previous = valid.get(ts)
            if not previous or row.get("kind", "series") == "series":
                valid[ts] = row
        board["values"] = sorted(valid.values(), key=lambda r: (r["t"], r["as_of"]))
        atomic_json(path, {"id": code, "date": day, "values": board["values"]})


def fetch_board_history(code):
    cache = CACHE / (code + "-daily.json")
    old = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else []
    old = merge_history(local_board_closes(code), old)
    if old and cache.exists() and time.time() - cache.stat().st_mtime < 900 and all(r.get("pct_change") is not None and r.get("main_net_inflow_yi") is not None for r in old[-5:]):
        return old
    days = []
    try:
        payload = get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get", {
            "secid": "90." + code, "lmt": 10, "klt": 101, "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63"}).json()
        if (payload.get("data") or {}).get("code") != code:
            raise ValueError("历史资金板块代码不一致")
        days = parse_fund_lines((payload.get("data") or {}).get("klines", []), daily=True)
        if not days:
            raise ValueError("历史资金空响应")
    except Exception:
        pass
    if not days or any(r.get("pct_change") is None for r in days):
        # 同一概念指数的日K可独立恢复每日涨跌幅；不据此推算资金净额。
        try:
            payload = get("https://91.push2his.eastmoney.com/api/qt/stock/kline/get", {
            "secid": "90." + code, "lmt": 10, "klt": 101, "fqt": 0, "end": "20500101",
            "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}).json()
            if (payload.get("data") or {}).get("code") != code:
                raise ValueError("历史日K板块代码不一致")
            for line in (payload.get("data") or {}).get("klines", []):
                fields = line.split(",")
                if len(fields) > 8 and number(fields[8]) is not None:
                    days.append({"date": fields[0], "pct_change": number(fields[8]), "main_net_inflow_yi": None})
        except Exception:
            pass
    merged = merge_history(old, days)
    if days:
        atomic_json(cache, merged)
    return merged


def local_board_closes(code):
    rows = []
    for path in sorted((CACHE / "closing").glob("*.json"))[-60:]:
        saved = json.loads(path.read_text(encoding="utf-8"))
        sections = saved.get("sections", {})
        for board in [*sections.get("concepts", {}).get("data", {}).get("items", []), *sections.get("fund_concepts", {}).get("data", {}).get("items", [])]:
            observed = board.get("as_of") or ""
            quoted = board.get("quote_as_of") or observed
            if board.get("id") == code and observed.startswith(path.stem) and observed[11:16] >= "15:00" and quoted.startswith(path.stem) and quoted[11:16] >= "15:00":
                rows.append({"date": path.stem, "pct_change": board.get("pct"), "main_net_inflow_yi": board.get("latest", {}).get("main")})
    # 真实15:00资金轨迹也能独立补回资金；不据此生成涨跌幅。
    for path in sorted((CACHE / "funds").glob("*/" + code + ".json"))[-60:]:
        saved = json.loads(path.read_text(encoding="utf-8"))
        date = path.parent.name
        if saved.get("id") != code or saved.get("date") != date:
            continue
        closes = [r for r in saved.get("values", []) if r.get("t") == 240 and (r.get("as_of") or "").startswith(date) and r["as_of"][11:16] >= "15:00" and number(r.get("main")) is not None]
        minutes = [r for r in closes if r.get("kind", "series") == "series"]
        if closes:
            row = max(minutes or closes, key=lambda r: r["as_of"])
            rows.append({"date": date, "main_net_inflow_yi": row["main"]})
    return merge_history(rows)


def merge_history(*groups):
    merged = {}
    for rows in groups:
        for row in rows:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.get("date", "")):
                merged.setdefault(row["date"], {}).update({k: v for k, v in row.items() if v is not None})
    return [merged[k] for k in sorted(merged)][-60:]


def repair_concept_history(section):
    """榜单失败也继续补取当前名单的历史；不修改榜单时间和资金分时。"""
    boards = [b for b in section.get("data", {}).get("items", []) if re.fullmatch(r"BK\d+", b.get("id", ""))]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(fetch_board_history, b["id"]): b for b in boards}
        for job in as_completed(jobs):
            board = jobs[job]
            try:
                board["days"] = merge_history(board.get("days", []), job.result())
            except Exception:
                pass


def parse_concept_inventory(html):
    soup = BeautifulSoup(html, "html.parser")
    popup = soup.select_one(".bkselectorpop")
    if popup is None:
        raise ValueError("官方概念目录缺失")
    labels = [li.get_text(strip=True) for li in popup.select(".pop_slider li")]
    panes = popup.select(".pop-cont")
    if "概念" not in labels or labels.index("概念") >= len(panes):
        raise ValueError("无法区分概念、行业和地域目录")
    entries = {}
    for anchor in panes[labels.index("概念")].find_all("a", href=True):
        match = re.fullmatch(r"/bkzj/(BK\d+)\.html", anchor["href"])
        if match:
            entries[match[1]] = anchor.get_text(strip=True)
    if len(entries) < 10:
        raise ValueError("概念目录不足10个")
    return entries


def concept_inventory():
    path = CACHE / "concept-inventory.json"
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return json.loads(path.read_text(encoding="utf-8"))["items"]
    entries = parse_concept_inventory(get("https://data.eastmoney.com/bkzj/gn.html").text)
    atomic_json(path, {"items": entries, "source": "https://data.eastmoney.com/bkzj/gn.html", "retrieved_at": stamp()})
    return entries


def batch_concept_quotes():
    """同一东财概念全集的备用报价通道；完整取齐后才计算Top10。"""
    inventory = concept_inventory()
    codes = sorted(inventory)

    def batch(chunk):
        payload = get("https://push2.eastmoney.com/api/qt/ulist.np/get", {
            "secids": ",".join("90." + c for c in chunk), "fltt": 2, "invt": 2,
            "fields": "f12,f14,f3,f62,f66,f72,f78,f84,f124", "ut": "bd1d9ddb04089700cf9c27f6f7426281"}).json()
        rows = (payload.get("data") or {}).get("diff") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        if {r.get("f12") for r in rows} != set(chunk):
            raise ValueError("概念批量行情未完整返回，不能据此宣称全市场Top10")
        return rows

    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(batch, codes[i:i + 80]) for i in range(0, len(codes), 80)]
        for future in as_completed(futures):
            rows.extend(future.result())
    return rows, len(inventory)


def select_concept_rows(diff, order="pct"):
    field = "f62" if order == "flow" else "f3"
    rows = [r for r in diff if re.fullmatch(r"BK\d+", str(r.get("f12", ""))) and number(r.get("f3")) is not None and number(r.get(field)) is not None and number(r.get("f124")) is not None and not any(x in str(r.get("f14", "")) for x in EXCLUDED)]
    rows.sort(key=lambda r: (-float(r[field]), str(r["f12"])))
    if len(rows) < 10:
        raise ValueError("概念榜不足10个有效主题")
    return rows[:10]


def fetch_fund_concepts():
    return fetch_concepts(order="flow")


def fetch_concepts(order="pct"):
    field = "f62" if order == "flow" else "f3"
    label = "主力资金净流入榜" if order == "flow" else "涨幅榜"
    params = {"pn": 1, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": field,
              "fs": "m:90 t:3", "fields": "f12,f14,f3,f62,f66,f72,f78,f84,f124"}
    route, universe = label, None
    try:
        payload = get("https://push2.eastmoney.com/api/qt/clist/get", params).json()
        diff = (payload.get("data") or {}).get("diff") or []
        if not diff:
            raise ValueError("榜单空响应")
    except Exception:
        try:
            # 同一概念范围的标准榜单入口；风格标签仍由同一过滤规则剔除。
            payload = get("https://79.push2.eastmoney.com/api/qt/clist/get", params).json()
            diff = (payload.get("data") or {}).get("diff") or []
            if not diff:
                raise ValueError("备用榜单空响应")
            route = label + "（标准概念入口）"
        except Exception:
            diff, universe = batch_concept_quotes()
            route = "官方概念全集 + 批量行情"
    if isinstance(diff, dict):
        diff = list(diff.values())
    return enrich_concepts(diff, order, route, universe)


def enrich_concepts(diff, order, route, universe=None):
    label = "主力资金净流入榜" if order == "flow" else "涨幅榜"
    rows = select_concept_rows(diff, order)
    boards = []
    for row in rows[:10]:
        ts = number(row.get("f124"))
        as_of = datetime.fromtimestamp(ts, TZ).isoformat() if ts else None
        funds = {key: None if number(row.get(field)) is None else number(row[field]) / 1e8 for key, field in (("main", "f62"), ("xl", "f66"), ("lg", "f72"), ("md", "f78"), ("sm", "f84"))}
        boards.append({"id": row["f12"], "name": row["f14"], "pct": float(row["f3"]), "as_of": as_of,
                       "ranking_main": funds["main"], "latest": funds, "values": [], "days": [], "errors": []})
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(func, b["id"]): (b, field) for b in boards for func, field in ((fetch_board_series, "values"), (fetch_board_history, "days"))}
        for job in as_completed(jobs):
            board, field = jobs[job]
            try:
                board[field] = job.result()
                if field == "values" and board["as_of"] and any(v["as_of"][:10] != board["as_of"][:10] for v in board[field]):
                    board[field] = []
                    board["errors"].append("资金轨迹日期不一致")
            except Exception:
                board["errors"].append("资金分时缺测" if field == "values" else "历史缺测")
    session = market_session(now(), load_holidays())
    for board in boards:
        board["quote_as_of"] = board["as_of"]
        retain_board_funds(board)
        minute_rows = [v for v in board["values"] if v.get("kind", "series") == "series"]
        if session["phase"] in ("closed", "preopen", "closed_today") and minute_rows:
            last = minute_rows[-1]
            if last["t"] == 240 and last["as_of"].startswith(session["expected_date"] or "INVALID") and board["as_of"] and board["as_of"][:10] == last["as_of"][:10]:
                board["latest"] = {key: last[key] for key in ("main", "xl", "lg", "md", "sm")}
                board["as_of"] = last["as_of"]
    times = [b["as_of"] for b in boards if b["as_of"]]
    return {"items": boards, "transport": route, "universe_count": universe, "ranking": order}, min(times) if times else None, "东方财富概念板块，" + label + "，过滤风格标签；" + route


def clean_text(text):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def fetch_news():
    payload = get("https://np-weblist.eastmoney.com/comm/web/getFastNewsList", {
        "client": "web", "biz": "web_724", "fastColumn": "102", "sortEnd": "", "pageSize": "200", "req_trace": "1710315450384"}).json()
    candidates = payload["data"]["fastNewsList"]
    overseas = re.compile("美国|美联储|美股|美债|纳斯达克|标普|道指|欧洲|欧央行|欧洲央行|日本|日央行|英国|英央行|美元|日元|欧元|国际|原油|WTI|布伦特|COMEX|OPEC|关税|特朗普|鲍威尔|IMF|全球")
    market_terms = re.compile("股|债|金融|利率|央行|经济|银行|GDP|CPI|PMI|PPI|通胀|原油|油价|OPEC|贸易|制裁|关税|商品|投资|财政|货币|就业|资本|市场|财报|美联储|评级|美元|日元|欧元|黄金|白银|科技|出口|进口")
    domestic = re.compile("央行|财政|证监会|国务院|发改委|统计局|工信部|宏观|经济|货币|利率|LPR|MLF|GDP|PMI|CPI|PPI|消费|人民币|A股|沪指|深证|创业板|北交所|交易所|社融|流动性|地方债|国债|出口|进口|金融|楼市|房地产|政策|市场|会议|制造业")
    groups = {"domestic": [], "overseas": []}
    for row in sorted(candidates, key=lambda r: r.get("showTime", ""), reverse=True):
        title, summary = clean_text(row.get("title")), clean_text(row.get("summary"))
        code = str(row.get("code", ""))
        published = str(row.get("showTime", ""))
        if not re.fullmatch(r"\d+", code) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", published):
            continue
        region = "overseas" if overseas.search(title) and market_terms.search(title) else "domestic" if not overseas.search(title) and domestic.search(title) else None
        if not region or len(groups[region]) >= 3:
            continue
        groups[region].append({"region": region, "category": "海外宏观与市场" if region == "overseas" else "国内宏观与市场",
                               "title": title, "summary": summary[:115] + ("…" if len(summary) > 115 else ""),
                               "source": "东方财富7×24快讯", "published_at": published.replace(" ", "T") + "+08:00",
                               "published_label": published[5:16], "url": "https://finance.eastmoney.com/a/" + code + ".html"})
    items = groups["domestic"] + groups["overseas"]
    if not items:
        raise ValueError("未返回宏观与市场快讯")
    return {"items": items, "checked_at": stamp(), "window_label": "滚动快讯", "timezone": "Asia/Shanghai"}, max(n["published_at"] for n in items), "东方财富7×24公开财经快讯"


def fetch_communications(calendar):
    from communications_data import fetch_communications as collect
    return collect(calendar)


class DashboardStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.refresh_lock = threading.Lock()
        self.history = seed_archived_breadth()
        self.holidays = load_holidays()
        self.path = CACHE / "live_snapshot.json"
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"sections": {}}
        self.state.update(app="industry-review-local-v1", refresh_seconds=60, refreshing=False)
        session = market_session(now(), self.holidays)
        target = session.get("expected_date")
        closing_file = CACHE / "closing" / (target + ".json") if target else None
        if closing_file and closing_file.exists():
            closing = json.loads(closing_file.read_text(encoding="utf-8"))
            for name, section in closing["sections"].items():
                old = self.state["sections"].get(name, {})
                if not old.get("as_of", "").startswith(target) or not old.get("data"):
                    self.state["sections"][name] = section
        # 进程启动时不把磁盘快照标成刚刚在线获取。
        for section in self.state["sections"].values():
            section["status"] = "cached" if section.get("data") else "unavailable"
        for name in ("concepts", "fund_concepts"):
            for board in self.state["sections"].get(name, {}).get("data", {}).get("items", []):
                retain_board_funds(board)
        if "news" not in self.state["sections"]:
            news = json.loads((DATA / "news_snapshot.json").read_text(encoding="utf-8"))
            self.state["sections"]["news"] = {"status": "cached", "data": news, "as_of": news["checked_at"], "retrieved_at": news["checked_at"], "source": "已核验新闻归档"}

    def history_window(self):
        records = {v["date"]: v for v in self.history["items"]}
        current = self.state["sections"].get("breadth", {}).get("data")
        if current:
            existing = records.get(current["date"])
            if existing is None or current["observed_at"] >= existing["observed_at"]:
                records[current["date"]] = current
        calendar = list(self.history.get("calendar") or sorted(records))
        if current and (not calendar or current["date"] > calendar[-1]):
            calendar.append(current["date"])
        rows = [records.get(day, {"date": day, "up": None, "down": None, "flat": None, "source": "缺测", "provisional": False}) for day in sorted(set(calendar))[-30:]]
        return {"scope": "沪深A股", "items": rows, "missing": sum(v["up"] is None or v["down"] is None for v in rows)}

    def snapshot(self):
        with self.lock:
            result = json.loads(json.dumps(self.state))
            result["breadth_history"] = self.history_window()
            result["server_time"] = stamp()
            result["market_session"] = market_session(now(), self.holidays)
            return result

    def refresh(self):
        if not self.refresh_lock.acquire(blocking=False):
            return False
        try:
            with self.lock:
                self.state.update(refreshing=True, attempted_at=stamp())
            jobs = {"indices": fetch_indices, "breadth": fetch_breadth, "concepts": fetch_concepts, "fund_concepts": fetch_fund_concepts,
                    "communications": lambda: fetch_communications(self.history.get("calendar", []))}
            session = market_session(now(), self.holidays)
            if session["phase"] in ("closed", "preopen", "closed_today"):
                for name in ("indices", "breadth", "concepts", "fund_concepts"):
                    prior = self.state["sections"].get(name, {})
                    as_of = prior.get("as_of")
                    complete = bool(as_of and as_of.startswith(session["expected_date"] or "INVALID") and as_of[11:16] >= "15:00" and prior.get("data"))
                    if name in ("concepts", "fund_concepts") and complete:
                        boards = prior["data"].get("items", [])
                        complete = len(boards) == 10 and all(b.get("values") and b["values"][-1]["t"] == 240 for b in boards)
                        full_history = all(len(b.get("days", [])) >= 5 and all(d.get("main_net_inflow_yi") is not None and d.get("pct_change") is not None for d in b["days"][-5:]) for b in boards)
                        age = time.time() - datetime.fromisoformat(prior["retrieved_at"]).timestamp()
                        if complete and not full_history and age >= 900:
                            complete = False  # 历史资金尚缺时每15分钟补试，其他时候直接使用收盘缓存。
                    if complete:
                        del jobs[name]
                        prior["status"] = "cached_close"
            previous = self.state["sections"].get("news", {})
            if previous.get("status") != "ok" or time.time() - datetime.fromisoformat(previous["retrieved_at"]).timestamp() >= 300:
                jobs["news"] = fetch_news
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = {pool.submit(func): name for name, func in jobs.items()}
                calendar_job = pool.submit(fetch_calendar) if not self.history.get("calendar") or self.history["calendar"][-1] < (session["expected_date"] or now().date().isoformat()) else None
                for future in as_completed(futures):
                    name = futures[future]
                    with self.lock:
                        try:
                            data, as_of, source = future.result()
                            self.state["sections"][name] = {"status": "ok", "data": data, "as_of": as_of, "retrieved_at": stamp(), "source": source}
                        except Exception as exc:
                            old = self.state["sections"].get(name, {})
                            old.update(status="stale" if old.get("data") else "unavailable", error=type(exc).__name__, failed_at=stamp())
                            self.state["sections"][name] = old
                if calendar_job:
                    try:
                        self.history["calendar"] = calendar_job.result()
                    except Exception:
                        pass
            for name in ("concepts", "fund_concepts"):
                if self.state["sections"].get(name, {}).get("status") != "ok":
                    repair_concept_history(self.state["sections"].get(name, {}))
            repair_fund_series(self.state["sections"], session.get("expected_date"))
            with self.lock:
                current = self.state["sections"].get("breadth", {}).get("data")
                if current:
                    rows = {r["date"]: r for r in self.history["items"]}
                    if current["date"] not in rows or current["observed_at"] >= rows[current["date"]]["observed_at"]:
                        rows[current["date"]] = current
                    self.history["items"] = [rows[k] for k in sorted(rows)][-100:]
                self.state.update(refreshing=False, completed_at=stamp())
                self.state["market_session"] = market_session(now(), self.holidays)
                atomic_json(DATA / "breadth_history.json", self.history)
                atomic_json(self.path, self.state)
                atomic_json(DATA / "breadth_snapshot.json", self.history_window())
                target = session.get("expected_date")
                sections = {name: self.state["sections"].get(name, {}) for name in ("indices", "breadth", "concepts")}
                if session["phase"] in ("closed", "preopen", "closed_today") and target and all(v.get("data") and (v.get("as_of") or "").startswith(target) and v["as_of"][11:16] >= "15:00" for v in sections.values()):
                    flow_section = self.state["sections"].get("fund_concepts", {})
                    if (flow_section.get("as_of") or "").startswith(target) and flow_section["as_of"][11:16] >= "15:00":
                        sections["fund_concepts"] = flow_section
                    atomic_json(CACHE / "closing" / (target + ".json"), {"date": target, "sections": sections, "saved_at": stamp()})
                from closing_archive import save_close
                save_close(self.snapshot())
            return True
        finally:
            with self.lock:
                self.state["refreshing"] = False
            self.refresh_lock.release()


if __name__ == "__main__":
    store = DashboardStore()
    store.refresh()
    view = store.snapshot()
    print(json.dumps({"history_days": len(view["breadth_history"]["items"]), "missing": view["breadth_history"]["missing"],
                      "sections": {k: {"status": v["status"], "as_of": v.get("as_of"), "error": v.get("error")} for k, v in view["sections"].items()}}, ensure_ascii=True))
