"""Measurement safeguards; synthetic rows only, never estimate research effects."""
import csv
import unittest
from build_candidate_panel import valid_bar,window_status,next_open,share_values,event_columns,ROOT


class CandidateTests(unittest.TestCase):
    def test_early_close_window_and_missing_label(self):
        bars={m:[{'valid':True}] for m in range(770,780)}
        self.assertEqual(window_status(bars,780,10),(0,0,0))
        del bars[775]
        self.assertEqual(window_status(bars,780,10)[0],1)
        self.assertEqual(window_status(bars,960,10)[0],10)

    def test_duplicate_cannot_be_hidden_by_valid_row(self):
        bars={m:[{'valid':True}] for m in range(950,960)}
        bars[955].append({'valid':False})
        self.assertEqual(window_status(bars,960,10),(0,1,1))

    def test_no_later_open_substitution(self):
        self.assertIsNone(next_open({571:[{'valid':True,'open':'10'}]}))
        self.assertIsNone(next_open({570:[{'valid':True},{'valid':True}]}))

    def test_spy_suspect_preserves_raw_ratio_but_blocks_share(self):
        out=share_values('SPY','2016-05-10',100,10000)
        self.assertEqual(out['auction_share_raw_diagnostic'],.01)
        self.assertIsNone(out['auction_share'])
        self.assertFalse(out['auction_share_eligible_provisional'])
        self.assertTrue(share_values('SPY','2016-09-07',1506352,10000000)['auction_share_eligible_provisional'])

    def test_invalid_volume_and_ohlc(self):
        for a,d in [(1,0),(-1,10),(11,10),(None,10),(1,None)]:
            self.assertIsNone(share_values('AAPL','2020-01-02',a,d)['auction_share'])
        self.assertEqual(share_values('AAPL','2020-01-02',0,10)['auction_share'],0)
        self.assertFalse(valid_bar([10,9,8,10,100]))
        self.assertFalse(valid_bar([10,11,9,10,-1]))
        self.assertTrue(valid_bar([10,11,9,10,0]))

    def test_calendar_successor_not_consecutive_date(self):
        with (ROOT/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv').open() as f:
            cal={r['session_date']:r for r in csv.DictReader(f)}
        self.assertEqual(cal['2013-07-03']['close_minute'],'780')
        self.assertEqual(cal['2013-07-03']['next_session'],'2013-07-05')
        self.assertEqual(cal['2025-12-31']['next_session'],'2026-01-02')

    def test_action_flags_are_not_exclusions_or_completeness_claims(self):
        ev={('AAPL','2020-08-31'):[{'type_raw':'Stock Split'}]}
        r=event_columns(ev,'AAPL','2020-08-28','2020-08-31')
        self.assertTrue(r['next_split_flag'])
        self.assertFalse(r['anchor_split_flag'])
        self.assertFalse(r['action_calendar_complete_verified'])


if __name__=='__main__':unittest.main()
