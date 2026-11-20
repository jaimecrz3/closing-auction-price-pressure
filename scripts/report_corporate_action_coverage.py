"""Offline source comparison and documentation; no returns or final event panel.

Reads saved diagnostics only. Nonzero source cells remain candidates; comparisons
preserve missing amounts, type ambiguity, provenance and date disagreements.
"""
import csv
import hashlib
import itertools
import json
from collections import Counter,defaultdict
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'reports/corporate_action_diagnostics'
OLD=BASE/'reports/adjustment_diagnostics'
IDS=['RL-C3503DB43BF9','RL-4DC331F6CC26']
CANONICAL='RL-4DC331F6CC26'
LABELS={IDS[0]:'CE-104',IDS[1]:'sp500_histories','RL-41A9B2151B06':'CE-08','RL-B1B6B9A28719':'CE-05','RL-F26C24A267B4':'CE-06','RL-05D1B15A9D42':'CE-102 (change-only)'}
PILOTS=['SPY','AAPL','MSFT']


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def readcsv(path):return list(csv.DictReader(path.open(encoding='utf-8',newline='')))


def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2),encoding='utf-8')


def csvsave(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields or list(rows[0]));writer.writeheader();writer.writerows(rows)


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(v).replace('|','/') for v in row)+' |' for row in rows])


def day(raw):
    return datetime.strptime(raw,'%m/%d/%Y').date().isoformat() if '/' in raw else raw[:10]


def nonzero(raw):
    try:
        value=Decimal(raw)
        return value.is_finite() and value!=0
    except Exception:return False


panels=[load(OUT/(ident+'_schema.json')) for ident in IDS]
equivalence=load(OUT/'physical_equivalence.json')
assert equivalence['equal_actual_sha256']
old=load(OLD/'local_action_candidates.json')
raw=readcsv(OUT/'daily_candidate_action_rows.csv')
focused=readcsv(OUT/'focused_raw_daily_rows.csv')
cases=readcsv(OLD/'event_cases.csv')
records=[]
for r in raw:
    for kind,column,amount in [('split','split_raw','split_raw'),('distribution','dividend_raw','dividend_raw')]:
        if nonzero(r[column]):records.append({'source_id':r['source_id'],'symbol':r['symbol'],'date':r['date'],'event_kind':kind,'raw_value':r[amount],'value_semantics':'nonzero source cell; field basis not documented','raw_date':r['raw_date'],'source_role':'daily panel; physical duplicate pair'})
aliases={s:s for s in PILOTS}|{s+' US':s for s in PILOTS}
for source in old:
    for r in source['pilot_rows']:
        symbol=aliases[r['Ticker']];d=day(r['Date'])
        if source['id']=='RL-41A9B2151B06':kind,value,role='split',r['Stock Splits'],'split-event table; complete coverage not certified'
        elif source['id']=='RL-05D1B15A9D42':kind,value,role='distribution',r['Dividend'],'dividend-change table; not all distributions'
        else:kind,value,role='distribution','','Dividend Ex-Date description; amounts absent; CE-05/06 share event dates'
        records.append({'source_id':source['id'],'symbol':symbol,'date':d,'event_kind':kind,'raw_value':value,'value_semantics':'ratio/cash basis requires documentation; blank means not supplied','raw_date':r['Date'],'source_role':role})
inperiod=[r for r in records if '2010-01-01'<=r['date']<='2025-12-31']
counts=[]
for source in LABELS:
    for symbol in PILOTS:
        rs=[r for r in inperiod if r['source_id']==source and r['symbol']==symbol]
        splits={r['date'] for r in rs if r['event_kind']=='split'};dist={r['date'] for r in rs if r['event_kind']=='distribution'}
        counts.append({'source_id':source,'source_label':LABELS[source],'symbol':symbol,'split_dates':len(splits),'distribution_or_change_dates':len(dist),'distribution_dates_missing_amount':len({r['date'] for r in rs if r['event_kind']=='distribution' and r['raw_value']==''}),'first_recorded_event_date':min((r['date'] for r in rs),default=''),'last_recorded_event_date':max((r['date'] for r in rs),default=''),'special_dividend_classification':'NOT_AVAILABLE; no explicit type field established','independence_note':'Daily panels byte-identical; CE-05/06 date copies are not independent corroboration'})
