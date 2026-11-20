"""Read-only catalog-resolved comparison; never shifts or repairs source dates."""
import csv,json,os,sys
from collections import Counter
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
root=Path(os.environ['RISKLAB_DATA_ROOT']);sys.path.insert(0,str(root/'_catalog'))
import data_paths as dp
from import_validate_bloomberg import ROOT,DIAG,number,write_csv,digest
path=dp.get(id='RL-ED340E2FF91E');before=digest(path)
with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
h=next(i for i,r in enumerate(rows) if r and r[0]=='Dates')
new=list(csv.DictReader((ROOT/'data/interim/bloomberg/closing_auction_volume.csv').open()))
out=[];summary={}
for symbol in ['AAPL','MSFT']:
    j=next(j for j,v in enumerate(rows[h-2]) if v.startswith(symbol+' '))
    security=rows[h-2][j]
    # Each security has opening-auction then closing-auction volume columns.
    if rows[h][j].strip()!='OFFICIAL_CLOSE_AUCTION_VOLUME':j+=1
    assert rows[h][j].strip()=='OFFICIAL_CLOSE_AUCTION_VOLUME',(symbol,j,rows[h][j])
    old=[]
    for row in rows[h+1:]:
        if not row or not row[0]:continue
        d=datetime.strptime(row[0],'%m/%d/%Y').date().isoformat()
        if j<len(row) and number(row[j]) is not None:old.append((d,number(row[j])))
    nn=[r for r in new if r['symbol']==symbol];bydate={r['date']:number(r['value']) for r in nn}
    byvalue={}
    for r in nn:byvalue.setdefault(number(r['value']),[]).append(r['date'])
    equal=0;unique=0;offsets=Counter()
    newindex={r['date']:i for i,r in enumerate(nn)}
    for i,(d,v) in enumerate(old):
        matches=byvalue.get(v,[]);same=bydate.get(d)==v;equal+=same
        if len(matches)==1:unique+=1;offsets[newindex[matches[0]]-i]+=1
        out.append({'symbol':symbol,'mm04_date':d,'mm04_value':str(v),'new_same_date_value':str(bydate.get(d,'')),'same_date_equal':same,'new_dates_with_equal_value':'|'.join(matches),'unique_value_match':len(matches)==1})
    summary[symbol]={'mm04_security':security,'mm04_field':rows[h][j],'dated_numeric_rows':len(old),'same_date_comparisons':sum(d in bydate for d,v in old),'same_date_equal':equal,'unique_value_matches':unique,'new_row_index_minus_mm04_row_index':dict(offsets),'first_mm04_date':old[0][0],'first_value_new_dates':byvalue.get(old[0][1],[]),'first_20_sequence_equal':all(v==number(nn[i]['value']) for i,(d,v) in enumerate(old[:20]))}
assert digest(path)==before
write_csv(DIAG/'mm04_comparison.csv',out)
(DIAG/'mm04_summary.json').write_text(json.dumps({'source_id':'RL-ED340E2FF91E','sha256':before,'comparisons':summary},indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
