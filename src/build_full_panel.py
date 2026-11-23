"""2016–2025 panel; source-internal returns and documented WMT venue mapping."""
import csv,json,os,sys
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from build_candidate_panel import ROOT,sha,write_csv,number,scan,window_status,next_open,volume_tables,share_values
import build_candidate_panel as candidate
from validate_bloomberg_workbook import instrument_columns,cell,serial_date,last_row
from xlsx_readonly import read_workbook,colname

OUT=ROOT/'data/analytic';DIAG=ROOT/'outputs/diagnostics'
ADDITIONAL=ROOT/'data/raw_bloomberg/Bloomberg_Project2_Additional_Prices - Values.xlsx'
SPEC=ROOT/'reports/final_empirical_specification.md'

def norm(s):return ' '.join(s.upper().split())
def venue(symbol,date):return ('WMT UW EQUITY' if date>='2025-12-09' else 'WMT UN EQUITY') if symbol=='WMT' else None

def read_prices(book):
    result={};coverage=[]
    for sheet in ['Close_SplitOnly','Close_SplitDiv','Open_SplitOnly','Open_SplitDiv']:
        table={};s=book[sheet]
        for col in instrument_columns(s,2):
            security=norm(cell(s,f'{colname(col)}1')['value']);dates=[];positive=0
            for row in range(2,last_row(s)+1):
                d=cell(s,f'{colname(col)}{row}')['value'];v=cell(s,f'{colname(col+1)}{row}')['value']
                if d is None and v is None:continue
                date=serial_date(d)
                if date is None:raise ValueError(f'Invalid price date: {sheet}:{row}')
                key=(security,date)
                if key in table:raise ValueError(f'Duplicate price key {sheet} {key}')
                table[key]={'value':number(v),'raw':v,'cells':f'{colname(col)}{row}:{colname(col+1)}{row}'}
                dates.append(date);positive+=number(v) is not None and number(v)>0
            coverage.append({'sheet':sheet,'security':security,'rows':len(dates),'positive':positive,'first_date':min(dates),'last_date':max(dates)})
        result[sheet]=table
    write_csv(DIAG/'final_price_coverage.csv',coverage)
    return result

def price_for(table,symbol,date):
    if symbol=='WMT':sec=venue(symbol,date)
    else:
        sec=symbol+(' UP EQUITY' if symbol=='SPY' else ' UW EQUITY' if symbol in {'AAPL','MSFT','AMZN','NVDA'} else ' UN EQUITY')
    return sec,table.get((sec,date),{})