csvsave('event_counts_2010_2025.csv',counts)
# Per-source evidence rows only; do not produce a reconciled/final calendar.
csvsave('source_candidate_events.csv',records)
sets=defaultdict(set)
for r in inperiod:sets[(r['source_id'],r['symbol'],r['event_kind'])].add(r['date'])
family={IDS[0]:'daily byte copies',IDS[1]:'daily byte copies','RL-B1B6B9A28719':'CE-05/06 ex-date copies','RL-F26C24A267B4':'CE-05/06 ex-date copies','RL-41A9B2151B06':'CE-08 split table','RL-05D1B15A9D42':'CE-102 change-only'}
evidence=defaultdict(list)
for r in inperiod:evidence[(r['symbol'],r['event_kind'],r['date'])].append(r)
family_only=[]
for (symbol,kind,d),rs in sorted(evidence.items()):
    families={family[r['source_id']] for r in rs}
    if len(families)==1:family_only.append({'symbol':symbol,'event_kind':kind,'date':d,'only_source_family':next(iter(families)),'source_ids':';'.join(sorted({r['source_id'] for r in rs})),'status':'candidate appears in one compared family only; coverage and change-only roles prevent automatic error classification'})
csvsave('source_family_only_events.csv',family_only)
family_counts=Counter((r['symbol'],r['event_kind'],r['only_source_family']) for r in family_only)
pairwise=[];unmatched=[];nearby=[];amount_differences=[]
for a,b in itertools.combinations([CANONICAL,*[x['id'] for x in old]],2):
    for symbol in PILOTS:
        for kind in ['split','distribution']:
            aa=sets[(a,symbol,kind)];bb=sets[(b,symbol,kind)]
            if not aa and not bb:continue
            # Event envelopes limit the comparison; they do NOT certify coverage.
            lo=max(min(aa) if aa else '9999',min(bb) if bb else '9999');hi=min(max(aa) if aa else '',max(bb) if bb else '')
            av={d for d in aa if lo<=d<=hi};bv={d for d in bb if lo<=d<=hi}
            pairwise.append({'source_a':a,'source_b':b,'symbol':symbol,'event_kind':kind,'same_date_matches_full_period':len(aa&bb),'only_a_full_period':len(aa-bb),'only_b_full_period':len(bb-aa),'overlapping_observed_event_envelope_start':lo if lo<=hi else '','overlapping_observed_event_envelope_end':hi if lo<=hi else '','only_a_in_envelope':len(av-bv),'only_b_in_envelope':len(bv-av),'scope_note':'Envelope is not certified coverage; CE-102 is change-only; no conflict automatically reconciled'})
            for source,other,exclusive,otherdates in [(a,b,aa-bb,bb),(b,a,bb-aa,aa)]:
                for d in sorted(exclusive):unmatched.append({'source_id':source,'comparator_id':other,'symbol':symbol,'event_kind':kind,'date':d,'inside_observed_event_overlap':lo<=d<=hi,'interpretation':'source-only relative to comparator; may reflect coverage/role difference, not necessarily incorrect date'})
            for da in av-bv:
                for db in bv-av:
                    distance=abs((date.fromisoformat(da)-date.fromisoformat(db)).days)
                    if 0<distance<=7:nearby.append({'source_a':a,'source_b':b,'symbol':symbol,'event_kind':kind,'date_a':da,'date_b':db,'calendar_day_distance':distance,'status':'POTENTIAL_DATE_DISAGREEMENT; no event matching or shifting applied'})
            for d in aa&bb:
                ra=[r for r in inperiod if (r['source_id'],r['symbol'],r['event_kind'],r['date'])==(a,symbol,kind,d) and r['raw_value']]
                rb=[r for r in inperiod if (r['source_id'],r['symbol'],r['event_kind'],r['date'])==(b,symbol,kind,d) and r['raw_value']]
                for x,y in itertools.product(ra,rb):
                    if Decimal(x['raw_value'])!=Decimal(y['raw_value']):amount_differences.append({'source_a':a,'source_b':b,'symbol':symbol,'event_kind':kind,'date':d,'raw_value_a':x['raw_value'],'raw_value_b':y['raw_value'],'status':'UNRESOLVED_EXACT_NUMERIC_DIFFERENCE; could be precision/scale; no tolerance reconciliation applied'})
