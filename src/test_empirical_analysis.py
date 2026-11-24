"""Numerical/statistical safeguards plus actual-panel alignment checks."""
import unittest
import numpy as np
import pandas as pd
from build_full_panel import ROOT,venue,price_for
from estimate_empirical_models import fit,trading_date_codes

class EmpiricalTests(unittest.TestCase):
    def test_bootstrap_preserves_scheduled_gap(self):
        frame=pd.DataFrame({'date':['2016-01-04','2016-01-06']})
        codes,n=trading_date_codes(frame)
        np.testing.assert_array_equal(codes,[0,2])
        self.assertEqual(n,3)

    def test_walmart_venue_boundary(self):
        self.assertEqual(venue('WMT','2025-12-08'),'WMT UN EQUITY')
        self.assertEqual(venue('WMT','2025-12-09'),'WMT UW EQUITY')
        self.assertEqual(price_for({('WMT UN EQUITY','2025-12-09'):{'value':99}},'WMT','2025-12-09')[1],{})

    def synthetic(self):
        rng=np.random.default_rng(482)
        g=pd.DataFrame({'symbol':np.tile(['A','B','C'],80),'date':np.repeat(pd.date_range('2020-01-01',periods=80).strftime('%Y-%m-%d'),3)})
        g['x_10m']=rng.normal(0,.01,len(g));g['a_centered']=rng.normal(0,.04,len(g))
        g['y_SplitOnly']=-.2*g.x_10m+.01*g.a_centered+2*g.x_10m*g.a_centered+g.symbol.map({'A':.1,'B':-.2,'C':.3})+pd.to_datetime(g.date).dt.month*.05+rng.normal(0,.001,len(g))
        return g

    def test_fwl_and_cluster_covariance_match_explicit_dummies(self):
        g=self.synthetic();result=fit(g)
        X=np.column_stack([g.x_10m,g.a_centered,g.x_10m*g.a_centered])
        dummy=pd.get_dummies(g[['symbol']].assign(month=g.date.str[:7]),dtype=float)
        D=np.column_stack([X,dummy.to_numpy()]);y=g.y_SplitOnly.to_numpy()
        b=np.linalg.lstsq(D,y,rcond=None)[0]
        np.testing.assert_allclose(result['coef'],b[:3],atol=1e-10)
        residual=y-D@b;codes=pd.factorize(g.date,sort=True)[0];scores=np.zeros((codes.max()+1,D.shape[1]));np.add.at(scores,codes,D*residual[:,None])
        inv=np.linalg.pinv(D.T@D);N=len(g);G=codes.max()+1;K=np.linalg.matrix_rank(D)
        cov=inv@scores.T@scores@inv*(G/(G-1))*((N-1)/(N-K))
        np.testing.assert_allclose(result['cov'],cov[:3,:3],rtol=1e-6,atol=1e-12)

    def test_weighted_fwl_matches_explicit_weighted_dummies(self):
        g=self.synthetic();rng=np.random.default_rng(54);w=rng.integers(0,4,len(g)).astype(float)
        result=fit(g,weights=w)
        X=np.column_stack([g.x_10m,g.a_centered,g.x_10m*g.a_centered])
        dummy=pd.get_dummies(g[['symbol']].assign(month=g.date.str[:7]),dtype=float)
        D=np.column_stack([X,dummy.to_numpy()]);root=np.sqrt(w)
        expected=np.linalg.lstsq(D*root[:,None],g.y_SplitOnly.to_numpy()*root,rcond=None)[0]
        np.testing.assert_allclose(result,expected[:3],atol=1e-9)

    def test_actual_panel_returns_and_dates(self):
        path=ROOT/'data/analytic/full_analytical_panel.csv'
        if not path.exists():self.skipTest('Full panel not built yet')
        f=pd.read_csv(path);self.assertFalse(f.duplicated(['symbol','date']).any())
        cal=pd.read_csv(ROOT/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv').set_index('session_date')
        self.assertTrue((f.next_session==f.date.map(cal.next_session)).all())
        for cfg in ['SplitOnly','SplitDiv']:
            valid=f[f['y_'+cfg].notna()]
            np.testing.assert_allclose(valid['y_'+cfg],valid['open_next_'+cfg]/valid['close_'+cfg]-1,atol=1e-14)
        for w in [5,10,15,30]:
            valid=f[f[f'complete_{w}m']]
            np.testing.assert_allclose(valid[f'x_{w}m'],valid.preclose_close/valid[f'start_{w}m_open']-1,atol=1e-14)
        suspect=f[f.spy_auction_100_suspect];self.assertEqual(len(suspect),87);self.assertTrue(suspect.auction_share.isna().all())
        self.assertFalse(f.loc[f.symbol=='SPY','asset_type'].eq('equity').any())
        eligible=f[f.eligible_primary];self.assertTrue(np.isfinite(eligible[['x_10m','y_SplitOnly','auction_share']]).all().all());self.assertTrue(eligible.auction_share.between(0,1).all())
        for col in ['close_security_SplitOnly','open_next_security_SplitOnly','daily_security']:
            self.assertTrue((f[col].str.split().str[0]==f.symbol).all())
        if 'a_centered' in f:
            np.testing.assert_allclose(eligible.groupby('symbol').a_centered.mean().to_numpy(),0,atol=1e-12)
        wmt=f[f.symbol=='WMT'];self.assertTrue((wmt.close_security_SplitOnly==wmt.date.map(lambda d:venue('WMT',d))).all());self.assertTrue((wmt.open_next_security_SplitOnly==wmt.next_session.map(lambda d:venue('WMT',d))).all())
        for s in ['JNJ','BAC','WMT']:self.assertGreater(f[(f.symbol==s)&f.date.str.startswith('2016')].close_SplitOnly.isna().sum(),0)

if __name__=='__main__':unittest.main()
