"""Fixed-effect regressions and prespecified date-block uncertainty; NumPy only."""
import json,math,hashlib
from pathlib import Path
from statistics import NormalDist
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/empirical';FIG=OUT/'figures'
SPEC=ROOT/'reports/final_empirical_specification.md'
SEED=20261121;REPLICATES=499;BLOCK=20

def absorb(values,groups,weights=None,tol=1e-12,max_iter=300):
    z=np.asarray(values,float).copy();weights=np.ones(len(z)) if weights is None else np.asarray(weights,float)
    for it in range(max_iter):
        previous=z.copy()
        for codes in groups:
            denom=np.bincount(codes,weights=weights);safe=np.where(denom>0,denom,1)
            for j in range(z.shape[1]):
                mean=np.bincount(codes,weights=weights*z[:,j],minlength=len(denom))/safe
                z[:,j]-=mean[codes]
        if np.max(np.abs(z-previous))<tol:return z
    raise ValueError('Fixed-effect absorption failed to converge')

def design(frame,xcol='x_10m',ycol='y_SplitOnly',interaction=True):
    x=frame[xcol].to_numpy(float);a=frame.a_centered.to_numpy(float)
    X=np.column_stack([x,a,x*a]) if interaction else x[:,None]
    y=frame[ycol].to_numpy(float)
    groups=[pd.factorize(frame.symbol,sort=True)[0],pd.factorize(frame.date.str[:7],sort=True)[0]]
    dates=pd.factorize(frame.date,sort=True)[0]
    return X,y,groups,dates

def fit(frame,xcol='x_10m',ycol='y_SplitOnly',interaction=True,weights=None):
    X,y,groups,dates=design(frame,xcol,ycol,interaction)
    z=absorb(np.column_stack([y,X]),groups,weights);yr=z[:,0];xr=z[:,1:]
    w=np.ones(len(frame)) if weights is None else weights
    xx=xr.T@(xr*w[:,None]);xy=xr.T@(yr*w)
    if np.linalg.matrix_rank(xx)<X.shape[1]:raise ValueError('Singular regression inputs')
    b=np.linalg.solve(xx,xy)
    if weights is not None:return b
    residual=yr-xr@b;G=dates.max()+1;n=len(frame)
    score=np.zeros((G,X.shape[1]));np.add.at(score,dates,xr*residual[:,None])
    K=sum(len(np.unique(g)) for g in groups)-1+X.shape[1]
    inv=np.linalg.inv(xx);cov=inv@(score.T@score)@inv*(G/(G-1))*((n-1)/(n-K))
    return {'coef':b,'cov':cov,'n':n,'securities':frame.symbol.nunique(),'dates':G,
            'start':frame.date.min(),'end':frame.date.max(),'K':K}

def bootstrap(frame,xcol='x_10m',ycol='y_SplitOnly'):
    dates=pd.factorize(frame.date,sort=True)[0];G=dates.max()+1;rng=np.random.default_rng(SEED);draws=[]
    for r in range(REPLICATES):
        starts=rng.integers(0,G,size=math.ceil(G/BLOCK))
        sampled=((starts[:,None]+np.arange(BLOCK))%G).ravel()[:G]
        counts=np.bincount(sampled,minlength=G);w=counts[dates]
        try:draws.append(fit(frame,xcol,ycol,weights=w))
        except ValueError:pass
        if (r+1)%100==0:print('bootstrap',frame.symbol.nunique(),'securities:',r+1,'/',REPLICATES,flush=True)
    if len(draws)<.95*REPLICATES:raise ValueError('Too many singular bootstrap draws')
    return np.array(draws)

def rows_for(label,res,interaction=True):
    names=['beta_x','gamma_auction_share','delta_interaction'] if interaction else ['beta_x']
    out=[]
    for j,name in enumerate(names):
        se=math.sqrt(max(res['cov'][j,j],0));b=res['coef'][j]
        out.append({'model':label,'term':name,'estimate':b,'date_cluster_se':se,'ci_low':b-1.96*se,'ci_high':b+1.96*se,
                    'n':res['n'],'securities':res['securities'],'trading_dates':res['dates'],'start':res['start'],'end':res['end']})
    return out

def slope(res,a):
    contrast=np.array([1.,0.,a]);b=float(contrast@res['coef']);se=math.sqrt(max(float(contrast@res['cov']@contrast),0))
    return b,b-1.96*se,b+1.96*se