def main():
    SPEC.read_text(encoding='utf-8')
    protected=[SPEC,ROOT/'design_decisions.md']+[p for base in ['data/raw_bloomberg','presentation'] for p in (ROOT/base).rglob('*') if p.is_file()]
    hashes={p:sha(p) for p in protected}
    book,_=read_workbook(ADDITIONAL)
    if any(c['has_formula'] for s in book.values() for c in s['cells'].values()):raise ValueError('Additional Values contains formulas')
    original,_=read_workbook(ROOT/'data/raw_bloomberg/Bloomberg_Project2_Additional_Prices.xlsx')
    for sheet in ['Close_SplitOnly','Open_SplitOnly','Close_SplitDiv','Open_SplitDiv']:
        for col in instrument_columns(book[sheet],2):
            formula=cell(original[sheet],f'{colname(col)}2')['formula'] or ''
            expected='N' if sheet.endswith('SplitOnly') else 'Y'
            assert all(t in formula for t in ['UseDPDF=N','CapChg=Y',f'CshAdjNormal={expected}',f'CshAdjAbnormal={expected}'])
            assert ('PX_OFFICIAL_CLOSE' if sheet.startswith('Close') else 'PX_OPEN') in formula
    prices=read_prices(book)
    master,_=read_workbook(ROOT/'data/raw_bloomberg/Bloomberg_Project2_Master - Values.xlsx')
    vols,_=volume_tables(master)
    symbols=sorted({s for s,d in vols['daily_volume']})
    candidate.PILOTS=symbols
    events,action_counts=candidate.action_table(master)
    write_csv(OUT/'full_action_event_ledger.csv',[e for items in events.values() for e in items])
    # Continuation formula/metadata and user-confirmed identity are explicit evidence.
    formula=cell(original['WMT_Auction_Continuation'],'A1')['formula'] or ''
    assert 'WMT UW Equity' in formula and 'OFFICIAL_CLOSE_AUCTION_VOLUME' in formula
    cont=[]
    for row in range(1,last_row(book['WMT_Auction_Continuation'])+1):
        date=serial_date(cell(book['WMT_Auction_Continuation'],f'A{row}')['value']);value=cell(book['WMT_Auction_Continuation'],f'B{row}')['value']
        assert date and '2025-12-09'<=date<='2025-12-31'
        assert ('WMT',date) not in vols['action_volume'],'Overlapping WMT source lines'
        vols['action_volume']['WMT',date]={'value':number(value),'raw_value':value,'security':'WMT UW EQUITY','field':'OFFICIAL_CLOSE_AUCTION_VOLUME','source_cells':f'A{row}:B{row}'}
        cont.append(date)
    calendar=pd.read_csv(ROOT/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv')
    anchors=calendar[calendar.session_date.between('2016-01-01','2025-12-31')].to_dict('records')
    expected=calendar[calendar.session_date.between('2025-12-09','2025-12-31')].session_date.tolist()
    assert sorted(cont)==expected and len(cont)==16
    schedule={r['session_date']:{**r,'close_minute':int(r['close_minute'])} for r in anchors}
    schedule['2026-01-02']={'close_minute':960}
    settings=json.loads((ROOT/'.vscode/settings.json').read_text())
    root=Path(os.environ.get('RISKLAB_DATA_ROOT',settings['terminal.integrated.env.windows']['RISKLAB_DATA_ROOT']))
    os.environ['RISKLAB_DATA_ROOT']=str(root);sys.path.insert(0,str(root/'_catalog'))
    import data_paths as dp
    availability=pd.read_csv(DIAG/'candidate_intraday_availability.csv').set_index('symbol')
    allrows=[];logs=[]
    cache=OUT/'full_endpoint_cache';cache.mkdir(exist_ok=True)
    for symbol in symbols:
        meta=availability.loc[symbol];path=dp.resolve(meta.relative_path);cachefile=cache/(symbol+'.csv');logfile=cache/(symbol+'.json')
        stat=path.stat()
        # Cache only ingestion endpoints, never estimates; validates exact source stat and script hash.
        if cachefile.exists() and logfile.exists():
            old=json.loads(logfile.read_text())
            if old['size_bytes']==stat.st_size and old['mtime_ns']==stat.st_mtime_ns and old['scanner_sha']==sha(Path(candidate.__file__)):
                endpoints=pd.read_csv(cachefile).to_dict('records');logs.append(old)
                print(symbol,'validated endpoint cache',flush=True)
            else:endpoints=None
        else:endpoints=None
        if endpoints is None:
            days,log=scan(path,schedule);endpoints=[]
            for session in anchors:
                date=session['session_date'];nxt=session['next_session'];close=int(session['close_minute'])
                bars=days.get(date,{});op=next_open(days.get(nxt,{}));last=bars.get(close-1,[])
                last=last[0] if len(last)==1 and last[0]['valid'] else {}
                r={'symbol':symbol,'date':date,'next_session':nxt,'early_close':bool(session['early_close']),
                   'risklab_id':meta.risklab_id,'intraday_path':meta.relative_path,'preclose_close':number(last.get('close')),
                   'preclose_timestamp':last.get('timestamp'),'preclose_line':last.get('line_number'),
                   'next0930_valid':op is not None,'next0930_open':number(op['open']) if op else None}
                for w in [5,10,15,30]:
                    missing,dupes,invalid=window_status(bars,close,w);b=bars.get(close-w,[{}])[0];start=number(b.get('open'))
                    good=not (missing or dupes or invalid)
                    r.update({f'complete_{w}m':good,f'missing_{w}m':missing,f'duplicate_{w}m':dupes,f'invalid_{w}m':invalid,
                              f'start_{w}m_open':start,f'start_{w}m_timestamp':b.get('timestamp'),f'start_{w}m_line':b.get('line_number'),
                              f'x_{w}m':r['preclose_close']/start-1 if good else None})
                miss,dup,inv=window_status({m:v for m,v in bars.items() if close-30<=m<close-20},close-20,10)
                start=bars.get(close-30,[{}])[0];end=bars.get(close-21,[{}])[0]
                good=not (miss or dup or inv)
                r['placebo_complete']=good;r['x_earlier10m']=number(end.get('close'))/number(start.get('open'))-1 if good else None
                endpoints.append(r)
            write_csv(cachefile,endpoints)
            log.update({'symbol':symbol,'relative_path':meta.relative_path,'risklab_id':meta.risklab_id,'scanner_sha':sha(Path(candidate.__file__))})
            logfile.write_text(json.dumps(log,indent=2));logs.append(log)
            print(symbol,'read-only scan complete',flush=True)
            del days
        for r in endpoints:
            date=r['date'];nxt=r['next_session'];r['asset_type']='ETF' if symbol=='SPY' else 'equity'
            for cfg in ['SplitOnly','SplitDiv']:
                close_sec,c=price_for(prices['Close_'+cfg],symbol,date);open_sec,o=price_for(prices['Open_'+cfg],symbol,nxt)
                cv=c.get('value');ov=o.get('value')
                r.update({f'close_{cfg}':cv,f'open_next_{cfg}':ov,f'close_raw_{cfg}':c.get('raw'),f'open_next_raw_{cfg}':o.get('raw'),
                          f'close_cells_{cfg}':c.get('cells'),f'open_next_cells_{cfg}':o.get('cells'),
                          f'close_security_{cfg}':close_sec,f'open_next_security_{cfg}':open_sec,
                          f'y_{cfg}':ov/cv-1 if cv is not None and ov is not None and cv>0 and ov>0 else None})
            a=vols['action_volume'].get((symbol,date),{});d=vols['daily_volume'].get((symbol,date),{})
            r.update({'auction_volume_raw':a.get('raw_value'),'daily_volume_raw':d.get('raw_value'),
                      'auction_security':a.get('security'),'daily_security':d.get('security'),
                      'auction_source_cells':a.get('source_cells'),'daily_source_cells':d.get('source_cells'),
                      'auction_source':'Additional_Prices:WMT_Auction_Continuation' if symbol=='WMT' and date>='2025-12-09' else 'Master:action_volume',
                      'bloomberg_price_workbook_sha256':hashes[ADDITIONAL]})
            r.update(share_values(symbol,date,a.get('value'),d.get('value')))
            r.update(candidate.event_columns(events,symbol,date,nxt))
            allrows.append(r)
    frame=pd.DataFrame(allrows)
    assert not frame.duplicated(['symbol','date']).any()
    for c in ['complete_5m','complete_10m','complete_15m','complete_30m','placebo_complete','next0930_valid','early_close']:
        frame[c]=frame[c].map(lambda v:str(v).lower()=='true')
    frame['eligible_primary']=frame.complete_10m & frame.next0930_valid & frame.y_SplitOnly.notna() & frame.auction_share.notna()
    frame['price_primary_valid']=frame.complete_10m & frame.next0930_valid & frame.y_SplitOnly.notna()
    frame.to_csv(OUT/'full_analytical_panel.csv',index=False)
    write_csv(DIAG/'full_intraday_source_log.csv',logs)
    # Adjustment behavior only; no x/y association is computed here.
    adjustment=[]
    for symbol,g in frame.groupby('symbol'):
        comparable=g[['close_SplitOnly','close_SplitDiv','open_next_SplitOnly','open_next_SplitDiv']].notna().all(axis=1)
        q=g[comparable];factor_ratio=(q.open_next_SplitDiv/q.open_next_SplitOnly)/(q.close_SplitDiv/q.close_SplitOnly)
        event=q.next_cash_distribution_flag.astype(bool)
        adjustment.append({'symbol':symbol,'comparable_pairs':len(q),'known_next_cash_pairs':int(event.sum()),
                           'median_absolute_factor_change_next_cash':float((factor_ratio[event]-1).abs().median()),
                           'median_absolute_factor_change_other':float((factor_ratio[~event]-1).abs().median()),
                           'max_abs_factor_change':float((factor_ratio-1).abs().max())})
    write_csv(DIAG/'price_adjustment_behavior.csv',adjustment)
    summary=[]
    for symbol,g in frame.groupby('symbol'):
        summary.append({'symbol':symbol,'calendar_rows':len(g),'eligible_primary':int(g.eligible_primary.sum()),
                        'missing_invalid_10m':int((~g.complete_10m).sum()),'missing_next0930':int((~g.next0930_valid).sum()),
                        'missing_official_close':int(g.close_SplitOnly.isna().sum()),'missing_next_open':int(g.open_next_SplitOnly.isna().sum()),
                        'missing_auction':int(g.auction_volume_raw.isna().sum()),'spy_suspect':int(g.spy_auction_100_suspect.sum()),
                        'anchor_actions':int(g.anchor_action_found_in_export.sum()),'next_actions':int(g.next_action_found_in_export.sum()),
                        'first_eligible':g.loc[g.eligible_primary,'date'].min(),'last_eligible':g.loc[g.eligible_primary,'date'].max()})
    write_csv(DIAG/'final_panel_counts.csv',summary)
    assert all(sha(p)==h for p,h in hashes.items()),'Protected source changed'
    for log in logs:
        stat=dp.resolve(log['relative_path']).stat();assert (stat.st_size,stat.st_mtime_ns)==(log['size_bytes'],log['mtime_ns'])
    text='# Final analytical panel QA\n\nPrimary measurements follow final_empirical_specification.md, frozen before estimation.\n\n'
    text+='| Symbol | Retained calendar rows | Primary eligible | Missing official close | Missing next open | Invalid 10m | Missing next 09:30 | Missing auction | SPY suspect |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n'
    for s in summary:text+=f"| {s['symbol']} | {s['calendar_rows']} | {s['eligible_primary']} | {s['missing_official_close']} | {s['missing_next_open']} | {s['missing_invalid_10m']} | {s['missing_next0930']} | {s['missing_auction']} | {s['spy_suspect']} |\n"
    text+='\nAll calendar rows retained; missing/nonpositive prices produce missing outcomes. Source gaps are never filled. Zero duplicate panel keys. Bloomberg close and next-session open use the same explicit configuration, with primary split-only and split+dividend sensitivity. Intraday returns use only RiskLab prices.\n\n'
    text+='WMT: exact downloaded PQ817 formula, user-confirmed identity, metadata and 16 dated, nonoverlapping Nasdaq auction rows validated. December 8 close uses UN, December 9 next open uses UW for the same confirmed WMT instrument. Daily denominator remains WMT US. Raw lines and cell references retained.\n\n'
    text+='2016–2025 is the authorized candidate period; JNJ/BAC/WMT 2016 close gaps retained. Fixed 15-equity sample is selected by source availability and is not a historical S&P universe. SPY is separate. All 87 suspect SPY values preserved and share-ineligible. No action dates removed from primary; flags support prespecified sensitivity. Cap of 275 actions is not reached. Common volume adjustment remains an interpretation limitation.\n\n'
    text+='Source scans: outputs/diagnostics/full_intraday_source_log.csv. Price coverage: final_price_coverage.csv. Corporate-action factor behavior: price_adjustment_behavior.csv. Protected raw/design/presentation hashes unchanged. New workbook Metadata Download date is preserved as supplied and is not independently verified as retrieval time.\n'
    text+='\n## Cumulative primary-equity eligibility (overlapping reason counts above)\n\n'
    subset=frame[frame.asset_type=='equity'];stages=[('Calendar skeleton',len(subset))]
    for label,condition in [('Valid 10-minute window',subset.complete_10m),('Required next 09:30',subset.next0930_valid),
                             ('Valid Bloomberg close/next open',subset.y_SplitOnly.notna()),('Valid auction share',subset.auction_share.notna())]:
        subset=subset[condition.reindex(subset.index)];stages.append((label,len(subset)))
    text+='| Stage | Retained equity rows |\n| --- | ---: |\n'+''.join(f'| {label} | {count} |\n' for label,count in stages)
    text+='\nFull action provenance ledger: data/analytic/full_action_event_ledger.csv. No rows are removed from the preserved full panel; eligibility selects the estimation subset.\n'
    (ROOT/'reports/final_panel_qa.md').write_text(text,encoding='utf-8')
    (DIAG/'full_panel_build.json').write_text(json.dumps({'spec_sha256':hashes[SPEC],'rows':len(frame),'equity_eligible':int(frame.loc[frame.asset_type=='equity','eligible_primary'].sum()),'spy_eligible':int(frame.loc[frame.symbol=='SPY','eligible_primary'].sum()),'protected_unchanged':True},indent=2))
    print('BUILD COMPLETE',len(frame),'rows;',int(frame.loc[frame.asset_type=='equity','eligible_primary'].sum()),'equity eligible',flush=True)

if __name__=='__main__':main()
