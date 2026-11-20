"""Validate saved candidate records without source rescans or predictive tests."""
import csv,json,math
from build_candidate_panel import ROOT,number,share_values


def main():
    with (ROOT/'data/analytic/candidate_daily_panel.csv').open(encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    keys={(r['symbol'],r['date']) for r in rows}
    assert len(keys)==len(rows)
    assert {r['symbol'] for r in rows}=={'SPY','AAPL','MSFT'}
    counts={'retained_rows':len(rows),'proxy_candidates':0,'joint_candidates':0,
            'spy_suspect':0,'missing_auction_values':0,'nonpositive_daily_values':0,
            'negative_auction_values':0,'out_of_range_raw_shares':0}
    for r in rows:
        expected=share_values(r['symbol'],r['date'],r['official_close_auction_volume_raw'],r['consolidated_daily_volume_raw'])
        actual=number(r['auction_share'])
        assert actual==expected['auction_share'] or (actual is not None and expected['auction_share'] is not None and math.isclose(actual,expected['auction_share'],rel_tol=1e-12))
        assert (r['spy_auction_100_suspect']=='True')==expected['spy_auction_100_suspect']
        if expected['spy_auction_100_suspect']:
            counts['spy_suspect']+=1
            assert actual is None and number(r['official_close_auction_volume_raw'])==100
        price_valid=r['window_10m_complete']=='True' and r['next0930_valid']=='True'
        assert (r['price_proxy_candidate_eligible']=='True')==price_valid
        assert (r['joint_candidate_eligible_provisional']=='True')==(price_valid and expected['auction_share_eligible_provisional'])
        counts['proxy_candidates']+=price_valid
        counts['joint_candidates']+=r['joint_candidate_eligible_provisional']=='True'
        for w in [5,10,15,30]:
            if r[f'window_{w}m_complete']=='True':
                correct=float(r['preclose_proxy_close'])/float(r[f'window_{w}m_start_raw_open'])-1
                assert math.isclose(float(r[f'provisional_preclose_return_{w}m']),correct,abs_tol=1e-15)
        if price_valid:
            correct=float(r['next0930_open'])/float(r['preclose_proxy_close'])-1
            assert math.isclose(float(r['provisional_preclose_to_next0930_return']),correct,abs_tol=1e-15)
        a=number(r['official_close_auction_volume_raw']);d=number(r['consolidated_daily_volume_raw']);raw=number(r['auction_share_raw_diagnostic'])
        counts['missing_auction_values']+=a is None
        counts['nonpositive_daily_values']+=d is not None and d<=0
        counts['negative_auction_values']+=a is not None and a<0
        counts['out_of_range_raw_shares']+=raw is not None and not 0<=raw<=1
    assert counts['spy_suspect']==87
    out=ROOT/'outputs/diagnostics/candidate_saved_output_validation.json'
    out.write_text(json.dumps({'checks':'PASS: keys, eligibility, original SPY values, all proxy-return algebra','counts':counts},indent=2),encoding='utf-8')
    print(json.dumps(counts,indent=2))


if __name__=='__main__':main()
