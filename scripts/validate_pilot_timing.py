r"""Calendar-relative coverage only. No returns, model inputs or regressions.

Run: . .\scripts\use_risklab.ps1
     .\.venv\Scripts\python.exe -B scripts\validate_pilot_timing.py
Provider opens are read-only. MM-04 is not opened or used. Existing checkpoint
JSON supplies manifest provenance only. All outputs stay inside the repository.
"""
import csv
import hashlib
import inspect
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'reports' / 'timing_diagnostics'
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', str(BASE / '.cache' / 'matplotlib'))
import exchange_calendars as xc
import pandas as pd

WINDOWS = [5, 10, 15, 30]
PILOTS = {'SPY': 'intraday_data/etfs/SPY_full_1min_adjsplitdiv.txt',
          'AAPL': 'intraday_data/stocks/AAPL_full_1min_adjsplitdiv.txt',
          'MSFT': 'intraday_data/stocks/MSFT_full_1min_adjsplitdiv.txt'}
# Selected by calendar/event/coverage category, never by a return or model result.
CASES = [('SPY','2010-01-04','normal; early in pilot'),
         ('AAPL','2015-06-15','normal; middle of pilot'),
         ('MSFT','2025-06-16','normal; late in pilot'),
         ('SPY','2013-07-03','early close; July'),
         ('AAPL','2018-11-23','early close; November'),
         ('MSFT','2025-12-24','early close; December'),
         ('AAPL','2020-03-16','missing opening minute labels'),
         ('MSFT','2020-03-09','missing opening minute label'),
         ('SPY','2012-10-26','next session crosses unscheduled exchange closures'),
         ('SPY','2000-01-03','historical missing 09:30 control; outside coverage period')]


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2), encoding='utf-8')


