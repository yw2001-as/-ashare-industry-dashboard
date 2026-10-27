from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import communications_data as comm
from live_data import TZ


class CommunicationsTests(unittest.TestCase):
    def test_quotes_require_matching_code_name_and_provider_time(self):
        row={'f12':'BK1128','f14':'CPO概念','f3':1.2,'f62':300000000,'f66':200000000,'f72':100000000,'f78':'-','f84':-300000000,'f124':1793070000}
        parsed=comm.parse_quotes({'data':{'diff':[row]}},{'BK1128':'CPO概念'})
        self.assertEqual(parsed['BK1128']['latest']['main'],3)
        self.assertIsNone(parsed['BK1128']['latest']['md'])
        for change in ({'f12':'BK9999'},{'f14':'其他板块'},{'f124':'-'},{'f3':'-'}):
            self.assertEqual(comm.parse_quotes({'data':{'diff':[{**row,**change}]}},{'BK1128':'CPO概念'}),{})

    def test_five_day_return_is_compounded_and_zero_is_valid(self):
        days=[{'pct_change':p,'main_net_inflow_yi':f} for p,f in zip([10,-10,0,0,0],[2,-1,0,1,-2])]
        value=comm.window_stats(days)
        self.assertAlmostEqual(value['pct_5d'],-1)
        self.assertEqual(value['flow_5d'],0)
        self.assertEqual(value['inflow_days'],2)

    def test_missing_day_does_not_make_partial_sum_look_like_five_days(self):
        days=[{'pct_change':1,'main_net_inflow_yi':2} for _ in range(5)]
        days[-1]['main_net_inflow_yi']=None
        stats=comm.window_stats(days)
        self.assertIsNone(stats['flow_5d']);self.assertIsNone(stats['inflow_days'])
        self.assertEqual(stats['flow_coverage'],4)
        self.assertIsNone(comm.window_stats(days[:4])['pct_5d'])

    def test_assessment_exposes_divergence_and_missing_history(self):
        row={'as_of':'2026-10-27T11:30:00+08:00','pct':1,'latest':{'main':-2},'stats':{'flow_coverage':1,'pct_coverage':5}}
        self.assertEqual(comm.assessment(row,'2026-10-27')['label'],'上涨·资金流出')
        self.assertIn('持续性待核验',comm.assessment(row,'2026-10-27')['reason'])
        self.assertEqual(comm.assessment(row,'2026-10-28')['label'],'日期待更新')

    def test_failed_refresh_retains_original_quote_date(self):
        setting=deepcopy(comm.config());setting['items']=setting['items'][:1]
        quote={'id':'BK1128','pct':2,'as_of':'2026-10-26T15:00:00+08:00','latest':{'main':3,'xl':2,'lg':1,'md':-1,'sm':-2}}
        with tempfile.TemporaryDirectory(prefix='comm-test-',dir=comm.CACHE) as directory:
            root=Path(directory);(root/'communications').mkdir()
            (root/'communications/quotes.json').write_text(json.dumps({'boards':{'BK1128':quote},'stocks':{}}),encoding='utf-8')
            with patch.object(comm,'CACHE',root),patch.object(comm,'config',return_value=setting),patch.object(comm,'get',side_effect=ConnectionError),patch.object(comm,'fetch_history',return_value=[]),patch.object(comm,'now',return_value=datetime(2026,10,27,12,tzinfo=TZ)):
                result,as_of,_=comm.fetch_communications(['2026-10-21','2026-10-22','2026-10-23','2026-10-26','2026-10-27'])
            board=result['items'][0]
            self.assertEqual(as_of,quote['as_of']);self.assertEqual(board['quote_status'],'cached')
            self.assertIsNone(board['days'][-1]['pct_change'])
            self.assertEqual(board['assessment']['label'],'日期待更新')

    def test_wrong_history_board_cannot_poison_cache(self):
        class Response:
            def json(self):return {'data':{'code':'BK9999','klines':['2026-10-23,1,2,3,4,5,6,7,8,9,10,11,12']}}
        with tempfile.TemporaryDirectory(prefix='comm-test-',dir=comm.CACHE) as directory,patch.object(comm,'CACHE',Path(directory)),patch.object(comm,'get',return_value=Response()):
            self.assertEqual(comm.fetch_history('BK1128'),[])

    def test_intraday_quote_is_not_archived_as_previous_close(self):
        setting=deepcopy(comm.config());setting['items']=setting['items'][:1]
        quote={'id':'BK1128','pct':2,'as_of':'2026-10-27T11:30:00+08:00','latest':{'main':3,'xl':2,'lg':1,'md':-1,'sm':-2}}
        with tempfile.TemporaryDirectory(prefix='comm-test-',dir=comm.CACHE) as directory:
            root=Path(directory);(root/'communications').mkdir()
            (root/'communications/quotes.json').write_text(json.dumps({'boards':{'BK1128':quote},'stocks':{}}),encoding='utf-8')
            with patch.object(comm,'CACHE',root),patch.object(comm,'config',return_value=setting),patch.object(comm,'get',side_effect=ConnectionError),patch.object(comm,'fetch_history',return_value=[]),patch.object(comm,'now',return_value=datetime(2026,10,27,12,tzinfo=TZ)):
                comm.fetch_communications(['2026-10-27'])
            self.assertEqual(json.loads((root/'communications/observed-closes.json').read_text(encoding='utf-8')), {})


if __name__=='__main__':unittest.main()
