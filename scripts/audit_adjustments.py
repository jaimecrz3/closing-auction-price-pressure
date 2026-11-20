"""Read-only price-variant inventory and corporate-action row excerpts.

No returns or analysis panel. Missing variants are never synthesized. Event
dates are externally documented examples, not events inferred from price moves.
"""
import csv
import gzip
import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict
import exchange_calendars as xc

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'reports'/'adjustment_diagnostics'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(Path(os.environ['RISKLAB_DATA_ROOT'])/'_catalog'))
import data_paths as dp
assert dp.data_root() not in OUT.parents

EVENTS=[
 {'case_id':'AAPL_SPLIT_2014','symbol':'AAPL','event_date':'2014-06-09','event_type':'split','terms':'7-for-1','date_source':'https://investor.apple.com/dividend-history/default.aspx'},
 {'case_id':'AAPL_SPLIT_2020','symbol':'AAPL','event_date':'2020-08-31','event_type':'split','terms':'4-for-1','date_source':'https://investor.apple.com/dividend-history/default.aspx'},
 {'case_id':'AAPL_DIV_2020','symbol':'AAPL','event_date':'2020-11-06','event_type':'ex_dividend','terms':'USD 0.205 per then-current share; provider documented example','date_source':'https://firstratedata.com/about/price_adjustment'},
 {'case_id':'MSFT_SPLIT_2003','symbol':'MSFT','event_date':'2003-02-18','event_type':'split','terms':'2-for-1; outside 2010-2025 pilot; diagnostic only','date_source':'https://www.microsoft.com/en-us/investor/faq.aspx?CollectionId=null'},
 {'case_id':'MSFT_DIV_2024','symbol':'MSFT','event_date':'2024-02-14','event_type':'ex_dividend','terms':'USD 0.75 per share','date_source':'https://news.microsoft.com/source/2023/11/29/microsoft-announces-quarterly-dividend-21/'},
 {'case_id':'SPY_DIV_2020','symbol':'SPY','event_date':'2020-03-20','event_type':'ex_distribution','terms':'US ex-distribution date; cash amount not independently verified in this audit','date_source':'https://www.ssga.com/library-content/announcements/etfs/au/20200320-SPY-Distribution-Announcement.pdf'},
]


def writecsv(name,rows):
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2),encoding='utf-8')