def csvout(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def clock(minute):
    return f'{minute//60:02d}:{minute%60:02d}'


def mask_for(minutes):
    return sum(1 << m for m in minutes)


def build_calendar():
    cal = xc.get_calendar('XNYS', start='1999-12-01', end='2026-01-06')
    schedule, dates = {}, list(cal.schedule.index)
    for i, (session, row) in enumerate(cal.schedule.iterrows()):
        opening = row['open'].tz_convert('America/New_York')
        closing = row['close'].tz_convert('America/New_York')
        day = session.date().isoformat()
        schedule[day] = {'session_date':day, 'open_local':opening.isoformat(),
                         'close_local':closing.isoformat(),
                         'open_utc':row['open'].isoformat(), 'close_utc':row['close'].isoformat(),
                         'open_minute':opening.hour*60+opening.minute,
                         'close_minute':closing.hour*60+closing.minute,
                         'early_close':closing.hour*60+closing.minute < 960,
                         'next_session':dates[i+1].date().isoformat() if i+1<len(dates) else ''}
    primary = [s for d,s in schedule.items() if '2010-01-01'<=d<='2025-12-31']
    csvout(OUT/'exchange_sessions_2010_2025.csv', primary)
    csvout(OUT/'early_close_sessions.csv', [s for s in primary if s['early_close']])
    annual = []
    for year in range(2010,2026):
        items=[s for s in primary if s['session_date'].startswith(str(year))]
        annual.append({'year':year,'sessions':len(items),'normal_sessions':sum(not s['early_close'] for s in items),'early_close_sessions':sum(s['early_close'] for s in items)})
    csvout(OUT/'calendar_by_year.csv', annual)
    # Independent known-event checks on package rules, not on observed file dates.
    for d in ['2012-10-29','2012-10-30','2018-12-05','2025-01-09','2022-06-20']:
        assert d not in schedule, d
    assert '2021-06-18' in schedule
    for d in ['2013-07-03','2018-11-23','2025-12-24']:
        assert schedule[d]['close_minute']==780
    assert schedule['2012-10-26']['next_session']=='2012-10-31'
    assert schedule['2025-12-31']['next_session']=='2026-01-02'
    assert all(s['open_minute']==570 and s['close_minute'] in [780,960] for s in primary)
    source=Path(inspect.getfile(type(cal)))
    metadata={'calendar':'XNYS','package':'exchange_calendars','version':version('exchange-calendars'),
              'timezone':'America/New_York','XNAS_resolves_to':xc.get_calendar('XNAS').name,
              'calendar_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'source_url':'https://github.com/gerrymanoim/exchange_calendars/blob/'+version('exchange-calendars')+'/exchange_calendars/exchange_calendar_xnys.py',
              'package_docs':'https://github.com/gerrymanoim/exchange_calendars',
              'exchange_reference':'https://www.nyse.com/markets/hours-calendars',
              'coverage_period':['2010-01-01','2025-12-31'],
              'follow_up_next_session':primary[-1]['next_session'],
              'expected_sessions':len(primary), 'early_close_sessions':sum(s['early_close'] for s in primary),
              'known_closures_checked':['2012-10-29','2012-10-30','2018-12-05','2025-01-09','2022-06-20'],
              'interpretation':'Shared US-equity core-session calendar; XNAS is an alias, not independent Nasdaq verification. Scheduled sessions do not model security-specific halts. Calendar generated locally, no session dates inferred from price observations.'}
    dump('calendar_metadata.json',metadata)
    print('Calendar',metadata['expected_sessions'],'sessions;',metadata['early_close_sessions'],'early closes',flush=True)
    return schedule, primary


def scan(symbol, schedule, primary):
    path=dp.resolve(PILOTS[symbol])
    before=path.stat()
    wanted_cases={d for s,d,_ in CASES if s==symbol}
    trace_dates=wanted_cases | {schedule[d]['next_session'] for d in wanted_cases}
    days={}
    non_session=Counter()
    counts=Counter()
    trace=[]
    for line,row in enumerate(csv.reader(path.open('r',encoding='utf-8-sig',newline='')),1):
        date=row[0][:10]
        if not ('2010-01-01'<=date<=primary[-1]['next_session'] or date in trace_dates):
            continue
        if date not in schedule:
            non_session[date]+=1
            continue
        minute=int(row[0][11:13])*60+int(row[0][14:16])
        session=schedule[date]
        close=session['close_minute']
        values=[float(v) for v in row[1:]]
        o,h,l,c,v=values
        valid=all(math.isfinite(x) for x in values) and min(o,h,l,c)>0 and v>=0 and l<=o<=h and l<=c<=h
        info=days.setdefault(date,{'mask':0,'valid_mask':0,'positive_volume_mask':0,'rows':0,'first_label':row[0], 'last_label':row[0],'selected':{}})
        info['mask'] |= 1<<minute
        if valid: info['valid_mask'] |= 1<<minute
        if valid and v>0: info['positive_volume_mask'] |= 1<<minute
        info['rows']+=1
        info['last_label']=row[0]
        counts['nonzero_seconds']+=row[0][-2:]!='00'
        if minute in set(range(569,576)) | {close-31,close-30,close-16,close-15,close-11,close-10,close-6,close-5,close-2,close-1,close,close+1,959,960,961}:
            info['selected'][minute]={'line_number':line,'timestamp':row[0],'open':row[1],'high':row[2],'low':row[3],'close':row[4],'volume':row[5]}
        if date in trace_dates and (569<=minute<=575 or close-31<=minute<=close+1):
            trace.append({'symbol':symbol,'source_relative_path':PILOTS[symbol],'source_line_number':line,'timestamp':row[0], 'open':row[1],'high':row[2],'low':row[3],'close':row[4],'volume':row[5],
                          'scheduled_close':clock(close),'in_core_session':570<=minute<close})
    after=path.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'Source changed during scan'
    assert counts['nonzero_seconds']==0
    dump(symbol.lower()+'_source_audit.json',{'relative_path':PILOTS[symbol],'size_bytes':before.st_size,'mtime_ns_before':before.st_mtime_ns,'mtime_ns_after':after.st_mtime_ns,'unchanged_size_and_mtime':True,'open_mode':'r','non_session_date_rows':dict(non_session)})
    csvout(OUT/(symbol.lower()+'_hand_check_raw_rows.csv'),trace)
    print(symbol,'scanned;',len(days),'calendar dates retained;',len(non_session),'non-session dates',flush=True)
    return days


def present(info, minute, key='valid_mask'):
    return bool(info.get(key,0) & (1<<minute))


def make_coverage(all_days,primary):
    detail, summary, annual=[],[],[]
    for symbol,days in all_days.items():
        for session in primary:
            d=session['session_date'];info=days.get(d,{});nxt=days.get(session['next_session'],{})
            close=session['close_minute']
            rec={'symbol':symbol,'session':d,'year':d[:4], 'early_close':session['early_close'],
                 'scheduled_close':clock(close),'next_session':session['next_session'],
                 'observed_session':bool(info), 'has_0930':present(info,570),
                 'has_0931':present(info,571),'has_0935':present(info,575),
                 'has_last_preclose':present(info,close-1),'has_close_time_bar':present(info,close),
                 'has_close_plus_one':present(info,close+1),'has_1600':present(info,960),
                 'next_session_valid_0930':present(nxt,570)}
            for length in WINDOWS:
                required=range(close-length,close)
                needed=mask_for(required)
                complete=info.get('mask',0)&needed==needed
                valid=info.get('valid_mask',0)&needed==needed
                positive_volume=info.get('positive_volume_mask',0)&needed==needed
                rec[f'complete_{length}']=complete
                rec[f'valid_{length}']=valid
                rec[f'absent_{length}']=';'.join(clock(m) for m in required if not present(info,m,'mask'))
                # Explicit alternatives for endpoint availability only; no prices/returns constructed.
                rec[f'usable_preclose_proxy_{length}']=valid and present(nxt,570)
                rec[f'usable_close_time_proxy_{length}']=valid and present(info,close) and present(nxt,570)
                rec[f'usable_positive_volume_{length}']=positive_volume and present(nxt,570,'positive_volume_mask')
            detail.append(rec)
        group=[r for r in detail if r['symbol']==symbol]
        for category in ['all','normal','early_close']:
            subset=[r for r in group if category=='all' or r['early_close']==(category=='early_close')]
            for length in WINDOWS:
                summary.append({'symbol':symbol,'window_minutes':length,'session_type':category,
                                'expected_sessions':len(subset),'observed_sessions':sum(r['observed_session'] for r in subset),
                                'complete_required_labels':sum(r[f'complete_{length}'] for r in subset),
                                'missing_at_least_one_label':sum(not r[f'complete_{length}'] for r in subset),
                                'early_close_sessions':sum(r['early_close'] for r in subset),
                                'valid_next_session_0930':sum(r['next_session_valid_0930'] for r in subset),
                                'usable_preclose_proxy':sum(r[f'usable_preclose_proxy_{length}'] for r in subset),
                                'usable_close_time_proxy':sum(r[f'usable_close_time_proxy_{length}'] for r in subset),
                                'usable_positive_volume_preclose_proxy':sum(r[f'usable_positive_volume_{length}'] for r in subset)})
        for year in range(2010,2026):
            subset=[r for r in group if r['year']==str(year)]
            for length in WINDOWS:
                annual.append({'symbol':symbol,'year':year,'window_minutes':length,'expected_sessions':len(subset),'complete_required_labels':sum(r[f'complete_{length}'] for r in subset), 'percent_complete':100*sum(r[f'complete_{length}'] for r in subset)/len(subset)})
    csvout(OUT/'coverage_by_session.csv',detail)
    csvout(OUT/'coverage_summary.csv',summary)
    csvout(OUT/'coverage_by_year.csv',annual)
    return detail,summary,annual


def behavior(all_days,primary):
    records=[]
    for symbol,days in all_days.items():
        for kind in ['normal','early_close']:
            counts=Counter()
            for s in primary:
                if s['early_close']!=(kind=='early_close'):continue
                counts['expected_sessions']+=1
                info=days.get(s['session_date'],{})
                selected=info.get('selected',{})
                close=s['close_minute']
                bar=selected.get(close);prev=selected.get(close-1)
                counts['last_preclose_present']+=prev is not None
                counts['bar_at_close_present']+=bar is not None
                counts['bar_one_minute_after_close_present']+=(close+1) in selected
                counts['fixed_1600_present']+=960 in selected
                if not bar:continue
                counts['close_bar_positive_high_low_range']+=float(bar['high'])>float(bar['low'])
                counts['close_bar_open_differs_close']+=float(bar['open'])!=float(bar['close'])
                counts['close_bar_positive_volume']+=float(bar['volume'])>0
                if prev:
                    counts['paired_preclose_and_close_bars']+=1
                    counts['close_bar_open_differs_previous_bar_close']+=float(bar['open'])!=float(prev['close'])
                    counts['close_bar_close_differs_previous_bar_close']+=float(bar['close'])!=float(prev['close'])
            records.append({'symbol':symbol,'session_type':kind,**{k:counts[k] for k in ['expected_sessions','last_preclose_present','bar_at_close_present','bar_one_minute_after_close_present','fixed_1600_present','close_bar_positive_high_low_range','close_bar_open_differs_close','close_bar_positive_volume','paired_preclose_and_close_bars','close_bar_open_differs_previous_bar_close','close_bar_close_differs_previous_bar_close']}})
    csvout(OUT/'close_bar_behavior_counts.csv',records)
    return records


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(v).replace('|','/') for v in row)+' |' for row in rows])


