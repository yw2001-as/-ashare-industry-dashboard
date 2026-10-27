"""关键口径测试：日期、缺测、资金单位和失败时保留原时间。"""
from copy import deepcopy
from datetime import datetime
import json
import threading
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import live_data as data


class DataTests(unittest.TestCase):
    def test_fund_cache_keeps_minutes_when_next_request_has_no_trace(self):
        first={'id':'BK1145','as_of':'2026-10-26T10:00:00+08:00','latest':{'main':3},'values':[
            {'t':1,'as_of':'2026-10-26T09:31:00+08:00','main':1}]}
        second={'id':'BK1145','as_of':'2026-10-26T10:01:30+08:00','latest':{'main':4},'values':[]}
        with tempfile.TemporaryDirectory(prefix='fund-test-',dir=data.CACHE) as directory,patch.object(data,'CACHE',Path(directory)):
            data.retain_board_funds(first)
            data.retain_board_funds(second)
            self.assertEqual([r['main'] for r in second['values']],[1,3,4])
            self.assertEqual(second['values'][-1]['t'],31.5)
            self.assertEqual(second['values'][-1]['kind'],'quote')
            data.retain_board_funds(second)
            self.assertEqual(len(second['values']),3,'Repeated quote must not duplicate observations')

    def test_fund_cache_isolates_day_and_board(self):
        board={'id':'BK1145','as_of':'2026-10-26T10:00:00+08:00','latest':{'main':3},'values':[
            {'t':1,'as_of':'2026-10-23T09:31:00+08:00','main':99}]}
        with tempfile.TemporaryDirectory(prefix='fund-test-',dir=data.CACHE) as directory,patch.object(data,'CACHE',Path(directory)):
            data.retain_board_funds(board)
            other={**board,'id':'BK1146','as_of':'2026-10-26T10:01:00+08:00','values':[],'latest':{'main':4}}
            data.retain_board_funds(other)
            tomorrow={**board,'as_of':'2026-10-27T09:31:00+08:00','values':[],'latest':{'main':5}}
            data.retain_board_funds(tomorrow)
            self.assertEqual([r['main'] for r in board['values']],[3])
            self.assertEqual([r['main'] for r in other['values']],[4])
            self.assertEqual([r['main'] for r in tomorrow['values']],[5])

    def test_lunch_quote_does_not_create_early_afternoon_trading(self):
        board={'id':'BK1145','as_of':'2026-10-27T12:20:51+08:00','latest':{'main':3},'values':[]}
        with tempfile.TemporaryDirectory(prefix='fund-test-',dir=data.CACHE) as directory,patch.object(data,'CACHE',Path(directory)):
            data.retain_board_funds(board)
            self.assertEqual(board['values'][-1]['t'],120)
            self.assertEqual(board['values'][-1]['rawMinute'],120)

    def test_official_inventory_selects_concepts_only(self):
        concepts=''.join(f'<a href="/bkzj/BK{i:04}.html">概念{i}</a>' for i in range(10))
        html='<div class="bkselectorpop"><ul class="pop_slider"><li>行业</li><li>概念</li><li>地域</li></ul><div class="pop-cont"><a href="/bkzj/BK1036.html">半导体</a></div><div class="pop-cont">'+concepts+'</div><div class="pop-cont"><a href="/bkzj/BK001.html">北京</a></div></div>'
        result=data.parse_concept_inventory(html)
        self.assertEqual(len(result),10)
        self.assertNotIn('BK1036',result)
        self.assertNotIn('BK001',result)

    def test_incomplete_batch_does_not_claim_top10(self):
        inventory={f'BK{i:04}':f'概念{i}' for i in range(10)}
        class Response:
            def json(self):
                return {'data':{'diff':[{'f12':'BK0000','f3':3}]}}
        with patch.object(data,'concept_inventory',return_value=inventory),patch.object(data,'get',return_value=Response()):
            with self.assertRaises(ValueError):
                data.batch_concept_quotes()

    def test_weekend_uses_complete_closing_cache_without_requery(self):
        store=data.DashboardStore.__new__(data.DashboardStore)
        store.lock,store.refresh_lock=threading.RLock(),threading.Lock()
        store.holidays=json.loads((data.DATA/'exchange_holidays.json').read_text(encoding='utf-8'))
        day={'date':'2026-10-23','up':4197,'down':887,'flat':135,'observed_at':'2026-10-23T15:00:00+08:00'}
        store.history={'calendar':['2026-10-23'],'items':[day]}
        store.path=data.CACHE/'unused-test.json'
        base={'status':'ok','as_of':'2026-10-23T15:00:00+08:00','retrieved_at':'2026-10-23T15:05:00+08:00'}
        boards=[{'values':[{'t':240}],'days':[{'main_net_inflow_yi':1,'pct_change':1}]*5} for _ in range(10)]
        store.state={'sections':{'indices':{**base,'data':{'items':[{}]*6}},'breadth':{**base,'data':day},'concepts':{**base,'data':{'items':boards}},'news':{'status':'ok','retrieved_at':'2026-10-25T10:00:00+08:00'}}}
        with patch.object(data,'now',return_value=datetime(2026,10,25,10,0,tzinfo=data.TZ)),patch.object(data,'fetch_indices') as indices,patch.object(data,'fetch_breadth') as breadth,patch.object(data,'fetch_concepts') as concepts,patch.object(data,'fetch_communications',side_effect=ConnectionError),patch.object(data,'fetch_fund_concepts',side_effect=ConnectionError),patch.object(data,'atomic_json'),patch('closing_archive.save_close'):
            store.refresh()
        indices.assert_not_called();breadth.assert_not_called();concepts.assert_not_called()
        self.assertEqual(store.state['sections']['concepts']['status'],'cached_close')
        self.assertEqual(store.state['sections']['concepts']['retrieved_at'],base['retrieved_at'])

    def test_weekend_targets_friday_close(self):
        holidays=json.loads((data.DATA/'exchange_holidays.json').read_text(encoding='utf-8'))
        result=data.market_session(datetime(2026,10,25,10,0,tzinfo=data.TZ),holidays)
        self.assertEqual((result['phase'],result['expected_date']),('closed','2026-10-23'))

    def test_weekday_holiday_targets_last_trading_session(self):
        holidays=json.loads((data.DATA/'exchange_holidays.json').read_text(encoding='utf-8'))
        for day in (1,2,7):
            result=data.market_session(datetime(2026,10,day,10,0,tzinfo=data.TZ),holidays)
            self.assertEqual((result['phase'],result['expected_date']),('closed','2026-09-30'))

    def test_preopen_lunch_and_close(self):
        holidays=json.loads((data.DATA/'exchange_holidays.json').read_text(encoding='utf-8'))
        pre=data.market_session(datetime(2026,10,8,8,0,tzinfo=data.TZ),holidays)
        self.assertEqual(pre['expected_date'],'2026-09-30')
        for hour,phase in ((10,'trading'),(12,'lunch'),(14,'trading'),(16,'closed_today')):
            result=data.market_session(datetime(2026,10,8,hour,0,tzinfo=data.TZ),holidays)
            self.assertEqual((result['phase'],result['expected_date']),(phase,'2026-10-08'))

    def test_lunch_collapses_without_time_from_system_clock(self):
        self.assertEqual([data.trading_minute(t) for t in ("0930", "1130", "1300", "1500")], [0, 120, 120, 240])

    def test_non_numeric_is_missing_not_zero(self):
        for value in (None, "-", "NaN", "inf", ""):
            self.assertIsNone(data.number(value))
        self.assertEqual(data.number(0), 0)

    def test_fund_field_order_and_yi_unit(self):
        row = data.parse_fund_lines(["2026-10-23 09:31,12836208,120141040,-132315344,-427513888,440350096"])[0]
        self.assertAlmostEqual(row["main"], .12836208)
        self.assertAlmostEqual(row["main"], row["xl"] + row["lg"])
        self.assertEqual(row["as_of"], "2026-10-23T09:31:00+08:00")
        self.assertAlmostEqual(row["sm"], 1.2014104)

    def test_invalid_fund_observation_not_fabricated(self):
        self.assertEqual(data.parse_fund_lines(["2026-10-23 09:31,-,0,0,0,0"]), [])

    def test_wrong_board_response_is_rejected(self):
        class Response:
            def json(self):
                return {'data':{'code':'BK9999','klines':['2026-10-23 15:00,1,2,3,4,5']}}
        with patch.object(data,'get',return_value=Response()):
            with self.assertRaises(ValueError):
                data.fetch_board_series('BK1145')

    def test_breadth_requires_provider_date(self):
        html = '<table><tr><td>上涨</td><td>4197</td><td>下跌</td><td>887</td><td>平盘</td><td>135</td></tr></table>'
        with self.assertRaises(ValueError):
            data.parse_breadth(html)
        value, as_of, _ = data.parse_breadth(html + '<span class="market-activity-time">2026-10-23 11:12:00</span>')
        self.assertEqual(value["up"], 4197)
        self.assertTrue(value["provisional"])
        self.assertEqual(as_of, "2026-10-23T11:12:00+08:00")

    def test_calendar_gap_does_not_create_zero_count(self):
        store = data.DashboardStore.__new__(data.DashboardStore)
        store.history = {"calendar": ["2026-10-22", "2026-10-23"], "items": [{"date": "2026-10-22", "up": 447, "down": 4739}]}
        store.state = {"sections": {}}
        view = store.history_window()
        self.assertEqual(view["missing"], 1)
        self.assertIsNone(view["items"][-1]["up"])

    def test_failed_refresh_keeps_original_data_and_asof(self):
        store = data.DashboardStore.__new__(data.DashboardStore)
        store.lock, store.refresh_lock = threading.RLock(), threading.Lock()
        store.history = {"calendar": [data.now().date().isoformat()], "items": []}
        store.holidays = json.loads((data.DATA/'exchange_holidays.json').read_text(encoding='utf-8'))
        store.path = data.CACHE / "unused-test.json"
        original = {"status": "ok", "data": {"items": []}, "as_of": "2026-10-23T15:00:00+08:00", "retrieved_at": "2026-10-23T15:01:00+08:00"}
        store.state = {"sections": {"concepts": deepcopy(original)}}
        with patch.object(data, "fetch_indices", side_effect=ConnectionError), patch.object(data, "fetch_breadth", side_effect=ConnectionError), patch.object(data, "fetch_concepts", side_effect=ConnectionError), patch.object(data, "fetch_communications", side_effect=ConnectionError), patch.object(data, "fetch_fund_concepts", side_effect=ConnectionError), patch.object(data, "fetch_news", side_effect=ConnectionError), patch.object(data, "atomic_json"), patch("closing_archive.save_close"):
            store.refresh()
        result = store.state["sections"]["concepts"]
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["as_of"], original["as_of"])
        self.assertEqual(result["retrieved_at"], original["retrieved_at"])
        self.assertEqual(result["data"], original["data"])
        self.assertEqual(store.state["sections"]["indices"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