inventory=[];scanned=0
with gzip.open(dp.catalog_root()/'intraday_inventory.csv.gz','rt',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        scanned+=1
        if r['asset_class'] in ['stocks','etfs'] and re.search(r'(?:^|/)(SPY|AAPL|MSFT)(?:[_.\-/]|$)',r['path'],re.I):
            inventory.append(r)
physical={}
for symbol,asset in [('SPY','etfs'),('AAPL','stocks'),('MSFT','stocks')]:
    physical[symbol]=[p.name for p in dp.frd(asset).iterdir() if re.match('^'+symbol+r'(?:[_.-]|$)',p.name,re.I)]
docs=[]
for file in ['stock.txt','etf.txt']:
    relative='intraday_data/_documentation/.archive/'+file
    lines=(dp.data_root()/relative).read_text(encoding='utf-8-sig').splitlines()
    docs.append({'relative_path':relative,'adjustment_lines':[{'line_number':i+1,'text':line} for i,line in enumerate(lines) if any(term in line.lower() for term in ['adjust','split','dividend'])]})
availability=[]
for symbol,asset in [('SPY','etfs'),('AAPL','stocks'),('MSFT','stocks')]:
    for variant in ['unadjusted','split_adjusted','split_and_dividend_adjusted_labeled']:
        matches=[r for r in inventory if Path(r['path']).name.startswith(symbol+'_') and ((variant=='split_and_dividend_adjusted_labeled' and '_adjsplitdiv.' in r['path']) or (variant=='split_adjusted' and re.search(r'_(adjsplit|splitadjusted)\.',r['path'],re.I)) or (variant=='unadjusted' and re.search(r'_full_1min\.',r['path'],re.I)))]
        availability.append({'symbol':symbol,'variant':variant,'status':'PRESENT_LABEL_DOCUMENTATION_SUPPORTED_FACTORS_UNVERIFIED' if matches else 'NOT_IDENTIFIED_LOCALLY','risklab_id':';'.join(r['id'] for r in matches),'relative_path':';'.join(r['path'] for r in matches),'evidence':'Inventory plus physical filenames; local notes define three adjustment types but do not contain file-specific factors or a suffix mapping.'})
save('variant_inventory.json',{'inventory_rows_scanned':scanned,'matching_records':inventory,'physical_filenames':physical,'intraday_root_entries':[p.name for p in dp.frd_root().iterdir()],'local_documentation':docs,'availability':availability})
writecsv('variant_availability.csv',availability)
cal=xc.get_calendar('XNYS',start='2003-01-01',end='2025-12-31')
selected_dates=defaultdict(set)
for e in EVENTS:
    d=e['event_date'];assert cal.is_session(d)
    e['previous_session']=cal.previous_session(d).date().isoformat()
    e['next_session']=cal.next_session(d).date().isoformat()
    for key in ['previous_session','event_date','next_session']:selected_dates[e['symbol']].add(e[key])
writecsv('event_cases.csv',EVENTS)
selected={};audits=[]
for r in inventory:
    symbol=Path(r['path']).name.split('_')[0]
    path=dp.resolve(r['path']);before=path.stat();days={}
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        for line,row in enumerate(csv.reader(f),1):
            if row[0][:10] not in selected_dates[symbol]:continue
            date=row[0][:10];clock=row[0][11:16]
            info=days.setdefault(date,{'first':None,'last':None,'rows':0,'selected':{}})
            record={'symbol':symbol,'variant':'split_and_dividend_adjusted_labeled','risklab_id':r['id'],'relative_path':r['path'],'source_line_number':line,'timestamp':row[0],**dict(zip(['open','high','low','close','volume'],row[1:]))}
            if info['first'] is None:info['first']=record
            info['last']=record;info['rows']+=1
            if clock in ['09:30','15:59','16:00','19:59']:info['selected'][clock]=record
    after=path.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
    selected[symbol]=days
    audits.append({'symbol':symbol,'relative_path':r['path'],'size_bytes':before.st_size,'mtime_ns_before':before.st_mtime_ns,'mtime_ns_after':after.st_mtime_ns,'unchanged':True,'open_mode':'r'})
    print(symbol,'corporate-action sessions extracted:',len(days),flush=True)
excerpts=[];assessment=[]
for e in EVENTS:
    for role in ['previous_session','event_date','next_session']:
        d=e[role];day=selected[e['symbol']].get(d)
        assert day is not None,(e['case_id'],d)
        records={r['timestamp']:r for r in [day['first'],*day['selected'].values(),day['last']]}
        for r in sorted(records.values(),key=lambda x:x['timestamp']):excerpts.append({'case_id':e['case_id'],'event_type':e['event_type'],'session_role':role,**r})
    assessment.append({'case_id':e['case_id'],'symbol':e['symbol'],'event_date':e['event_date'],'local_variants_present':1,'cross_variant_price_difference':'NOT_COMPUTABLE_MISSING_VARIANTS','cross_variant_volume_difference':'NOT_COMPUTABLE_MISSING_VARIANTS','cross_event_continuity':'Raw price levels saved; no return calculated; adjustment cannot be separated from actual price movement in one series','retrospective_adjustment':'Documented vendor policy; not independently proven for this snapshot','dividend_pre_post_effect':'Documented prior-date adjustment; local differential not identifiable without raw/split-only comparator','volume_adjustment':'Documented vendor policy; magnitude and formula not locally identifiable from one variant'})
writecsv('corporate_action_raw_excerpts.csv',excerpts)
writecsv('event_assessments.csv',assessment)
save('source_audits.json',audits)
save('audit_summary.json',{'events':len(EVENTS),'inventory_rows_scanned':scanned,'variants_found':len(inventory),'raw_excerpt_rows':len(excerpts),'source_stats_unchanged':True,'no_returns_computed':True,'cross_variant_comparison_possible':False})
print('Saved adjustment availability and event diagnostics; no returns or factors calculated.',flush=True)
