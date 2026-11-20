r"""Offline, immutable OOXML import. No Excel automation, refresh, returns or models.

Run from repository root: .venv\Scripts\python.exe scripts/import_validate_bloomberg.py
Observation-level outputs intentionally live under ignored data/interim/.
"""
import csv, hashlib, json
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xlsx_readonly import read_workbook, colname

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/interim/bloomberg'
OUT.mkdir(parents=True, exist_ok=True)
DIAG = OUT / 'diagnostics'
DIAG.mkdir(exist_ok=True)

def write_csv(path, rows, fields=None):
    rows=list(rows)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def date(v):return (datetime(1899,12,30)+timedelta(days=float(v))).date().isoformat()
def number(v):
    try:
        n=Decimal(str(v));return n if n.is_finite() else None
    except InvalidOperation:return None

def main():
    files=[ROOT/'data/raw_bloomberg'/n for n in ['Bloomberg_Project2.xlsx','Bloomberg_Project2 - Values.xlsx']]
    hashes={p.name:digest(p) for p in files}
    books=[read_workbook(p) for p in files];formula,values=books[0][0],books[1][0]
    assert all(not sheet['date1904'] for book,_ in books for sheet in book.values()),'1904 date system requires explicit block-map update'
    audit=[];sources=[]
    for p,(sheets,meta) in zip(files,books):
        for name,s in sheets.items():
            audit.append({'file':p.name,'sheet':name,'range':s['declared_dimension'],'stored_cells':len(s['cells']),'formula_cells':sum(c['has_formula'] for c in s['cells'].values()),'error_cells':sum(c['type']=='e' for c in s['cells'].values())})
        sources.append({'source_id':'PROJECT2-BBG-'+('VALUES' if 'Values' in p.name else 'FORMULAS'),'relative_path':p.relative_to(ROOT).as_posix(),'sha256':hashes[p.name],'size_bytes':p.stat().st_size,'sheets_and_ranges':json.dumps({n:s['declared_dimension'] for n,s in sheets.items()}),'retrieved_at':'UNKNOWN','retrieval_settings':'Only literal saved formulas observed; defaults/DPDF/units not recorded','document_created':meta.get('created',''),'document_modified':meta.get('modified',''),'provenance':'User-delivered local workbook; document times are not retrieval times'})
    (DIAG/'workbook_audit.json').write_text(json.dumps({'sources':sources,'sheets':audit,'raw_cell_inventory':{p.name:b[0] for p,b in zip(files,books)}},indent=2),encoding='utf-8')
    write_csv(ROOT/'manifests/bloomberg_source_log.csv',sources)
    symbols=['SPY','AAPL','MSFT'];tables={};reconciliations=[]
    # Each map explicitly identifies static copies; no generic "all nonformula cells" import.
    def block(sheet, src_col, dst_col, src_row, dst_row, width, symbol):
        result=[];r=0
        while True:
            ref=f'{colname(dst_col)}{dst_row+r}';c=values[sheet]['cells'].get(ref)
            if not c or c['value'] is None:break
            row=[]
            for j in range(width):
                target=f'{colname(dst_col+j)}{dst_row+r}';cell=values[sheet]['cells'].get(target,{'value':None,'type':'missing','has_formula':False})
                assert not cell['has_formula'],(sheet,target)
                original=f'{colname(src_col+j)}{src_row+r}'
                for bookname,book in [('formula',formula),('values',values)]:
                    assert cell['value']==book[sheet]['cells'].get(original,{}).get('value'),(sheet,target,original,bookname)
                row.append(cell['value'])
            result.append((dst_row+r,row));r+=1
        reconciliations.append({'sheet':sheet,'symbol':symbol,'static_range':f'{colname(dst_col)}{dst_row}:{colname(dst_col+width-1)}{dst_row+r-1}','source_range':f'{colname(src_col)}{src_row}:{colname(src_col+width-1)}{src_row+r-1}','rows':r,'cached_comparison':'exact match in both workbooks'})
        return result
    for name,sheet,field in [('daily_volume','daily_volume','PX_VOLUME'),('closing_auction_volume','action_volume','OFFICIAL_CLOSE_AUCTION_VOLUME')]:
        rows=[]
        for i,symbol in enumerate(symbols):
            security=f'{symbol} '+('US' if name=='daily_volume' else ('UP' if symbol=='SPY' else 'UW'))+' Equity'
            for r,v in block(sheet,1+3*i,11+3*i,1,1,2,symbol):
                n=number(v[1]);rows.append({'symbol':symbol,'security':security,'field':field,'date':date(v[0]),'raw_date':v[0],'value':v[1],'value_status':'numeric' if n is not None else ('missing' if v[1] is None else 'error_or_text'),'units':'UNVERIFIED','adjustment':'UNVERIFIED','source_sheet':sheet,'source_cells':f'{colname(11+3*i)}{r}:{colname(12+3*i)}{r}','source_sha256':hashes[files[1].name]})
        tables[name]=rows;write_csv(OUT/f'{name}.csv',rows)
    prices=[]
    for i,symbol in enumerate(symbols):
        for r,v in block('price_pilot',1+5*i,1+5*i,1,15,4,symbol):
            for j,field in enumerate(['PX_OFFICIAL_CLOSE','PX_LAST','PX_OPEN'],1):
                prices.append({'symbol':symbol,'security':symbol+' US Equity','date':date(v[0]),'raw_date':v[0],'field':field,'value':v[j],'value_status':'numeric' if number(v[j]) is not None else 'missing_or_error','currency':'UNVERIFIED','adjustment':'UNVERIFIED','source_sheet':'price_pilot','source_cell':f'{colname(1+5*i+j)}{r}','source_sha256':hashes[files[1].name]})
    write_csv(OUT/'price_pilot.csv',prices)
    actions=[]
    for i,symbol in enumerate(symbols):
        for r,v in block('corporate_actions',1+8*i,1+8*i,2,70,7,symbol):
            record={'symbol':symbol,'security':symbol+' US Equity','field':'DVD_HIST_ALL','candidate_ex_date':date(v[1]),'date_role_status':'column 2 candidate ex-date; returned headers absent','raw_event_value':v[4],'frequency_raw':v[5],'event_type_raw':v[6],'value_basis':'UNVERIFIED','source_sheet':'corporate_actions','source_range':f'{colname(1+8*i)}{r}:{colname(7+8*i)}{r}','source_sha256':hashes[files[1].name]}
            for j in range(4):record[f'raw_date_column_{j+1}']=v[j];record[f'date_column_{j+1}']=date(v[j]) if v[j] is not None else ''
            actions.append(record)
    write_csv(OUT/'corporate_actions.csv',actions)
    write_csv(OUT/'dividends.csv',[r for r in actions if r['event_type_raw'] in ['Income','Regular Cash']])
    write_csv(OUT/'stock_splits.csv',[r for r in actions if r['event_type_raw']=='Stock Split'])
    membership=[]
    for r in range(1,504):
        a=values['SP500_membership']['cells'];assert not a[f'D{r}']['has_formula'] and not a[f'E{r}']['has_formula']
        assert a[f'A{r}']['value']==a[f'D{r}']['value'] and a[f'B{r}']['value']==a[f'E{r}']['value']
        assert a[f'A{r}']['value']==formula['SP500_membership']['cells'][f'A{r}']['value']
        assert a[f'B{r}']['value']==formula['SP500_membership']['cells'][f'B{r}']['value']
        membership.append({'security_raw':a[f'D{r}']['value'],'weight_raw':a[f'E{r}']['value'],'requested_asof':'2025-12-31','asof_status':'formula override only; not returned date','field':'INDX_MWEIGHT_HIST','source_sheet':'SP500_membership','source_range':f'D{r}:E{r}','source_sha256':hashes[files[1].name]})
    write_csv(OUT/'membership_reference.csv',membership)
    write_csv(DIAG/'block_reconciliation.csv',reconciliations)
    cal=list(csv.DictReader((ROOT/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv').open()))
    expected={r['session_date'] for r in cal};summary={};ratios=[]
    daily={(r['symbol'],r['date']):r for r in tables['daily_volume']}
    for name,rows in tables.items():
        summary[name]={}
        for s in symbols:
            rr=[r for r in rows if r['symbol']==s];dates=[r['date'] for r in rr];ns=[number(r['value']) for r in rr];counts=Counter(r['value'] for r in rr)
            within={d for d in expected if min(dates)<=d<=max(dates)}
            summary[name][s]={'rows':len(rr),'start':min(dates),'end':max(dates),'duplicate_dates':len(dates)-len(set(dates)),'nonnumeric_or_missing':sum(n is None for n in ns),'zero':sum(n==0 for n in ns),'negative':sum(n is not None and n<0 for n in ns),'expected_2010_2025':len(expected),'missing_inside_coverage':len(within-set(dates)),'outside_calendar':len(set(dates)-expected),'outside_field_coverage':len(expected-within),'most_common_count':counts.most_common(1)[0][1]}
            if name=='closing_auction_volume':
                hundred=[r['date'] for r in rr if number(r['value'])==100]
                summary[name][s]['equal_100']={'count':len(hundred),'start':min(hundred) if hundred else None,'end':max(hundred) if hundred else None,'by_year':dict(Counter(d[:4] for d in hundred))}
                if hundred:
                    summary[name][s]['equal_100']['intervening_non100_sessions']=sorted({d for d in expected if min(hundred)<=d<=max(hundred)}-set(hundred))
        if name=='closing_auction_volume':
            for r in rows:
                den=daily.get((r['symbol'],r['date']));n=number(r['value']);d=number(den['value']) if den else None
                ratio=n/d if n is not None and d is not None and d>0 else None
                ratios.append({'symbol':r['symbol'],'date':r['date'],'diagnostic_ratio':str(ratio) if ratio is not None else '', 'missing_denominator':den is None or d is None,'nonpositive_denominator':d is not None and d<=0,'negative_ratio':ratio is not None and ratio<0,'ratio_gt_one':ratio is not None and ratio>1,'suspect_100':r['symbol']=='SPY' and n==100,'purpose':'source consistency only; not analysis variable'})
    write_csv(DIAG/'volume_consistency.csv',ratios)
    summary['ratio_diagnostics']={s:{k:sum(bool(r[k]) for r in ratios if r['symbol']==s) for k in ['missing_denominator','nonpositive_denominator','negative_ratio','ratio_gt_one','suspect_100']} for s in symbols}
    pairs={(r['symbol'],r['date']):{} for r in prices}
    for r in prices:pairs[r['symbol'],r['date']][r['field']]=r['value']
    summary['price_pilot']={'observations':len(prices),'security_dates':len(pairs),'start':min(k[1] for k in pairs),'end':max(k[1] for k in pairs),'missing_or_error':sum(number(r['value']) is None for r in prices),'nonpositive':sum(number(r['value']) is not None and number(r['value'])<=0 for r in prices),'duplicate_keys':len(prices)-len({(r['symbol'],r['date'],r['field']) for r in prices}),'close_last_equal':sum(number(v['PX_OFFICIAL_CLOSE'])==number(v['PX_LAST']) for v in pairs.values()),'non_session_dates':len({k[1] for k in pairs}-expected),'early_close_dates':len({k[1] for k in pairs}&{r['session_date'] for r in cal if r['early_close'].lower()=='true'})}
    old=list(csv.DictReader((ROOT/'reports/corporate_action_diagnostics/source_candidate_events.csv').open()))
    summary['corporate_actions']={}
    for s in symbols:
        rr=[r for r in actions if r['symbol']==s];dates={r['candidate_ex_date'] for r in rr};local={r['date'] for r in old if r['symbol']==s and '2010-01-01'<=r['date']<='2025-12-31'}
        summary['corporate_actions'][s]={'rows':len(rr),'types':dict(Counter(r['event_type_raw'] for r in rr)),'start':min(dates),'end':max(dates),'duplicate_candidate_keys':len(rr)-len({(r['candidate_ex_date'],r['event_type_raw']) for r in rr}),'missing_event_values':sum(number(r['raw_event_value']) is None for r in rr),'nonpositive_event_values':sum(number(r['raw_event_value']) is not None and number(r['raw_event_value'])<=0 for r in rr),'local_candidate_dates':len(local),'shared_dates':len(local&dates),'local_only_dates':sorted(local-dates),'new_only_date_count':len(dates-local),'split_dates':[(r['candidate_ex_date'],r['raw_event_value']) for r in rr if r['event_type_raw']=='Stock Split']}
    summary['membership']={'rows':len(membership),'unique_identifiers':len({r['security_raw'] for r in membership}),'distinct_weights':len({r['weight_raw'] for r in membership}),'negative_weights':sum(number(r['weight_raw'])<0 for r in membership),'missing_weights':sum(number(r['weight_raw']) is None for r in membership),'returned_dates':0,'requested_asof':'2025-12-31'}
    (DIAG/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    assert all(digest(p)==hashes[p.name] for p in files),'Raw workbook changed'
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
