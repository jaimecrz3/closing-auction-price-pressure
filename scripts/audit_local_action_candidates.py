"""Read only local action-table candidates, retaining pilot securities only."""
import csv
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'reports/adjustment_diagnostics'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(Path(os.environ['RISKLAB_DATA_ROOT'])/'_catalog'))
import data_paths as dp

matches=[r for r in dp.catalog() if re.search(r'dividend|stock.?split|split.?factor|corporate.?action',' '.join(r.get(k,'') for k in ['path','title','description','fields']),re.I)]
(OUT/'corporate_action_catalog_candidates.json').write_text(json.dumps(matches,indent=2),encoding='utf-8')
records=[]
for ident in ['RL-41A9B2151B06','RL-05D1B15A9D42','RL-B1B6B9A28719','RL-F26C24A267B4']:
    source=dp.get(id=ident);before=source.stat();selected=[]
    with source.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames
        for row in reader:
            if re.match(r'^(AAPL|MSFT|SPY)(?:[ .]|$)',row.get('Ticker','').strip()):selected.append(row)
    after=source.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
    records.append({'id':ident,'relative_path':dp.find(id=ident)[0]['path'],'catalog':dp.find(id=ident)[0],'fields':fields,'pilot_rows':selected,'source_stat_unchanged':True,'open_mode':'r'})
(OUT/'local_action_candidates.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print('Saved four local action candidates, filtered to pilot symbols; no returns.')