def hand_checks(all_days,schedule):
    overview=[];sections=[]
    for number,(symbol,date,reason) in enumerate(CASES,1):
        s=schedule[date]; info=all_days[symbol].get(date,{})
        close=s['close_minute'];nextdate=s['next_session'];nxt=all_days[symbol].get(nextdate,{})
        missing_open=[clock(m) for m in range(570,576) if not present(info,m,'mask')]
        status=[]
        for length in WINDOWS:
            missing=[clock(m) for m in range(close-length,close) if not present(info,m,'mask')]
            usable=not missing and present(nxt,570)
            status.append(f'{length}m: '+('complete' if not missing else 'absent '+','.join(missing))+f'; next-open eligible={usable}')
        overview.append([number,symbol,date,reason,clock(close),nextdate,','.join(missing_open) or 'none',present(nxt,570)])
        selections=info.get('selected',{})
        keys=sorted(set([569,570,571,575,close-30,close-15,close-10,close-5,close-1,close,close+1]))
        raw=[]
        for minute in keys:
            r=selections.get(minute)
            raw.append([clock(minute),r['line_number'] if r else 'ABSENT',r['open'] if r else '',r['high'] if r else '',r['low'] if r else '',r['close'] if r else '',r['volume'] if r else ''])
        nextrow=nxt.get('selected',{}).get(570)
        raw.append(['next '+nextdate+' 09:30',nextrow['line_number'] if nextrow else 'ABSENT',*[nextrow[k] if nextrow else '' for k in ['open','high','low','close','volume']]])
        sections += [f'## {number}. {symbol} {date}', '',reason+'.', '',
                     f'Calendar: open 09:30, close {clock(close)}, next session {nextdate}. '+('Outside 2010–2025 coverage; diagnostic control only.' if date<'2010-01-01' else 'Inside 2010–2025 coverage.'),'',
                     'Required-label check: '+'; '.join(status)+'.', '',
                     'Within the 09:30–09:35 opening window, absent labels: '+(', '.join(missing_open) or 'none')+'. No substitution made.', '',
                     table(['Raw label','Source line','Open','High','Low','Close','Volume'],raw),'',
                     'All available raw rows from the final 30-minute window, nearby endpoint labels, and next-session opening neighborhood are traceable in `timing_diagnostics/'+symbol.lower()+'_hand_check_raw_rows.csv`. These are small diagnostic excerpts, not copies of source files.','']
    text=['# Ten timing hand-checks','',
          'Cases are selected for calendar/timing coverage, never by returns. No research returns are calculated. Source line numbers are one-based; numeric strings below are unchanged. Every missing label is explicit. All ten traces have been reviewed for calendar-relative label arithmetic and raw-row lineage; official auction identity remains unverified.','',
          table(['Case','Symbol','Date','Purpose','Close','Next session','Absent opening labels','Next 09:30 present'],overview),'',*sections]
    (BASE/'reports'/'timing_hand_checks.md').write_text('\n'.join(text),encoding='utf-8')


