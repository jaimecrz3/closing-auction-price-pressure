"""Read-only, provisional SPY/AAPL/MSFT candidate panel. No estimation.

Run with Python -B after configuring RISKLAB_DATA_ROOT, or use the root in the
workspace .vscode/settings.json. All licensed outputs stay in ignored paths.
"""
import csv
import gzip
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'scripts'))
from xlsx_readonly import read_workbook,colname,colnum
sys.path.insert(0,str(ROOT/'src'))
from validate_bloomberg_workbook import instrument_columns,cell,serial_date,last_row

PILOTS=['SPY','AAPL','MSFT']
VALIDATED_IDS={'SPY':'FRD-A2CDBBD48520','AAPL':'FRD-5D74998770F0','MSFT':'FRD-A28AB2B9DF55'}
WINDOWS=[5,10,15,30]
OUT=ROOT/'data/analytic'
DIAG=ROOT/'outputs/diagnostics'
START,END='2013-05-01','2025-12-31'


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def write_csv(path,rows):
    rows=list(rows)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def number(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None


def valid_bar(values):
    if len(values)!=5 or any(v is None or not math.isfinite(v) for v in values):return False
    o,h,l,c,v=values
    return min(o,h,l,c)>0 and v>=0 and l<=o<=h and l<=c<=h


def window_status(bars,close,length):
    required=[bars.get(m,[]) for m in range(close-length,close)]
    missing=sum(not x for x in required)
    duplicates=sum(max(0,len(x)-1) for x in required)
    invalid=sum(bool(x) and (len(x)!=1 or not x[0]['valid']) for x in required)
    return missing,duplicates,invalid


def next_open(bars):
    rows=bars.get(570,[])
    return rows[0] if len(rows)==1 and rows[0]['valid'] else None


def share_values(symbol,date,auction,daily):
    a=number(auction);d=number(daily)
    suspect=symbol=='SPY' and a==100 and date.startswith('2016-')
    raw=a/d if a is not None and d is not None and d>0 else None
    invalid=a is None or a<0 or d is None or d<=0 or raw is None or not 0<=raw<=1
    return {'auction_share_raw_diagnostic':raw,'spy_auction_100_suspect':suspect,
            'invalid_auction_or_daily_volume':invalid,
            'auction_share':raw if not invalid and not suspect else None,
            'auction_share_eligible_provisional':not invalid and not suspect}


def volume_tables(book):
    result={};counts={}
    for sheet,field in [('action_volume','OFFICIAL_CLOSE_AUCTION_VOLUME'),('daily_volume','PX_VOLUME')]:
        s=book[sheet];table={};count=Counter()
        for col in instrument_columns(s,2):
            security=cell(s,f'{colname(col)}1')['value'];symbol=security.split()[0]
            for row in range(2,last_row(s)+1):
                dc,vc=cell(s,f'{colname(col)}{row}'),cell(s,f'{colname(col+1)}{row}')
                if dc['value'] is None and vc['value'] is None:continue
                date=serial_date(dc['value'])
                if date is None:raise ValueError(f'Invalid volume date {sheet} {row}')
                key=(symbol,date)
                if key in table:raise ValueError(f'Duplicate/ambiguous volume key {sheet} {key}')
                table[key]={'raw_value':vc['value'],'value':number(vc['value']),'security':security,
                            'field':field,'source_cells':f'{colname(col)}{row}:{colname(col+1)}{row}'}
                count[symbol]+=1
        result[sheet]=table;counts[sheet]=dict(count)
    return result,counts


def action_table(book):
    s=book['corporate_actions'];events=defaultdict(list);counts={}
    for col in instrument_columns(s,7):
        security=cell(s,f'{colname(col)}1')['value'];symbol=security.split()[0];count=0
        for row in range(2,last_row(s)+1):
            v=[cell(s,f'{colname(col+j)}{row}')['value'] for j in range(7)]
            if not any(x is not None for x in v):continue
            date=serial_date(v[1])
            if date is None:raise ValueError('Action EX-Date invalid; review actual export schema')
            event={'symbol':symbol,'security':security,'candidate_ex_date':date,
                   'declared_date_raw':v[0],'ex_date_raw':v[1],'record_date_raw':v[2],
                   'pay_date_raw':v[3],'amount_or_terms_raw':v[4],'frequency_raw':v[5],
                   'type_raw':v[6],'source_cells':f'{colname(col)}{row}:{colname(col+6)}{row}',
                   'schema_basis':'user-transcribed DVD_HIST_ALL; actual headers absent'}
            if symbol in PILOTS:events[symbol,date].append(event)
            count+=1
        if count>=275:raise ValueError('DVD_HIST_ALL cap reached; verify completeness')
        counts[symbol]=count
    return events,counts


def event_columns(events,symbol,date,next_date):
    out={}
    for prefix,d in [('anchor',date),('next',next_date)]:
        ev=events.get((symbol,d),[]);types={x['type_raw'] for x in ev}
        out[prefix+'_action_found_in_export']=bool(ev)
        out[prefix+'_action_types']='|'.join(sorted(types))
        out[prefix+'_cash_distribution_flag']=bool(types&{'Income','Regular Cash'})
        out[prefix+'_split_flag']='Stock Split' in types
        out[prefix+'_other_action_flag']=bool(types-{'Income','Regular Cash','Stock Split'})
    out['action_calendar_complete_verified']=False
    return out


def scan(path,schedule):
    """Keep only last-30-minute bars and exact 09:30; SHA256 all original bytes."""
    before=path.stat();hasher=hashlib.sha256();days=defaultdict(lambda:defaultdict(list));counts=Counter()
    with path.open('rb') as f:
        for line_no,raw in enumerate(f,1):
            hasher.update(raw);counts['raw_lines']+=1
            if len(raw)<19:counts['short_lines']+=1;continue
            date=raw[:10].decode('ascii',errors='replace')
            if date not in schedule:continue
            try:minute=int(raw[11:13])*60+int(raw[14:16])
            except ValueError:counts['unparsed_time']+=1;continue
            close=schedule[date]['close_minute']
            if minute!=570 and not close-30<=minute<close:continue
            row=next(csv.reader([raw.decode('utf-8-sig').rstrip('\r\n')]))
            vals=[number(v) for v in row[1:]]
            exact_label=len(row[0])==19 and row[0][16:]==':00'
            valid=len(row)==6 and exact_label and valid_bar(vals)
            entry={'timestamp':row[0],'line_number':line_no,'valid':valid,
                   'open':row[1] if len(row)>1 else None,'close':row[4] if len(row)>4 else None}
            days[date][minute].append(entry);counts['selected_rows']+=1
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Provider file changed')
    return days,{'sha256':hasher.hexdigest(),'size_bytes':before.st_size,'mtime_ns':before.st_mtime_ns,**counts}


def main():
    OUT.mkdir(parents=True,exist_ok=True);DIAG.mkdir(parents=True,exist_ok=True)
    protected=[ROOT/'design_decisions.md']+list(p for p in (ROOT/'presentation').rglob('*') if p.is_file())+list(p for p in (ROOT/'data/raw_bloomberg').rglob('*') if p.is_file())
    hashes={p:sha(p) for p in protected}
    settings=ROOT/'.vscode/settings.json'
    configured=json.loads(settings.read_text(encoding='utf-8'))['terminal.integrated.env.windows']['RISKLAB_DATA_ROOT']
    root=Path(os.environ.get('RISKLAB_DATA_ROOT',configured))
    if not root.is_dir():raise FileNotFoundError(f'Configured RiskLab root inaccessible: {root}')
    os.environ['RISKLAB_DATA_ROOT']=str(root);sys.path.insert(0,str(root/'_catalog'))
    import data_paths as dp
    workbook=ROOT/'data/raw_bloomberg/Bloomberg_Project2_Master - Values.xlsx'
    book,_=read_workbook(workbook)
    if any(s['date1904'] for s in book.values()):raise ValueError('1904 date system: review source date parsing')
    if any(c['has_formula'] for s in book.values() for c in s['cells'].values()):raise ValueError('Static delivery unexpectedly contains formulas')
    volumes,counts=volume_tables(book);events,action_counts=action_table(book)
    symbols=set(counts['daily_volume'])
    with gzip.open(dp.catalog_root()/'intraday_inventory.csv.gz','rt',encoding='utf-8-sig',newline='') as f:
        inventory=list(csv.DictReader(f))
    availability=[];pilot_sources={}
    for symbol in sorted(symbols):
        # Use the already validated exact filename convention. Catalog symbol
        # metadata need not equal the issuer ticker (do not silently assume it).
        matches=[r for r in inventory if r['path'].endswith('/'+symbol+'_full_1min_adjsplitdiv.txt')
                 and r['path'].startswith(('intraday_data/stocks/','intraday_data/etfs/'))]
        for r in matches:
            p=dp.resolve(r['path']);exists=p.is_file()
            availability.append({'symbol':symbol,'risklab_id':r['id'],'relative_path':r['path'],
                                 'exists':exists,'size_bytes':p.stat().st_size if exists else '',
                                 'inventory_symbol_raw':r['symbol'],'inventory_frequency_raw':r['frequency'],
                                 'role':'included validated pilot' if symbol in PILOTS else 'discovered only; NOT expanded or content-validated'})
        if symbol in PILOTS:
            if len(matches)!=1:raise ValueError(f'Pilot mapping ambiguous/missing: {symbol}')
            if matches[0]['id']!=VALIDATED_IDS[symbol]:raise ValueError('Pilot stable ID changed; review mapping')
            pilot_sources[symbol]=matches[0]
        if not matches:availability.append({'symbol':symbol,'risklab_id':'','relative_path':'','exists':False,'size_bytes':'',
                                          'inventory_symbol_raw':'','inventory_frequency_raw':'',
                                          'role':'no matching documented variant in inventory'})
    write_csv(DIAG/'candidate_intraday_availability.csv',availability)
    print('Availability report saved before any panel expansion; building SPY/AAPL/MSFT only.',flush=True)
    calendar_path=ROOT/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv'
    with calendar_path.open(encoding='utf-8-sig') as f:calendar=list(csv.DictReader(f))
    anchors=[r for r in calendar if START<=r['session_date']<=END]
    schedule={r['session_date']:{**r,'close_minute':int(r['close_minute'])} for r in anchors}
    # Extend calendar from package rules for follow-up; never infer next session from raw rows.
    import exchange_calendars as xc
    follow=sorted({r['next_session'] for r in anchors}-schedule.keys())
    cal=xc.get_calendar('XNYS',start=START,end=max(follow))
    for d in follow:
        close=cal.schedule.loc[d,'close'].tz_convert('America/New_York')
        schedule[d]={'close_minute':close.hour*60+close.minute}
    panel=[];source_log=[]
    for symbol in PILOTS:
        meta=pilot_sources[symbol];path=dp.resolve(meta['path']);days,log=scan(path,schedule)
        source_log.append({'symbol':symbol,'risklab_id':meta['id'],'relative_path':meta['path'],**log})
        for session in anchors:
            date=session['session_date'];nxt=session['next_session'];close=int(session['close_minute'])
            bars=days.get(date,{});opening=next_open(days.get(nxt,{}));last=bars.get(close-1,[])
            lastbar=last[0] if last else {}
            row={'symbol':symbol,'date':date,'next_session':nxt,'scheduled_close_minute':close,
                 'early_close':str(session['early_close']).lower()=='true','intraday_risklab_id':meta['id'],
                 'intraday_relative_path':meta['path'],'intraday_variant':'adjsplitdiv-labelled; exact factors unresolved',
                 'preclose_proxy_timestamp':lastbar.get('timestamp'),'preclose_proxy_close':number(lastbar.get('close')),
                 'preclose_proxy_close_raw':lastbar.get('close'),
                 'preclose_source_line':lastbar.get('line_number'),
                 'next0930_raw_open':number(days.get(nxt,{}).get(570,[{}])[0].get('open')),
                 'next0930_open_raw_string':days.get(nxt,{}).get(570,[{}])[0].get('open'),
                 'next0930_open':number(opening['open']) if opening else None,
                 'next0930_timestamp':opening['timestamp'] if opening else None,
                 'next0930_source_line':opening['line_number'] if opening else None,
                 'next0930_valid':opening is not None,
                 'price_endpoint_status':'PROVISIONAL continuous-minute proxies; NOT official auction execution',
                 'common_price_volume_adjustments_verified':False,
                 'bloomberg_values_sha256':hashes[workbook]}
            for window in WINDOWS:
                missing,dupes,invalid=window_status(bars,close,window)
                startbar=bars.get(close-window,[{}])[0]
                start_price=number(startbar.get('open'));end_price=row['preclose_proxy_close']
                complete=not (missing or dupes or invalid)
                row.update({f'window_{window}m_start_raw_open':start_price,
                            f'window_{window}m_start_open_raw_string':startbar.get('open'),
                            f'window_{window}m_start_timestamp':startbar.get('timestamp'),
                            f'window_{window}m_start_source_line':startbar.get('line_number'),
                            f'window_{window}m_missing_labels':missing,f'window_{window}m_duplicate_rows':dupes,
                            f'window_{window}m_invalid_labels':invalid,f'window_{window}m_complete':complete,
                            f'provisional_preclose_return_{window}m':end_price/start_price-1 if complete else None})
            price_valid=row['window_10m_complete'] and row['next0930_valid']
            row['price_proxy_candidate_eligible']=price_valid
            row['provisional_preclose_to_next0930_return']=row['next0930_open']/row['preclose_proxy_close']-1 if price_valid else None
            a=volumes['action_volume'].get((symbol,date));d=volumes['daily_volume'].get((symbol,date))
            row.update({'auction_merge_matched':a is not None,'daily_merge_matched':d is not None,
                        'auction_security':a['security'] if a else {'SPY':'SPY UP EQUITY','AAPL':'AAPL UW EQUITY','MSFT':'MSFT UW EQUITY'}[symbol],
                        'daily_security':d['security'] if d else symbol+' US EQUITY',
                        'official_close_auction_volume_raw':a['raw_value'] if a else None,
                        'consolidated_daily_volume_raw':d['raw_value'] if d else None,
                        'auction_source_cells':a['source_cells'] if a else None,
                        'daily_source_cells':d['source_cells'] if d else None,
                        'auction_field':'OFFICIAL_CLOSE_AUCTION_VOLUME','daily_field':'PX_VOLUME',
                        'volume_scope':'primary-exchange closing auction / consolidated US daily shares',
                        'share_measurement_status':'PROVISIONAL; common volume adjustment and denominator inclusions unverified'})
            row.update(share_values(symbol,date,a['value'] if a else None,d['value'] if d else None))
            row['joint_candidate_eligible_provisional']=price_valid and row['auction_share_eligible_provisional']
            row.update(event_columns(events,symbol,date,nxt));panel.append(row)
        print(symbol,'source scan complete;',len(anchors),'candidate rows retained',flush=True)
    keys=[(r['symbol'],r['date']) for r in panel]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate panel key')
    if sum(r['spy_auction_100_suspect'] for r in panel)!=87:raise ValueError('SPY anomaly count changed; review')
    if not all(sha(p)==h for p,h in hashes.items()):raise ValueError('Protected raw/design/presentation file changed')
    for source in source_log:
        stat=dp.resolve(source['relative_path']).stat()
        if (stat.st_size,stat.st_mtime_ns)!=(source['size_bytes'],source['mtime_ns']):raise ValueError('Provider source changed')
    write_csv(OUT/'candidate_daily_panel.csv',panel)
    write_csv(DIAG/'candidate_panel_source_log.csv',source_log)
    action_rows=[e for es in events.values() for e in es]
    write_csv(OUT/'candidate_action_event_ledger.csv',action_rows)
    summary=[]
    for symbol in PILOTS:
        rr=[r for r in panel if r['symbol']==symbol]
        summary.append({'symbol':symbol,'calendar_skeleton':len(rr),'after_intraday_left_retention':len(rr),
                        'after_auction_left_retention':len(rr),'auction_matches':sum(r['auction_merge_matched'] for r in rr),
                        'after_daily_left_retention':len(rr),'daily_matches':sum(r['daily_merge_matched'] for r in rr),
                        'missing_or_invalid_10m_window':sum(not r['window_10m_complete'] for r in rr),
                        'missing_or_invalid_next0930':sum(not r['next0930_valid'] for r in rr),
                        'proxy_return_candidates':sum(r['price_proxy_candidate_eligible'] for r in rr),
                        'suspect_spy_100':sum(r['spy_auction_100_suspect'] for r in rr),
                        'joint_provisional_candidates':sum(r['joint_candidate_eligible_provisional'] for r in rr),
                        'invalid_or_missing_volume':sum(r['invalid_auction_or_daily_volume'] for r in rr),
                        'raw_share_outside_0_1':sum(r['auction_share_raw_diagnostic'] is not None and not 0<=r['auction_share_raw_diagnostic']<=1 for r in rr),
                        'anchor_action_days':sum(r['anchor_action_found_in_export'] for r in rr),
                        'next_action_days':sum(r['next_action_found_in_export'] for r in rr),
                        'anchor_split_days':sum(r['anchor_split_flag'] for r in rr),
                        'next_split_days':sum(r['next_split_flag'] for r in rr)})
    write_csv(DIAG/'candidate_panel_merge_qa.csv',summary)
    (DIAG/'candidate_panel_run.json').write_text(json.dumps({'completed_at':datetime.now().astimezone().isoformat(),
        'period':[START,END],'included_symbols':PILOTS,'rows':len(panel),'duplicate_keys':0,
        'proxy_candidates':sum(r['price_proxy_candidate_eligible'] for r in panel),
        'joint_provisional_candidates':sum(r['joint_candidate_eligible_provisional'] for r in panel),
        'action_counts':action_counts,'calendar_sha256':sha(calendar_path),
        'values_workbook_sha256':hashes[workbook],'protected_sources_unchanged':True,
        'extra_symbols_expanded':False,'regressions_run':False},indent=2),encoding='utf-8')
    report(summary,availability)
    from validate_candidate_panel_output import main as validate_saved
    validate_saved()
    print(json.dumps(summary,indent=2),flush=True)


def report(summary,availability):
    total=sum(r['calendar_skeleton'] for r in summary);usable=sum(r['joint_provisional_candidates'] for r in summary)
    additional=sorted({r['symbol'] for r in availability if r['exists'] and r['symbol'] not in PILOTS})
    text=f'''# First candidate daily panel — provisional proxy construction

Built {datetime.now().astimezone().isoformat()}. Licensed outputs are ignored:
`data/analytic/candidate_daily_panel.csv` and `candidate_action_event_ledger.csv`.
Period **{START}–{END}**, three fixed pilot symbols, {total:,} retained calendar
rows. There are **{usable:,} jointly eligible provisional price/share candidates**;
these are not a final scientific sample or certified official-close returns.
Every row is retained, including missing volumes and all 87 flagged SPY values.
No regression, predictive summary, significance comparison or universe expansion.

## Scope, discovery and provenance

Candidate period is the existing daily-volume request range, not a new frozen
sample decision. Original research horizon was 2010–2025. The calendar supplies
next sessions, including 2025-12-31→2026-01-02. Early closes follow actual schedule.
The source archive is broader, but no additional anchor year is added.

Additional catalog-matched minute files physically present: {', '.join(additional) or 'none'}.
They are **discovered only**, not content-validated or included. Exact RiskLab IDs,
relative paths and sizes are in `outputs/diagnostics/candidate_intraday_availability.csv`.
Discovery is written before panel building; expansion requires separate validation.
The inventory stores filename-like symbols and frequency `unknown` for these
paths; matching therefore uses exact validated filename patterns, with stable
pilot IDs checked against the previous validation. Raw catalog metadata is
preserved in the discovery CSV. Presence is not content validation for the 13
additional names.
These securities are not called a historical S&P universe. Rejected membership,
MM-04 and WMT UN/UW splices are not used.

Minute sources resolve through `<RISKLAB_DATA_ROOT>/_catalog/data_paths.py`.
Complete source bytes were SHA256-hashed during read-only scans; file size/mtime
checked after scanning. Raw Bloomberg, design and all presentation checksums
were checked unchanged. Spreadsheet formulas are not executed. Static Master
Values fields/keys are parsed directly, not taken from the older pilot workbook.
Source IDs, line numbers, raw price strings/levels, date labels, workbook SHA256
and Bloomberg cell references remain available for tracing.

## Construction and reversible eligibility

- Window L requires every unique valid label C−L through C−1. Prices are the
  first bar's open and last pre-close bar's close; all 5/10/15/30-minute windows
  and their counts are retained. A duplicate or invalid required row disqualifies
  that window; no filling, shortening, later opening-bar substitution or averaging.
- `provisional_preclose_return_Lm = preclose_proxy_close / window_Lm_start_raw_open − 1`.
  `provisional_preclose_to_next0930_return = next0930_open / preclose_proxy_close − 1`.
  Fractions, not percent units or log returns. Same RiskLab variant throughout;
  no Bloomberg nominal prices mixed into either return. These are continuous-
  minute proxies, not final official auction execution measures. Price levels
  remain separate so endpoint revisions need not repeat source ingestion.
- `auction_share_raw_diagnostic` preserves numerator/denominator arithmetic.
  `auction_share` is blank for missing/invalid/out-of-bounds inputs and the 87
  flagged SPY 2016 values. Raw volumes and diagnostic ratios are retained. This
  implements the user's explicit instruction that those SPY values are not valid
  auction-share observations; no provider value is modified or scientific cause
  inferred. Nonpositive denominator and negative numerator are invalid; zero
  auction numerator would be permitted as an observed zero, not a missing fill.
- `joint_candidate_eligible_provisional` requires valid primary-window/next-open
  proxies plus a valid, nonsuspect auction share. It does not certify adjustment
  compatibility. Other robustness-window flags are separate.
- Event flags indicate anchor-date and next-session EX-Date matches, cash
  distribution, split or other types, using supplied DVD_HIST_ALL order. No event
  is excluded by these flags. No matching event means absent from the export,
  not proof no action occurred. The ledger preserves raw dates/terms and types.

## Merge retention and quality counts

All joins are conceptual one-to-one **left matches on symbol/trading date** after
explicit venue/composite mapping. No row-number joins. Calendar rows remain after
each match; matched-source counts differ from retained-row counts.

| Symbol | Skeleton / after each left merge | Auction matches | Daily matches | Valid proxy pair | SPY suspect | Joint provisional candidates | Anchor / next action days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
'''
    for r in summary:text+=f"| {r['symbol']} | {r['calendar_skeleton']:,} | {r['auction_matches']:,} | {r['daily_matches']:,} | {r['proxy_return_candidates']:,} | {r['suspect_spy_100']} | {r['joint_provisional_candidates']:,} | {r['anchor_action_days']} / {r['next_action_days']} |\n"
    text+=f"\nTotals: {sum(r['missing_or_invalid_10m_window'] for r in summary):,} missing/invalid primary windows; {sum(r['missing_or_invalid_next0930'] for r in summary):,} missing/invalid next 09:30 endpoints; {total-sum(r['auction_matches'] for r in summary):,} unmatched auction observations; {total-sum(r['daily_matches'] for r in summary):,} unmatched daily observations; {sum(r['invalid_or_missing_volume'] for r in summary):,} missing/invalid volume pairs; {sum(r['raw_share_outside_0_1'] for r in summary):,} raw shares outside [0,1].\n"
    text+='''
Full missing/invalid-window/open, invalid-volume, split and out-of-range counts:
`outputs/diagnostics/candidate_panel_merge_qa.csv`. Duplicate panel keys are zero;
duplicate source volume keys halt the build. Missing initial auction coverage
remains unmatched, not filled. No rows are deleted from the saved candidate panel.

## Ready, provisional and blocked

- **Ready structurally:** primary window/next-session calendar extraction,
  preserved raw levels, source joins, anomaly/event flags and source lineage.
- **Provisional only:** RiskLab continuous-minute returns and primary-exchange
  auction shares over consolidated US daily volume. Local prices are labelled
  split-and-dividend adjusted, but exact factors across sessions remain unverified.
  Matching nominal Bloomberg prices was not assumed. Volume split basis,
  denominator auction inclusion and original export settings remain unconfirmed.
- **Not final:** official auction price endpoints, action-complete exclusion or
  adjustment policy and a cross-sectional universe. Supplied action history has
  a 275-record cap (not reached here), capital-change adjustment dependence on
  request dates and no returned column headers. Absence of a flag cannot certify
  complete event coverage. No action-crossing policy is silently selected.

The earlier audit's source limitations remain, including missing original caches.
These do **not** prevent the explicitly authorized provisional panel, but they
prevent presenting its coefficients as final official-close evidence. No such
coefficients were estimated.

## Reproduce and next step

Use configured workspace root (or RISKLAB_DATA_ROOT) and run:

```powershell
.venv/Scripts/python.exe -B src/test_candidate_panel.py
.venv/Scripts/python.exe -B src/build_candidate_panel.py
.venv/Scripts/python.exe -B src/validate_candidate_panel_output.py
```

Uses existing stdlib OOXML reader and installed exchange_calendars. No download.
The build invokes saved-output validation automatically; its separate command
can recheck keys, SPY preservation, eligibility and return algebra without
rescanning RiskLab or inspecting predictive relationships.
Outputs/run provenance: `outputs/diagnostics/candidate_panel_run.json`,
`candidate_panel_source_log.csv`, `candidate_panel_merge_qa.csv`.

Next, on new estimation authorization: specify the model/controls/inference and
action policy before seeing estimates, then test closing-pressure reversal and
its auction-share interaction on explicitly provisional proxies. Frozen windows
are preserved. Local data suffice to execute such a provisional test without a
default new Bloomberg request. Measurement documentation is required for final
interpretation. A WMT new-venue segment or validated historical membership is
conditional on expansion; official auction-price history is conditional on that
endpoint choice. Neither is required to retain the three-symbol proxy pilot.
With only three securities, security-clustered inference cannot rely on a
large-number-of-clusters approximation. Address common-day dependence and the
small pilot scope in the pre-estimation plan rather than selecting an inference
method from significance. No inference method or scientific specification is
frozen by this report.
'''
    (ROOT/'reports/candidate_panel_qa.md').write_text(text,encoding='utf-8')


if __name__=='__main__':main()
