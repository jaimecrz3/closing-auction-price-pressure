"""Read-only daily-panel schema, hash and candidate corporate-action audit.

No price ratios, returns, final panel, Bloomberg requests or reconciled event
calendar. Both physical datasets are independently scanned and hashed. Event
labels below describe observed nonzero cells until field semantics are verified.
"""
import csv
import hashlib
import json
import math
import os
import sys
from datetime import date
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'reports'/'corporate_action_diagnostics'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(Path(os.environ['RISKLAB_DATA_ROOT'])/'_catalog'))
import data_paths as dp
assert dp.data_root() not in OUT.parents
IDS=['RL-C3503DB43BF9','RL-4DC331F6CC26']
PILOTS=['SPY','AAPL','MSFT']
NUMERIC=['Open','High','Low','Close','Volume','Dividends','Stock Splits','Adj Close']
NA={'','nan','na','n/a','#n/a','#n/a n/a','null','none'}


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')


def csvsave(name,rows,fields=None):
    if not rows and fields is None:return
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields or list(rows[0]));writer.writeheader();writer.writerows(rows)


def number(raw):
    if raw.strip().lower() in NA:return None
    try:
        value=float(raw)
        return value if math.isfinite(value) else None
    except ValueError:return None


cases=list(csv.DictReader((BASE/'reports/adjustment_diagnostics/event_cases.csv').open(encoding='utf-8')))
focused=defaultdict(set)
for case in cases:
    for field in ['event_date','previous_session','next_session']:focused[case['symbol']].add(case[field])