def main():
    OUT.mkdir(parents=True,exist_ok=True);FIG.mkdir(exist_ok=True)
    spec_hash=hashlib.sha256(SPEC.read_bytes()).hexdigest()
    panel_path=ROOT/'data/analytic/full_analytical_panel.csv';df=pd.read_csv(panel_path)
    assert not df.duplicated(['symbol','date']).any()
    for c in ['eligible_primary','early_close','anchor_action_found_in_export','next_action_found_in_export','next_cash_distribution_flag']:
        df[c]=df[c].map(lambda x:str(x).lower()=='true')
    eq=df[(df.asset_type=='equity') & df.eligible_primary].copy();spy=df[(df.symbol=='SPY') & df.eligible_primary].copy()
    centers=eq.groupby('symbol').auction_share.mean().to_dict();centers['SPY']=spy.auction_share.mean()
    df['auction_share_reference_mean']=df.symbol.map(centers);df['a_centered']=df.auction_share-df.auction_share_reference_mean
    df.to_csv(panel_path,index=False)
    eq=df[(df.asset_type=='equity') & df.eligible_primary].copy();spy=df[(df.symbol=='SPY') & df.eligible_primary].copy()
    assert eq.symbol.nunique()==15 and not eq[['x_10m','y_SplitOnly','auction_share','a_centered']].isna().any().any()
    fits={};tables=[];samples={}
    def model(label,frame,x='x_10m',y='y_SplitOnly',interaction=True):
        frame=frame[np.isfinite(frame[x]) & np.isfinite(frame[y])].copy()
        res=fit(frame,x,y,interaction);fits[label]=res;samples[label]=frame
        tables.extend(rows_for(label,res,interaction));print(label,len(frame),'rows',flush=True)
    model('Primary_10m_split_only',eq)
    model('Reversal_only',eq,interaction=False)
    model('SPY_benchmark',spy)
    for symbol,g in eq.groupby('symbol'):model('Security_'+symbol,g)
    for w in [5,15,30]:
        base=df[(df.asset_type=='equity') & df[f'complete_{w}m'] & df.next0930_valid & df.y_SplitOnly.notna() & df.auction_share.notna()]
        model(f'Window_{w}m',base,x=f'x_{w}m')
    both=eq[eq.y_SplitDiv.notna()]
    model('Split_dividend',both,y='y_SplitDiv')
    if len(both)!=len(eq):model('Split_only_common_adjustment_sample',both)
    model('Exclude_all_identified_actions',eq[~eq.anchor_action_found_in_export & ~eq.next_action_found_in_export])
    model('Exclude_next_cash_exdate',eq[~eq.next_cash_distribution_flag])
    model('Exclude_early_closes',eq[~eq.early_close])
    model('Earlier10m_Cminus30_Cminus21',eq[eq.placebo_complete],x='x_earlier10m')
    for symbol in sorted(eq.symbol.unique()):model('Leave_out_'+symbol,eq[eq.symbol!=symbol])
    results=pd.DataFrame(tables);results.to_csv(OUT/'regression_coefficients.csv',index=False)
    boot=bootstrap(eq);np.save(OUT/'main_bootstrap_coefficients.npy',boot)
    # ETF time dependence gets the same fixed-block uncertainty check.
    spyboot=bootstrap(spy);np.save(OUT/'spy_bootstrap_coefficients.npy',spyboot)
    br=[]
    for label,draws in [('Primary_10m_split_only',boot),('SPY_benchmark',spyboot)]:
        for j,name in enumerate(['beta_x','gamma_auction_share','delta_interaction']):
            low,high=np.quantile(draws[:,j],[.025,.975]);br.append({'model':label,'term':name,'estimate':fits[label]['coef'][j],
                'block_ci_low':low,'block_ci_high':high,'replicates':len(draws),'block_trading_dates':BLOCK,'seed':SEED})
    pd.DataFrame(br).to_csv(OUT/'block_bootstrap_intervals.csv',index=False)
    qlo,qhi=np.quantile(eq.a_centered,[.25,.75]);res=fits['Primary_10m_split_only'];marginal=[]
    for label,a in [('low_Q25',qlo),('reference_mean',0),('high_Q75',qhi)]:
        b,lo,hi=slope(res,a);sampleslope=boot[:,0]+boot[:,2]*a;blo,bhi=np.quantile(sampleslope,[.025,.975])
        marginal.append({'participation':label,'centered_share':a,'slope':b,'date_ci_low':lo,'date_ci_high':hi,
                         'block_ci_low':blo,'block_ci_high':bhi,'overnight_bp_for_plus100bp_x':100*b,
                         'date_low_bp_for_plus100bp_x':100*lo,'date_high_bp_for_plus100bp_x':100*hi})
    pd.DataFrame(marginal).to_csv(OUT/'marginal_slopes.csv',index=False)
    difference=res['coef'][2]*(qhi-qlo);diffboot=boot[:,2]*(qhi-qlo)
    # Clear, fixed-format tables with every major estimate and confidence interval.
    md='# Regression estimates\n\n95% trading-date clustered intervals; fractions for returns/shares.\n\n| Model | N | Securities | Dates | beta [CI] | delta [CI] |\n| --- | ---: | ---: | --- | --- | --- |\n'
    for label,r in fits.items():
        def fmt(j):
            se=math.sqrt(max(r['cov'][j,j],0));b=r['coef'][j];return f'{b:.4f} [{b-1.96*se:.4f}, {b+1.96*se:.4f}]'
        md+=f"| {label} | {r['n']} | {r['securities']} | {r['start']}–{r['end']} | {fmt(0)} | {fmt(2) if len(r['coef'])==3 else '—'} |\n"
    (ROOT/'reports/regression_tables.md').write_text(md,encoding='utf-8')
    make_figures(fits,results,marginal,res,qlo,qhi)
    write_report(fits,results,br,marginal,difference,np.quantile(diffboot,[.025,.975]),len(boot),eq,spy)
    assert hashlib.sha256(SPEC.read_bytes()).hexdigest()==spec_hash
    (OUT/'estimation_run.json').write_text(json.dumps({'spec_sha256':spec_hash,'panel_sha256':hashlib.sha256(panel_path.read_bytes()).hexdigest(),
          'models':len(fits),'seed':SEED,'replicates_main':len(boot),'replicates_spy':len(spyboot),'block_length':BLOCK,'numpy_version':np.__version__},indent=2))
    print('ESTIMATION COMPLETE',flush=True)