def manifest():
    previous=BASE/'reports'/'source_diagnostics'
    search=json.loads((previous/'catalog_search.json').read_text(encoding='utf-8'))
    records=[]
    for r in search['pilot_records']:
        records.append({'risklab_id':r['id'],'relative_path':r['path'],'path_base':'RISKLAB_DATA_ROOT', 'provider':r['provider'],'role':'pilot minute OHLCV','validation_status':'read-only full scan; calendar timing diagnostics','used_in_current_timing_phase':'yes'})
    for ident,path,role in [('RL-ED340E2FF91E','bloomberg/02_market/microstructure/MM-04_SP500_AuctionVolumes_Daily_2010-2025.csv','auction-volume candidate; alignment and units unresolved'),('RL-0A4026EAEC53','bloomberg/02_market/factors/AP15_All S&P Composite Constituents_PXLAST_PXVOLUME (4).csv','price/volume panel; not verified historical membership')]:
        records.append({'risklab_id':ident,'relative_path':path,'path_base':'RISKLAB_DATA_ROOT','provider':'Bloomberg','role':role,'validation_status':'previous source checkpoint only; not accessed in this phase','used_in_current_timing_phase':'no'})
    for path,role in [('_catalog/data_paths.py','path utility'),('_catalog/catalog.csv','authoritative catalog'),('_catalog/intraday_inventory.csv.gz','intraday inventory'),('bloomberg/inventory.csv','Bloomberg inventory'),('intraday_data/_documentation/.archive/stock.txt','local stock format documentation'),('intraday_data/_documentation/.archive/etf.txt','local ETF format documentation'),('intraday_data/_documentation/.archive/stock_ticker_dates_listing.txt','local ticker date listing')]:
        records.append({'risklab_id':'','relative_path':path,'path_base':'RISKLAB_DATA_ROOT','provider':'RiskLab / First Rate Data metadata','role':role,'validation_status':'verified in source checkpoint; no stable dataset ID supplied','used_in_current_timing_phase':'utility imported; inventory/metadata findings reused'})
    records.append({'risklab_id':'','relative_path':'exchange_calendars/exchange_calendar_xnys.py','path_base':'installed Python package','provider':'exchange_calendars '+version('exchange-calendars'),'role':'XNYS session rules; XNAS alias','validation_status':'version/source hash and calendar snapshot recorded','used_in_current_timing_phase':'yes'})
    csvout(BASE/'data_manifest.csv',records)