calendar=list(csv.DictReader((BASE/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv').open(encoding='utf-8')))
expected={r['session_date'] for r in calendar}


def scan(ident):
    row=dp.find(id=ident)[0];path=dp.get(id=ident);before=path.stat();digest=hashlib.sha256()
    fieldstats={};tickers=Counter();widths=Counter();dates=Counter();rawdates={}
    seen_raw=defaultdict(int);seen_date=defaultdict(int);dup_raw=Counter();dup_date=Counter()
    pilot_dates={s:set() for s in PILOTS};pilot_missing={s:Counter() for s in PILOTS}
    candidate_actions=[];focus=[];bad_dates=[];rows=0;start=end=None
    event_values={'Dividends':Counter(),'Stock Splits':Counter()}
    with path.open('rb') as binary:
        def hashed_lines():
            for line in binary:
                digest.update(line)
                yield line.decode('utf-8-sig')
        reader=csv.reader(hashed_lines());fields=next(reader)
        fieldstats={f:{'blank':0,'na_token':0,'numeric':0,'integer_valued':0,'non_numeric':Counter(),'min':None,'max':None} for f in fields}
        for r in reader:
            rows+=1;widths[len(r)]+=1
            if len(r)!=len(fields):continue
            values=dict(zip(fields,r));ticker=values['Ticker'];rawdate=values['Date'];tickers[ticker]+=1
            # Validate the label as a date without timezone-shifting a midnight date field.
            day=rawdate[:10]
            try:
                date.fromisoformat(day)
            except ValueError:
                if len(bad_dates)<10:bad_dates.append({'record':rows+1,'raw_date':rawdate})
                continue
            if day not in dates:dates[day]=0
            dates[day]+=1
            if rawdate not in rawdates:rawdates[rawdate]=len(rawdates)
            # Dense date ids keep duplicate detection compact across the full universe.
            if day not in scan.day_ids:scan.day_ids[day]=len(scan.day_ids)
            dbit=1<<scan.day_ids[day];rbit=1<<rawdates[rawdate]
            if seen_date[ticker]&dbit:dup_date[(ticker,day)]+=1
            if seen_raw[ticker]&rbit:dup_raw[(ticker,rawdate)]+=1
            seen_date[ticker]|=dbit;seen_raw[ticker]|=rbit
            start=day if start is None else min(start,day);end=day if end is None else max(end,day)
            nums={}
            for field,raw in values.items():
                stat=fieldstats[field]
                if not raw.strip():stat['blank']+=1
                elif raw.strip().lower() in NA:stat['na_token']+=1
                elif field in NUMERIC:
                    n=number(raw);nums[field]=n
                    if n is None:stat['non_numeric'][raw]+=1
                    else:
                        stat['numeric']+=1;stat['integer_valued']+=n.is_integer()
                        stat['min']=n if stat['min'] is None else min(stat['min'],n)
                        stat['max']=n if stat['max'] is None else max(stat['max'],n)
                        if field in event_values and n!=0:event_values[field][raw]+=1
            if ticker in PILOTS:
                pilot_dates[ticker].add(day)
                for field in NUMERIC:
                    if number(values[field]) is None:pilot_missing[ticker][field]+=1
                if day in focused[ticker]:focus.append({'source_id':ident,'relative_path':row['path'],'source_csv_record':rows+1,**values})
                dividend=number(values['Dividends']);split=number(values['Stock Splits'])
                if (dividend is not None and dividend!=0) or (split is not None and split!=0):
                    candidate_actions.append({'source_id':ident,'symbol':ticker,'date':day,'raw_date':rawdate,'dividend_raw':values['Dividends'],'split_raw':values['Stock Splits'],'source_csv_record':rows+1,'interpretation':'nonzero source cell; not a certified cash amount/date convention without corroboration'})
            if rows%500000==0:print(ident,rows,'rows scanned',flush=True)
    after=path.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
    for stat in fieldstats.values():stat['non_numeric']=dict(stat['non_numeric'])
    coverage=[]
    for symbol in PILOTS:
        observed=pilot_dates[symbol]
        for year in range(2010,2026):
            exp={d for d in expected if d.startswith(str(year))};actual={d for d in observed if d.startswith(str(year))}
            coverage.append({'source_id':ident,'symbol':symbol,'year':year,'expected_sessions':len(exp),'observed_dates':len(actual),'expected_dates_present':len(exp&actual),'expected_dates_absent':len(exp-actual),'unexpected_dates':len(actual-exp),'first_observed_date':min(actual) if actual else '', 'last_observed_date':max(actual) if actual else ''})
    result={'id':ident,'relative_path':row['path'],'catalog_record':row,'size_bytes':before.st_size,'actual_sha256':digest.hexdigest(),'catalog_sha256_match':digest.hexdigest()==row['sha256'],'row_count_excluding_header':rows,'column_count':len(fields),'columns':fields,'row_width_counts':dict(widths),'minimum_date':start,'maximum_date':end,'unique_dates':len(dates),'unique_raw_date_strings':len(rawdates),'number_of_securities':len(tickers),'entity_field':'Ticker; string labels; no stable identifier or historical membership flag','security_row_counts':dict(tickers),'field_stats':fieldstats,'duplicate_exact_date_ticker_extra_rows':sum(dup_raw.values()),'distinct_duplicate_exact_keys':len(dup_raw),'duplicate_calendar_date_ticker_extra_rows':sum(dup_date.values()),'distinct_duplicate_calendar_keys':len(dup_date),'duplicate_key_examples':[{'ticker':k[0],'date':k[1],'extra_rows':v} for k,v in list(dup_date.items())[:10]],'malformed_date_examples':bad_dates,'nonzero_event_values':{k:dict(v) for k,v in event_values.items()},'pilot':{s:{'rows':tickers[s],'unique_dates':len(pilot_dates[s]),'min_date':min(pilot_dates[s]) if pilot_dates[s] else None,'max_date':max(pilot_dates[s]) if pilot_dates[s] else None,'missing_numeric_fields':dict(pilot_missing[s]),'expected_2010_2025_dates_absent':len(expected-pilot_dates[s]),'absent_date_examples':sorted(expected-pilot_dates[s])[:8],'absent_tail_dates':sorted(expected-pilot_dates[s])[-8:]} for s in PILOTS},'source_mtime_ns_before':before.st_mtime_ns,'source_mtime_ns_after':after.st_mtime_ns,'source_size_and_mtime_unchanged':True,'open_mode':'rb','date_semantics':'Observed midnight timestamp strings with offsets; date component used without conversion; event-date semantics require documentation','explicit_adjustment_factor_columns':[f for f in fields if 'factor' in f.lower()],'schema_interpretation':'CSV text; numerical parse diagnostics supplied, not a certified provider adjustment schema'}
    save(ident+'_schema.json',result)
    print(ident,'DONE',rows,'rows',len(tickers),'securities',start,end,flush=True)
    return result,candidate_actions,focus,coverage


scan.day_ids={}
results=[];actions=[];focus=[];coverage=[]
for ident in IDS:
    result,a,f,c=scan(ident);results.append(result);actions+=a;focus+=f;coverage+=c
csvsave('daily_candidate_action_rows.csv',actions)
csvsave('focused_raw_daily_rows.csv',focus)
csvsave('daily_pilot_calendar_coverage.csv',coverage)
save('physical_equivalence.json',{'first_id':IDS[0],'second_id':IDS[1],'equal_actual_sha256':results[0]['actual_sha256']==results[1]['actual_sha256'],'equal_size':results[0]['size_bytes']==results[1]['size_bytes'],'interpretation':'Byte-identical evidence is one underlying source, not independent corroboration' if results[0]['actual_sha256']==results[1]['actual_sha256'] else 'Different physical contents; no equivalence assumed'})
# Save only documentation relevant to provenance/definitions, never mutate provider docs.
save('documentation_review.json',{'bloomberg_readme':(dp.library_root()/'README.md').read_text(encoding='utf-8-sig'),'catalog_readme':(dp.catalog_root()/'README.md').read_text(encoding='utf-8-sig'),'conclusion':'Collection docs warn unknown adjustment, units, currency, timezone and point-in-time status remain unresolved. No field-level definitions for these panels were established.'})
print('Saved independent panel hashes, schema/coverage and candidate event diagnostics. No returns.',flush=True)