csvsave('pairwise_event_comparison.csv',pairwise)
csvsave('unmatched_source_events.csv',unmatched)
csvsave('potential_date_disagreements.csv',nearby,['source_a','source_b','symbol','event_kind','date_a','date_b','calendar_day_distance','status'])
csvsave('raw_value_disagreements.csv',amount_differences,['source_a','source_b','symbol','event_kind','date','raw_value_a','raw_value_b','status'])
selected=[]
for c in cases:
    daily=[r for r in focused if r['source_id']==CANONICAL and r['Ticker']==c['symbol'] and day(r['Date'])==c['event_date']]
    selected.append({'case_id':c['case_id'],'symbol':c['symbol'],'event_date':c['event_date'],'canonical_daily_row_present':bool(daily),'daily_dividend_raw':daily[0]['Dividends'] if daily else 'NO SECURITY ROW','daily_split_raw':daily[0]['Stock Splits'] if daily else 'NO SECURITY ROW','daily_adj_close_raw':daily[0]['Adj Close'] if daily else 'NO SECURITY ROW','CE08_same_date':any(r['source_id']=='RL-41A9B2151B06' and r['symbol']==c['symbol'] and r['date']==c['event_date'] for r in records),'CE05_same_date':any(r['source_id']=='RL-B1B6B9A28719' and r['symbol']==c['symbol'] and r['date']==c['event_date'] for r in records),'CE06_same_date':any(r['source_id']=='RL-F26C24A267B4' and r['symbol']==c['symbol'] and r['date']==c['event_date'] for r in records),'CE102_same_date':any(r['source_id']=='RL-05D1B15A9D42' and r['symbol']==c['symbol'] and r['date']==c['event_date'] for r in records),'known_event_terms':c['terms']})
csvsave('six_event_representation.csv',selected)
schema=panels[1]
save('coverage_assessment.json',{'period':'2010-2025 plus next-session boundary as needed','daily_panels_byte_identical':True,'daily_panels_independent_sources':1,'split_calendar_complete_enough_for_all_three_full_period':False,'distribution_calendar_complete_enough_for_all_three_full_period':False,'adjustment_decision':'UNRESOLVED','policy_A':'insufficient standalone dividend protection','policy_B':'measurement rationale defensible; full local coverage not established; do not implement/freeze','policy_C':'unsupported file-specific assumptions remain','special_dividends_separately_identifiable':False,'missing_amounts_alone_block_exclusion_policy':False,'reasons':['SPY absent from both daily panels','AAPL/MSFT daily rows stop 2025-09-26; 66 expected 2025 dates absent','CE-05/06 only provide pilot dates from late 2019 to September 2025','CE-102 records changes, not all distributions','No documented exhaustive cash-event/special-event coverage or file-specific adjustment factors','Adj Close entirely blank; do not derive or assume adjustment factors'],'potential_nearby_date_disagreements':len(nearby),'raw_value_disagreements':len(amount_differences),'no_returns_or_reconciled_final_calendar':True})