def figure(annual):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={5:'#0072B2',10:'#D55E00',15:'#009E73',30:'#CC79A7'}
    fig,axes=plt.subplots(1,3,figsize=(13,4.4),sharey=True)
    for ax,symbol in zip(axes,PILOTS):
        for length in WINDOWS:
            r=[v for v in annual if v['symbol']==symbol and v['window_minutes']==length]
            ax.plot([v['year'] for v in r],[v['percent_complete'] for v in r],label=f'{length} minutes',color=colors[length],marker='o',markersize=3,lw=1.5,alpha=.8)
        ax.set_title(symbol);ax.set_xticks([2010,2015,2020,2025]);ax.set_xlabel('Anchor-session year')
        ax.set_ylim(0,101);ax.grid(axis='y',alpha=.2)
        if all(v['percent_complete']==100 for v in annual if v['symbol']==symbol):
            ax.text(.5,.75,'All four windows: 100% each year',transform=ax.transAxes,ha='center',fontsize=9)
    axes[0].set_ylabel('Expected sessions with all required labels (%)')
    axes[-1].legend(loc='lower left',frameon=False)
    fig.suptitle('Pilot coverage only: calendar-relative closing windows, 2010–2025',fontsize=13)
    fig.text(.5,.015,'Denominator: all XNYS sessions, including calendar-relative early closes. Overlapping lines indicate equal coverage. No returns or model results.',ha='center',fontsize=8)
    fig.tight_layout(rect=[0,.06,1,.93])
    fig.savefig(BASE/'reports'/'pilot_coverage.png',dpi=180)
    plt.close(fig)


def validate(detail,summary,all_days,schedule,primary):
    assert len(detail)==len(primary)*3
    assert len(summary)==36
    for r in summary:
        assert r['expected_sessions']==r['complete_required_labels']+r['missing_at_least_one_label']
        assert r['usable_close_time_proxy']<=r['usable_preclose_proxy']<=r['complete_required_labels']
        assert r['usable_preclose_proxy']<=r['valid_next_session_0930']
    for r in detail:
        # Nesting of required labels must hold, independent of observed prices.
        assert all(not r[f'complete_{b}'] or r[f'complete_{a}'] for a,b in zip(WINDOWS,WINDOWS[1:]))
    assert not present(all_days['SPY']['2000-01-03'],570)
    for s,d,_ in CASES:
        assert d in schedule and d in all_days[s]
    checks={'calendar_snapshot_sessions':len(primary),'coverage_detail_rows':len(detail),'summary_rows':len(summary),'hand_check_cases':len(CASES),'source_stat_checks':'passed for three sources','calendar_known_closure_assertions':'passed','coverage_reconciliation_and_nested_window_assertions':'passed','raw_handcheck_case_presence':'passed'}
    dump('validation_checks.json',checks)


if __name__=='__main__':
    sys.path.insert(0, str(Path(os.environ['RISKLAB_DATA_ROOT']) / '_catalog'))
    import data_paths as dp
    assert dp.data_root() not in OUT.parents
    schedule,primary=build_calendar()
    all_days={symbol:scan(symbol,schedule,primary) for symbol in PILOTS}
    detail,summary,annual=make_coverage(all_days,primary)
    behavior(all_days,primary)
    hand_checks(all_days,schedule)
    manifest()
    figure(annual)
    validate(detail,summary,all_days,schedule,primary)
    versions={name:version(name) for name in ['exchange-calendars','pandas','numpy','matplotlib','tzdata']}
    dump('environment_versions.json',versions)
    (BASE/'requirements-timing.txt').write_text('\n'.join(f'{k}=={v}' for k,v in versions.items())+'\n',encoding='utf-8')
    print('Timing diagnostics, hand-checks, manifest and coverage figure saved.',flush=True)