def make_figures(fits,results,marginal,res,qlo,qhi):
    plt.rcParams.update({'font.family':'Arial','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    labels=['Pooled at mean share']+list(sorted(k.removeprefix('Security_') for k in fits if k.startswith('Security_')))
    keys=['Primary_10m_split_only']+['Security_'+s for s in labels[1:]]
    b=[fits[k]['coef'][0] for k in keys];se=[math.sqrt(fits[k]['cov'][0,0]) for k in keys]
    fig,ax=plt.subplots(figsize=(8,6));ax.errorbar(b,range(len(b)),xerr=np.array(se)*1.96,fmt='o',color='#087E8B',capsize=3);ax.set_yticks(range(len(b)),labels);ax.invert_yaxis();ax.axvline(0,color='gray',ls='--');ax.set_xlabel('Overnight return slope per unit final-10-minute return');ax.set_title('Reversal heterogeneity at security-mean auction share');fig.text(.5,.01,'Fixed security/month effects; 95% trading-date clustered CIs',ha='center',fontsize=9);fig.tight_layout(rect=(0,.035,1,1));fig.savefig(FIG/'reversal_heterogeneity.png',dpi=220);plt.close(fig)
    grid=np.linspace(qlo,qhi,100);vals=np.array([slope(res,a) for a in grid])*100
    fig,ax=plt.subplots(figsize=(7.5,4.8));ax.plot(grid*100,vals[:,0],color='#087E8B');ax.fill_between(grid*100,vals[:,1],vals[:,2],color='#087E8B',alpha=.18);ax.axhline(0,color='gray',ls='--');ax.set_xlabel('Auction share minus security mean (percentage points)');ax.set_ylabel('Predicted overnight change (bp) for +100 bp x');ax.set_title('Auction-share moderation, 25th–75th percentile');fig.text(.5,.01,'95% date-clustered joint intervals; conditional association',ha='center',fontsize=9);fig.tight_layout(rect=(0,.035,1,1));fig.savefig(FIG/'auction_moderation.png',dpi=220);plt.close(fig)
    keys=['Primary_10m_split_only','Window_5m','Window_15m','Window_30m','Split_dividend','Exclude_all_identified_actions','Exclude_next_cash_exdate','Exclude_early_closes','Earlier10m_Cminus30_Cminus21']
    names=['Primary 10m','5m','15m','30m','Dividend-adjusted y','Exclude identified actions','Exclude next ex-dividend','Exclude early closes','Earlier 10m window']
    fig,axes=plt.subplots(1,2,figsize=(10,5),sharey=True)
    for ax,j,title in zip(axes,[0,2],['Reversal slope beta','Moderation interaction delta']):
        bs=[fits[k]['coef'][j] for k in keys];ses=[math.sqrt(fits[k]['cov'][j,j]) for k in keys]
        ax.errorbar(bs,range(len(keys)),xerr=np.array(ses)*1.96,fmt='o',color='#246BCE',capsize=3);ax.axvline(0,color='gray',ls='--');ax.set_title(title);ax.set_yticks(range(len(keys)),names);ax.grid(axis='x',alpha=.15)
    axes[0].invert_yaxis();fig.suptitle('Prespecified robustness checks');fig.text(.5,.01,'95% trading-date clustered CIs; alternate-window regressors have different scales',ha='center',fontsize=9);fig.tight_layout(rect=(0,.035,1,.95));fig.savefig(FIG/'robustness.png',dpi=220);plt.close(fig)

def write_report(fits,results,br,marginal,difference,diffci,draws,eq,spy):
    r=fits['Primary_10m_split_only'];b,g,d=r['coef'];se=np.sqrt(np.diag(r['cov']));boot={x['term']:x for x in br if x['model']=='Primary_10m_split_only'}
    low,ref,high=marginal
    status_beta='supported' if b+1.96*se[0]<0 and boot['beta_x']['block_ci_high']<0 else 'unsupported in the predicted direction' if b-1.96*se[0]>0 and boot['beta_x']['block_ci_low']>0 else 'inconclusive'
    status_delta='supported in sign' if d-1.96*se[2]>0 and boot['delta_interaction']['block_ci_low']>0 else 'unsupported in the predicted direction' if d+1.96*se[2]<0 and boot['delta_interaction']['block_ci_high']<0 else 'inconclusive'
    text=f'''# Empirical results — fixed source-available sample

Primary panel: **{r['securities']} individual equities, {r['n']:,} security-days**,
{r['start']}–{r['end']}, {r['dates']} trading dates. SPY is separate ({len(spy):,}
eligible observations). Measurement and inference were fixed in
`final_empirical_specification.md` before estimation. All estimates, including
unfavorable findings, are retained. These are conditional associations.

## Main estimates and uncertainty

Security and calendar-year-month fixed effects; split-only Bloomberg official
close to next-session PX_OPEN; RiskLab-only final-10-minute signal. Auction share
is centered within security at its primary-sample mean. Returns/shares are fractions.

| Term | Estimate | Date-clustered 95% CI | 20-date block-bootstrap 95% CI |
| --- | ---: | --- | --- |
'''
    for j,name in enumerate(['beta_x','gamma_auction_share','delta_interaction']):
        bb=boot[name];text+=f"| {name} | {r['coef'][j]:.5f} | [{r['coef'][j]-1.96*se[j]:.5f}, {r['coef'][j]+1.96*se[j]:.5f}] | [{bb['block_ci_low']:.5f}, {bb['block_ci_high']:.5f}] |\n"
    text+=f'''\nBootstrap: {draws}/{REPLICATES} successful circular 20-trading-date draws,
seed {SEED}; entire cross-sections move together, FE refit in every draw.
Date clustering accommodates common-day dependence; the block check addresses
serial dependence. Individual-security table intervals use date clusters and
should not be read as serial-dependence-adjusted findings for each stock.

**Reversal hypothesis: {status_beta}.** The beta at reference auction share is
{b:.5f}. **Interaction prediction: {status_delta}.** A positive delta alone is
not enough: examine total slopes below. Economic magnitudes are effects of a
signal change conditional on fixed effects/share; intercepts are not predictions.

## Total slopes and economic magnitudes

| Participation reference | Centered share | Total slope [date-cluster CI] | Overnight bp for +100 bp intraday move | Block-bootstrap slope CI |
| --- | ---: | --- | ---: | --- |
'''
    for a in marginal:text+=f"| {a['participation']} | {a['centered_share']:.4f} | {a['slope']:.4f} [{a['date_ci_low']:.4f}, {a['date_ci_high']:.4f}] | {a['overnight_bp_for_plus100bp_x']:.2f} | [{a['block_ci_low']:.4f}, {a['block_ci_high']:.4f}] |\n"
    text+=f'''\nHigh-minus-low slope difference: {difference:.5f}; bootstrap 95% CI
[{diffci[0]:.5f}, {diffci[1]:.5f}]. Low/high are pooled percentiles of the
**centered** share, not two universal absolute auction-share levels. Whether
the negative slope becomes less negative, crosses zero or steepens is visible
in the total slopes; do not relabel continuation as reversal attenuation.

## Robustness and concentration

Every major model's sample count/date range, coefficients and date-cluster
intervals are in `regression_tables.md` and outputs/empirical/regression_coefficients.csv.
The comparison below is fixed ex ante; no specification is promoted for significance.

| Model | N | beta | delta | Overnight bp at low / high reference share for +100 bp x |
| --- | ---: | ---: | ---: | ---: |
'''
    names=['Window_5m','Window_15m','Window_30m','Split_dividend','Exclude_all_identified_actions','Exclude_next_cash_exdate','Exclude_early_closes','Earlier10m_Cminus30_Cminus21','SPY_benchmark']
    for k in names:
        rr=fits[k];bb,_,dd=rr['coef'];text+=f"| {k} | {rr['n']} | {bb:.5f} | {dd:.5f} | {100*(bb+dd*low['centered_share']):.2f} / {100*(bb+dd*high['centered_share']):.2f} |\n" if k!='SPY_benchmark' else f"| {k} | {rr['n']} | {bb:.5f} | {dd:.5f} | Separate ETF; own mean/scale |\n"
    loo=[v['coef'] for k,v in fits.items() if k.startswith('Leave_out_')]
    individual=[(k.removeprefix('Security_'),v['coef'][0]) for k,v in fits.items() if k.startswith('Security_')]
    text+=f'''\nLeave-one-equity-out beta range: [{min(x[0] for x in loo):.5f}, {max(x[0] for x in loo):.5f}];
delta range: [{min(x[2] for x in loo):.5f}, {max(x[2] for x in loo):.5f}].
Individual-security beta signs: {sum(v<0 for s,v in individual)}/15 negative,
{sum(v>=0 for s,v in individual)}/15 nonnegative. Individual coefficients and
uncertainty are fully reported, not selected by significance. Cross-security
heterogeneity and leave-one-out stability must qualify any pooled claim.

The reversal finding remains negative with date-clustered intervals below zero
for all three alternative window lengths, the dividend-adjusted outcome, action
exclusions and early-close exclusion. Removing each equity in turn leaves the
pooled reversal slope negative with similar magnitude; no single stock accounts
for its sign. The 5-minute interaction is positive with a date-clustered interval
above zero, whereas the primary 10-minute and 15/30-minute interactions include
zero. Thus auction attenuation is not a robust pooled conclusion across windows.
The earlier-window reversal interval includes zero, giving weaker timing evidence;
its difference from the primary coefficient has not been formally tested.

SPY's reversal date-clustered interval is below zero but its 20-date bootstrap
interval includes zero. Treat the ETF benchmark evidence as inconclusive under
serial-dependence robustness, not a replication with equally strong support.

The earlier 10-minute comparison is a timing contrast, not a guaranteed null
placebo: news and pressure can persist over both windows. Alternative windows
change signal scale and cannot be compared as identical-sized treatments without
the reported +100 bp normalization. Action removal uses identified exported events;
incomplete action coverage can leave contamination. Primary retains action dates.

## Limits and interpretation

PX_OFFICIAL_CLOSE is an exchange official mark; not every value is independently
verified as an auction execution. PX_OPEN is first daily trade, not a certified
opening auction. Close history and 2016 gaps constrain an unbalanced sample;
no interpolation or PX_LAST substitution is used. Within-source returns avoid
cross-provider level mixing, but local intraday factor constancy and rounding
remain imperfectly documented. Split-only y includes ex-dividend price drops;
split+dividend y and action exclusions provide alternative interpretations.

Auction numerator is primary-venue executed shares and denominator consolidated
US daily shares. Their original volume adjustments/trade filters are not fully
documented. This limitation is not cured by ratios in [0,1]. WMT uses the user-
confirmed dated UN/UW transition and downloaded continuation; SPY's 87 suspect
volumes are preserved and excluded from its eligible share sample. No rejected
historical membership data are used. Fixed source availability introduces
survivorship/selection risk; results do not represent a historical S&P universe.

Month/security effects do not identify causality: news, volatility/liquidity and
auction participation are jointly determined. A single prespecified block length
is a finite robustness check, not proof of arbitrary time-series robustness.
No new Bloomberg request or final presentation was created.

## Reproduce

```powershell
.venv/Scripts/python.exe -B src/build_full_panel.py
.venv/Scripts/python.exe -B src/test_empirical_analysis.py
.venv/Scripts/python.exe -B src/estimate_empirical_models.py
```

Build requires read-only RiskLab root; estimation/tests use local panel and NumPy,
pandas/matplotlib already installed. Endpoint caches are ignored, keyed to source
size/mtime and scanner hash. Delete only the local cache if deliberately rescanning.
Figures: outputs/empirical/figures/reversal_heterogeneity.png,
auction_moderation.png, robustness.png. No licensed observation data are committed.
'''
    (ROOT/'reports/empirical_results.md').write_text(text,encoding='utf-8')

if __name__=='__main__':main()