report=['# Corporate-action coverage checkpoint','',
        'Read-only inspection recorded 2026-10-27. Only source structure and corporate-action evidence were assessed; no research returns, overnight interval panel, regressions or predictive relationships were created. No Bloomberg access occurred.','',
        '## Conclusion','',
        '**Both daily files are useful as partial AAPL/MSFT event evidence, but not as two independent sources or a complete SPY/AAPL/MSFT 2010–2025 action calendar. Keep adjustment UNRESOLVED.** Do not implement the proposed split/distribution exclusions or silently truncate the research period to fit the source cutoff. Six already-frozen choices and endpoint/universe decisions are unchanged.','',
        '## Independent physical and schema checks','',
        table(['RiskLab ID / source','Relative path','Rows × columns','Dates','Securities','Duplicate Date/Ticker rows'],[[p['id']+' / '+LABELS[p['id']],'`'+p['relative_path']+'`',f"{p['row_count_excluding_header']:,} × {p['column_count']}",p['minimum_date']+' to '+p['maximum_date'],p['number_of_securities'],p['duplicate_exact_date_ticker_extra_rows']] for p in panels]),'',
        'Each file is 350,487,184 bytes. Independent full-file SHA256 scans produced the same digest:', '',
        '`'+schema['actual_sha256']+'`','',
        'Both match the catalog checksum. The files are therefore byte-identical, not merely similar-schema tables. Catalog canonical/golden source is `RL-4DC331F6CC26` (`sp500_histories.csv`). Treat CE-104 as a physical duplicate; combining them would duplicate every key. Each individual table has zero duplicate exact timestamp/Ticker keys and zero duplicate calendar-date/Ticker keys. No conflicting duplicate rows were found within either table.','',
        'Exact columns: `'+', '.join(schema['columns'])+'`. `Date` contains midnight timestamp strings with UTC offsets (for example `2000-01-03 00:00:00-05:00`); date labels were compared without timezone-shifting. `Ticker` contains 499 string security labels, not stable IDs or membership-effective records. There are '+str(schema['unique_dates'])+' unique date labels. Numeric parse types are floating-point values where populated; `Adj Close` is wholly empty and has no usable numeric observations. No explicit adjustment-factor column exists.','',
        table(['Field','Finite numeric rows (each file)','Blank / NA-token rows','Interpretation limits'],[[f,schema['field_stats'][f]['numeric'],str(schema['field_stats'][f]['blank'])+' / '+str(schema['field_stats'][f]['na_token']),('Entirely blank; no scale bridge' if f=='Adj Close' else 'Observed numeric; units/adjustment not certified')] for f in ['Open','Close','Adj Close','Dividends','Stock Splits']]),'',
        'Full schema, all-field missingness, nonnumeric tokens, entity counts and duplicate-key diagnostics are in the two `*_schema.json` files under [corporate_action_diagnostics](corporate_action_diagnostics/). These are observational parse types, not evidence of the original software/export defaults.','',
        '## Field definitions and price-scale limits','',
        'The inspected catalog records say `units`, `currency`, `adjustment`, `timezone` and `point_in_time` are unknown; provider/source is assigned through migration metadata. Nearby provider/catalog READMEs explicitly say unknown details remain unresolved. No file-specific field dictionary or original extraction/adjustment settings were established. Do not infer a vendor/library, adjustment methodology or ex-date meaning solely from these familiar column names or numerical patterns.','',
        '- `Dividends`: selected AAPL 2020-11-06 and MSFT 2024-02-14 cells match the independently documented cash amounts shown below. That supports cash-per-share interpretation for these examples, rather than a binary indicator or a price-adjustment factor. It does not establish historical nominal versus split-adjusted amounts, currency, gross/net basis, or exhaustive ordinary/special coverage for every row.',
        '- `Stock Splits`: the selected 7, 4 and 2 values match documented 7-for-1, 4-for-1 and 2-for-1 events and CE-08. Those examples contain ratios rather than just a flag. Reverse-split ratio orientation and complete no-action coverage are not certified by field documentation.',
        '- Selected dates match the known ex-date/effective-trading dates. This is corroboration for those examples, not a general date convention established by documentation. CE-06’s 10:00 values are not treated as dissemination/ex-date intraday cutoffs.',
        '- `Open` and `Close` supply price levels but are not documented as nominal versus adjusted or official auction prices. `Adj Close` is entirely blank, so it supplies no price-scale information or adjustment factor. No Close/Adj Close ratio or research return was calculated.','',
        '## Six selected event checks','',
        table(['Case / event date','Daily row','Daily Dividends','Daily Stock Splits','CE-08','CE-05 / CE-06','CE-102'],[[r['case_id']+' / '+r['event_date'],r['canonical_daily_row_present'],r['daily_dividend_raw'],r['daily_split_raw'],r['CE08_same_date'],str(r['CE05_same_date'])+' / '+str(r['CE06_same_date']),r['CE102_same_date']] for r in selected]),'',
        'The five AAPL/MSFT events have source-date agreement and the split/dividend values expected for the already verified examples. SPY 2020-03-20 has no daily security row, so these files add neither a SPY distribution amount nor an independent SPY price scale. CE-05/06 supply its ex-date; CE-102 supplies no SPY row. CE-102 absence on an unchanged-dividend date is not itself a conflict because it is a change-only table. The MSFT 2003 case remains diagnostic and is outside the 2010–2025 event counts. Raw daily excerpts retain all original fields and source record numbers in [focused_raw_daily_rows.csv](corporate_action_diagnostics/focused_raw_daily_rows.csv).','',
        '## 2010–2025 event counts and comparisons','',
        'Counts below are distinct dates with nonzero candidate event cells, described ex-dates, or change-only records as appropriate. Zero count is not certified absence of corporate actions. Special dividends cannot be classified separately: no explicit ordinary/special code was established.','',
        table(['Source','Security','Split dates','Distribution/change dates','Distribution dates with no amount'],[[r['source_label'],r['symbol'],r['split_dates'],r['distribution_or_change_dates'],r['distribution_dates_missing_amount']] for r in counts]),'',
        'Daily duplicates are shown separately to satisfy per-source reporting but must not be summed as independent coverage. CE-05 and CE-06 share the same event-date records and are also not independent validation. CE-102 is explicitly change-only. Cross-file agreement does not certify the sources are independently produced.','',
        'Full comparisons retain shared dates, source-only dates, limited common observed-event envelopes, nearby unmatched dates and exact numeric differences. **An observed event-date envelope is not certified source coverage.** Events outside another source’s dates, and events absent from CE-102, are not automatically conflicting dates. No dates or amounts were shifted, filled, averaged or reconciled.','',
        'Events appearing only in one compared source family (byte copies/date copies grouped; this does not certify independence of the other families):','',
        table(['Security','Event kind','Only compared family','Dates'],[[symbol,kind,fam,n] for (symbol,kind,fam),n in sorted(family_counts.items())]),'',
        'Exact dates are preserved in [source_family_only_events.csv](corporate_action_diagnostics/source_family_only_events.csv). These are evidence-comparison results, not a reconciled or validated event calendar.','',
        f'- Potential unmatched dates within seven calendar days of one another inside shared observed-event envelopes: **{len(nearby)}**. See [potential_date_disagreements.csv](corporate_action_diagnostics/potential_date_disagreements.csv); none is automatically declared the same event.',
        f'- Exact differing nonblank values on common dates: **{len(amount_differences)}**. See [raw_value_disagreements.csv](corporate_action_diagnostics/raw_value_disagreements.csv). Precision or share-basis differences are flagged, not silently tolerated.',
        '- Shared/source-only date counts: [pairwise_event_comparison.csv](corporate_action_diagnostics/pairwise_event_comparison.csv). Exact unmatched dates: [unmatched_source_events.csv](corporate_action_diagnostics/unmatched_source_events.csv). Per-source candidates remain separate in [source_candidate_events.csv](corporate_action_diagnostics/source_candidate_events.csv); this is not a final reconciled action calendar.','',
        '### Coverage boundaries that prevent a complete policy','',
        '- AAPL/MSFT each have 6,473 daily observations from 2000-01-03 through 2025-09-26. Within the target period, 3,958 of 4,024 expected sessions are represented, with all 66 absent sessions at 2025-09-29–2025-12-31. Their event cells are nonmissing on represented dates, but documentation must still establish what zero/nonzero exhaustively covers.',
        '- SPY has **zero daily rows** in both files. CE-08 and CE-102 also have no SPY event rows; absence in event-only tables is not an explicit no-split guarantee. CE-05/06 supply only 24 SPY distribution dates from 2019-12-20 to 2025-09-19, with no amounts. Earlier 2010–2019 SPY dates and the late-2025 tail are not established by these sources.',
        '- AAPL/MSFT calendar descriptions in CE-05/06 begin in late 2019/2020 and stop by September 2025; the change-only CE-102 cannot fill unchanged quarterly dates. These sources do not close the daily panels’ late-2025 gap. The next-session boundary after 2025-12-31 is 2026-01-02 and must also be handled by any eventual event calendar.',
        '- No complete ordinary-plus-special cash-event coverage or historical amount basis is documented. Missing amounts and unclassified special types matter for valuation/adjustment checks, but **amounts are not required just to exclude all documented cash-event crossings**. Policy B is blocked here by incomplete/uncertified event-date coverage, not by cash amounts alone.','',
        '## Pre-declared policy feasibility','',
        table(['Policy','Assessment independent of outcomes'],[
            ['A: exclude split-crossing intervals only','Insufficient alone for pure price pressure: cash-distribution ex-date effects remain. Existing combined-adjusted data also require verified behavior; excluding splits alone does not establish it.'],
            ['B: exclude split and cash-distribution crossings','Defensible measurement approach if an exhaustive, documented date calendar exists. Current local evidence is incomplete for SPY and late 2025 and lacks full event semantics. Do not implement or freeze it yet. Cash amounts are not needed solely for exclusions.'],
            ['C: combined-adjusted minute prices on all intervals','Requires verified retrospective price/volume behavior, within-session factor constancy, dividend reference-price convention, action coverage, rounding/vintage stability and compatibility with chosen endpoints. No local factor bridge is supplied by these daily panels; not justified by current evidence.']]),'',
        'No policy is selected using sample size, price behavior or model results. The proposed combination—existing within-session adjusted prices plus split/cash-crossing exclusions and no nominal/adjusted mixing—**cannot yet be frozen** because a complete reproducible action calendar is not established. Exact close/open endpoints and final universe are unchanged.','',
        '## Remaining corporate-action verification; minimize new data','',
        '1. Establish complete split/reverse-split dates or explicit no-action coverage for the three securities across 2010–2025 and the required next-session boundary. Reuse the corroborated CE-08 AAPL dates/ratios; do not re-download them just to obtain known dates.',
        '2. Fill/verify SPY cash-distribution dates before 2019-12-20 and after 2025-09-19, and AAPL/MSFT coverage after 2025-09-26 through the needed boundary. Confirm the source covers special as well as ordinary cash events, with actual ex-dates rather than announcement/payment dates.',
        '3. Verify existing `Dividends`/`Stock Splits` definitions, date convention, ratio orientation, amount/share basis and source provenance. If amounts are needed for adjustment validation, establish cash currency, ordinary/special type and historical split basis. These are separate from the minimum date-only exclusion requirement.',
        '4. Resolve flagged differences and file-specific minute adjustment/price-scale compatibility. A blanket new Bloomberg action download is not justified; first seek definitions/authoritative coverage and then request only verified gaps if separately authorized. No Bloomberg access is authorized or performed in this step.','',
        '## Reproduction and checks','',
        '`scripts/audit_daily_action_panels.py` streams/hashes the two provider files read-only and saves structural/event diagnostics. `scripts/report_corporate_action_coverage.py` compares saved source evidence and updates documentation without provider access. Source size/mtime stayed unchanged for both panels. Frozen-design/endpoint/universe rows are checked for preservation when updating the register. No returns, final panel, regressions or predictive analysis were created.','']
