import unittest
from copy import deepcopy
from pathlib import Path
import tempfile
from unittest.mock import patch
import live_data as data
import closing_archive as archive


class FundRankingTests(unittest.TestCase):
    def rows(self):
        return [{'f12':f'BK{i:04}', 'f14':f'测试概念{i}', 'f3':i, 'f62':(20-i)*1e8, 'f124':1793080800} for i in range(20)]

    def test_independent_universe_not_price_top_ten(self):
        rows=self.rows()
        price=data.select_concept_rows(rows,'pct')
        flow=data.select_concept_rows(rows,'flow')
        self.assertEqual([r['f12'] for r in price], [f'BK{i:04}' for i in range(19,9,-1)])
        self.assertEqual([r['f12'] for r in flow], [f'BK{i:04}' for i in range(10)])
        self.assertFalse(set(r['f12'] for r in price)&set(r['f12'] for r in flow))

    def test_missing_money_not_zero_and_same_style_filter(self):
        rows=self.rows()
        rows[0]['f62']='-'
        rows[1]['f14']='昨日涨停'
        chosen=data.select_concept_rows(rows,'flow')
        self.assertEqual(chosen[0]['f12'],'BK0002')

    def test_signed_value_sort_and_tie(self):
        rows=self.rows()
        for r in rows:r['f62']=-1
        chosen=data.select_concept_rows(list(reversed(rows)),'flow')
        self.assertEqual([r['f12'] for r in chosen],[f'BK{i:04}' for i in range(10)])

    def test_selection_tags_are_removed_but_industry_themes_remain(self):
        rows=self.rows()
        for row,name in zip(rows,['券商金股','保险重仓','茅指数','宁组合','贬值受益','CPO概念','F5G概念','光通信模块','PCB','液冷服务器']):
            row['f14']=name
        for order in ('pct','flow'):
            names={r['f14'] for r in data.select_concept_rows(rows,order)}
            self.assertFalse(names&{'券商金股','保险重仓','茅指数','宁组合','贬值受益'})
        names={r['f14'] for r in data.select_concept_rows(rows,'flow')}
        self.assertTrue({'CPO概念','F5G概念','光通信模块','PCB','液冷服务器'}<=names)

    def test_flow_requests_f62_and_keeps_source_order(self):
        class Response:
            def json(self):return {'data':{'diff':FundRankingTests().rows()}}
        with patch.object(data,'get',return_value=Response()) as get,patch.object(data,'fetch_board_series',return_value=[]),patch.object(data,'fetch_board_history',return_value=[]),patch.object(data,'retain_board_funds'):
            value,_,_=data.fetch_fund_concepts()
        self.assertEqual(get.call_args.args[1]['fid'],'f62')
        self.assertEqual(value['ranking'],'flow')
        self.assertEqual(value['items'][0]['ranking_main'],20)

    def test_html_contains_both_groups_and_shared_renderer(self):
        html=archive.dashboard_html({'server_time':'2026-10-27T15:00:01+08:00','sections':{},'market_session':{'expected_date':'2026-10-27'}})
        self.assertIn('data-ranking="flow"',html)
        self.assertIn('fund_concepts',html)
        for n in range(1,8):self.assertIn(f'<span class="section-no">{n:02}</span>',html)
        self.assertNotIn('<script src=',html)

    def test_failed_rank_can_repair_traces_once_for_both_groups(self):
        board={'id':'BK1128','as_of':'2026-10-27T13:07:18+08:00','pct':1,'latest':{'main':5},'values':[]}
        sections={name:{'status':'stale','as_of':board['as_of'],'data':{'items':[deepcopy(board)]}} for name in ('concepts','fund_concepts')}
        rows=[{'t':138,'as_of':'2026-10-27T13:18:00+08:00','main':6}]
        with tempfile.TemporaryDirectory(dir=data.CACHE) as folder,patch.object(data,'CACHE',Path(folder)),patch.object(data,'fetch_board_series',return_value=rows) as fetch:
            data.repair_fund_series(sections,'2026-10-27')
        self.assertEqual(fetch.call_count,1)
        for section in sections.values():
            self.assertEqual(section['as_of'],board['as_of'],'Trace recovery must not change the rank quote timestamp')
            self.assertEqual(section['data']['items'][0]['series_as_of'],rows[0]['as_of'])
            self.assertTrue(any(r['main']==6 for r in section['data']['items'][0]['values']))

    def test_trace_repair_rejects_wrong_date_and_keeps_existing_data(self):
        board={'id':'BK1128','as_of':'2026-10-27T13:07:18+08:00','values':[{'t':1,'as_of':'2026-10-27T09:31:00+08:00','main':1}]}
        section={'status':'stale','data':{'items':[board]}}
        wrong=[{'t':138,'as_of':'2026-10-26T13:18:00+08:00','main':999}]
        with tempfile.TemporaryDirectory(dir=data.CACHE) as folder,patch.object(data,'CACHE',Path(folder)),patch.object(data,'fetch_board_series',return_value=wrong):
            data.repair_fund_series({'concepts':section},'2026-10-27')
        self.assertEqual([r['main'] for r in board['values']],[1])


if __name__=='__main__':unittest.main()