(BASE/'reports/corporate_action_coverage.md').write_text('\n'.join(report),encoding='utf-8')

# Preserve the six frozen rules and unresolved endpoint/universe decisions exactly.
design_path=BASE/'design_decisions.md';text=design_path.read_text(encoding='utf-8')
protected=lambda s:[line for line in s.splitlines() if '| FROZEN |' in line or line.startswith(('| Exact close price |','| Exact next-open price |','| Final cross-sectional universe |'))]
before=protected(text)
newrow='| Adjustment convention | UNRESOLVED | Local daily duplicates add partial AAPL/MSFT action evidence but no SPY rows or usable Adj Close/factors. The 2010–2025 event calendar is incomplete, including late 2025. Do not freeze cash/split-crossing exclusions, reconstruct variants or mix nominal and adjusted endpoints. See reports/corporate_action_coverage.md. |'
text='\n'.join(newrow if line.startswith('| Adjustment convention |') else line for line in text.splitlines())+'\n'
text=text.replace('Review already-owned\nCE-104/sp500_histories event columns and provenance before requesting overlapping\ncorporate-action history.','The CE-104/sp500_histories review is complete; see the coverage checkpoint below.\nResolve remaining source definitions and event-date gaps before requesting\noverlapping corporate-action history.')
marker='## Corporate-action coverage checkpoint'
if marker in text:text=text.split(marker)[0].rstrip()+'\n'
text+='''
## Corporate-action coverage checkpoint — 2026-10-27

[Full coverage assessment](reports/corporate_action_coverage.md): CE-104 and
sp500_histories are independently hash-confirmed byte-identical. They add useful
AAPL/MSFT dates and candidate cash/split values, but contain no SPY and stop at
2025-09-26. Adj Close is entirely blank; no explicit factor is supplied. Existing
date/change tables do not establish the missing SPY history or late-2025 coverage.

Adjustment remains UNRESOLVED. Policy A (split-only exclusions) leaves cash-event
effects; Policy B (split plus cash-event exclusions) needs complete documented
event dates; Policy C (combined-adjusted prices on all intervals) needs verified
factor/endpoint semantics. Amounts are not necessary solely to exclude all cash
crossings, but missing/uncertified dates prevent freezing Policy B here. No
policy was implemented and the research period was not truncated.

The six frozen choices, exact close/open decisions and final universe are
unchanged. No provider data or Bloomberg service was modified/accessed, and no
return, final panel, regression or predictive relationship was constructed.
'''
assert before==protected(text)
assert text.count('| FROZEN |')==6 and text.count('| UNRESOLVED |')==4
design_path.write_text(text,encoding='utf-8')
manifest_path=BASE/'data_manifest.csv';manifest=readcsv(manifest_path);existing={r['risklab_id']:r for r in manifest}
for p in panels:
    row=existing.get(p['id'])
    if row is None:
        row={k:'' for k in manifest[0]};manifest.append(row)
    row.update(risklab_id=p['id'],relative_path=p['relative_path'],path_base='RISKLAB_DATA_ROOT',provider='Bloomberg per catalog; original extraction settings unknown',role='partial AAPL/MSFT action evidence; '+('canonical byte copy' if p['id']==CANONICAL else 'duplicate of RL-4DC331F6CC26'),validation_status='full schema/hash scan; no SPY; ends 2025-09-26; adjustment semantics unresolved',used_in_current_timing_phase='no; corporate-action coverage audit only')
with manifest_path.open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(manifest[0]));writer.writeheader();writer.writerows(manifest)
adjust_path=BASE/'reports/adjustment_comparison.md';text=adjust_path.read_text(encoding='utf-8');marker='## Subsequent daily-panel coverage audit'
if marker in text:text=text.split(marker)[0].rstrip()+'\n'
text+='''
## Subsequent daily-panel coverage audit — 2026-10-27

The previously pending CE-104/sp500_histories review is complete. See
[corporate_action_coverage.md](corporate_action_coverage.md) for independently
verified byte identity, exact schema, missingness, event counts and source
disagreements. The copies supply partial AAPL/MSFT candidate amounts/dates and
split ratios, no SPY rows, no usable Adj Close and no explicit adjustment factor.
Their last date is 2025-09-26; other local event tables do not establish a complete
three-security 2010–2025 calendar. Earlier references above to their not-yet-read
status describe the preceding audit, not current status.

No adjustment policy is newly frozen. The six user-frozen choices and the
endpoint/universe decisions remain unchanged. Policy B requires verified complete
event dates, not necessarily cash amounts; Policy C still lacks factor/endpoint
support. Do not re-download already corroborated events or implement exclusions
from an uncertified merged calendar. No returns or research panel were created.
'''
adjust_path.write_text(text,encoding='utf-8')
# Keep prior metadata-only instructions current without changing any field claims,
# user-observed definitions, production authorization or five-priority ordering.
plan_path=BASE/'reports/bloomberg_pilot_plan.md'
if plan_path.exists():
    t=plan_path.read_text(encoding='utf-8')
    t=t.replace('Inspect locally owned\nCE-104/sp500_histories event columns/provenance before duplicating them.','The local CE-104/sp500_histories review is complete; see\n[corporate_action_coverage.md](corporate_action_coverage.md). These are duplicate\nAAPL/MSFT panels ending in September 2025 with no SPY or usable adjustment factor.\nVerify complete event-date coverage and request only documented gaps, not known events.')
    plan_path.write_text(t,encoding='utf-8')
spec_path=BASE/'manifests/bloomberg_pilot_spec.csv'
if spec_path.exists():
    with spec_path.open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f);spec_fields=reader.fieldnames;spec=list(reader)
    for r in spec:
        if r['item_id']=='dividend_events':
            r['local_overlap_action']='Review completed: CE-104/sp500_histories are byte-identical AAPL/MSFT panels, no SPY, cutoff 2025-09-26, no usable Adj Close/factor. CE-05/06 give partial ex-dates; CE-102 is change-only. Fill verified date gaps only; cash amounts not necessary solely for exclusions.'
            r['terminal_questions']='Verify complete cash-distribution ex-dates, including ordinary/special coverage: SPY before 2019-12-20 and after 2025-09-19; AAPL/MSFT after 2025-09-26; required next-session boundary. Establish existing column date/amount/share basis. Request amounts/factors only if adjustment validation needs them; do not repeat known dates.'
        if r['item_id']=='split_events':
            r['local_overlap_action']='CE-08 and daily duplicate panels corroborate sampled split dates/ratios. Full three-security no-action/reverse-split coverage and late-2025 tail are not certified; SPY absent from daily panels. Reuse known events.'
            r['terminal_questions']='Verify exhaustive split/reverse-split dates or explicit no-action coverage for all three securities through 2025 and required next-session boundary; clarify effective-date and ratio orientation. Do not re-download already corroborated AAPL 2014/2020 or MSFT 2003 dates merely to obtain known events.'
    with spec_path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=spec_fields);writer.writeheader();writer.writerows(spec)
save('verification_checks.json',{'both_source_stat_checks_passed':all(p['source_size_and_mtime_unchanged'] for p in panels),'independent_hash_equivalence_verified':equivalence['equal_actual_sha256'],'global_numeric_and_blank_counts_reconcile':all(all(p['field_stats'][f]['numeric']+p['field_stats'][f]['blank']+p['field_stats'][f]['na_token']+sum(p['field_stats'][f]['non_numeric'].values())==p['row_count_excluding_header'] for f in ['Open','Close','Adj Close','Dividends','Stock Splits']) for p in panels),'frozen_and_endpoint_universe_rows_preserved':True,'protected_design_rows_sha256':hashlib.sha256('\n'.join(before).encode()).hexdigest(),'no_returns_or_final_calendar':True})
print('Wrote corporate-action coverage report; adjustment remains UNRESOLVED; six frozen choices preserved.')
