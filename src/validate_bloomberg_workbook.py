"""Offline Project 2 master-delivery audit; never execute Excel or modify sources.

Run from any directory with Python 3.10+: python src/validate_bloomberg_workbook.py
Uses the repository's stdlib-only OOXML reader and saved exchange calendar.
No Terminal, network, returns, final analysis panel or research design changes.
"""
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from xlsx_readonly import read_workbook, colname, colnum

OUT = ROOT / 'outputs/diagnostics'


def save(name, rows, fields=None):
    rows = list(rows)
    if not rows and fields is None:
        fields = ['status']
    with (OUT / name).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def numeric(v):
    try:
        n = Decimal(str(v))
        return n if n.is_finite() else None
    except InvalidOperation:
        return None


def serial_date(v):
    n = numeric(v)
    if n is None or not 30000 < n < 60000 or n != int(n):
        return None
    return (datetime(1899, 12, 30) + timedelta(days=int(n))).date().isoformat()


def cell(sheet, ref):
    return sheet['cells'].get(ref, {'value': None, 'type': 'missing', 'has_formula': False})


def require(condition, message):
    """Layout checks must remain active even when Python runs with -O."""
    if not condition:
        raise ValueError(message)


def populated(sheet):
    return {ref for ref, c in sheet['cells'].items() if c['value'] is not None or c['has_formula']}


def last_row(sheet):
    return max((int(re.search(r'\d+', ref)[0]) for ref in populated(sheet)), default=0)


def instrument_columns(sheet, width):
    headers = sorted(colnum(ref) for ref in populated(sheet)
                     if re.fullmatch(r'[A-Z]+1', ref) and
                     'EQUITY' in str(cell(sheet, ref)['value']).upper())
    require(bool(headers), 'No instrument headers found')
    require(all((c-1) % (width+1) == 0 for c in headers), 'Changed instrument block spacing')
    end_row = last_row(sheet)
    allowed = {f'{colname(c+j)}{r}' for c in headers for j in range(width)
               for r in range(1, end_row+1)}
    require(not (populated(sheet)-allowed),
            f'Unmapped nonempty cells: {sorted(populated(sheet)-allowed)[:8]}')
    return headers


def column_rows(sheet, columns):
    return sorted({int(re.search(r'\d+', ref)[0]) for ref in populated(sheet)
                   if colnum(ref) in columns})


def validate_price_layout(sheet, original):
    """Fixed pilot blocks are deliberate; reject new data rather than truncate it."""
    blocks = [('SPY US Equity',1,1,10), ('AAPL US Equity',6,1,10),
              ('MSFT US Equity',11,1,10), ('AMZN UW Equity',1,14,21)]
    allowed = {'A13','E13'} | {f'E{r}' for r in range(14,22)}
    for _, col, start, end in blocks:
        allowed |= {f'{colname(col+j)}{r}' for j in range(4) for r in range(start,end+1)}
    require(not (populated(sheet)-allowed), 'Price pilot expanded/moved: update explicit block map before audit')
    anchors = {ref for ref,c in original['cells'].items() if c['formula'] and '_xll.BDH(' in c['formula']}
    require(anchors == {'A1','F1','K1','A14'}, 'Price request anchors changed: review block map')
    for security,col,start,_ in blocks:
        formula = cell(original,f'{colname(col)}{start}')['formula'] or ''
        require(security in formula and 'PX_OFFICIAL_CLOSE,PX_LAST,PX_OPEN' in formula,
                'Price request security/field order changed')
    return blocks


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = ROOT / 'data/raw_bloomberg'
    sources = [raw / 'Bloomberg_Project2_Master.xlsx', raw / 'Bloomberg_Project2_Master - Values.xlsx',
               raw / 'support/bloomberg_ticket_H1342549641.md', raw / 'support/memb_2013_screenshot.png']
    sources += sorted((raw/'support/bloomberg_hp_evidence_2026-11-02').glob('*'))
    sources += [ROOT/'presentation/progress_update/MMF_2026_Project_Progress_Update_Template.pptx']
    require(all(p.is_file() for p in sources), 'Missing or non-file evidence source')
    before = {p: (sha(p), p.stat().st_size, p.stat().st_mtime_ns) for p in sources}
    design_before = sha(ROOT / 'design_decisions.md')
    original, ometa = read_workbook(sources[0])
    values, vmeta = read_workbook(sources[1])
    assert original.keys() == values.keys(), 'Worksheet mismatch requires manual block-map review'
    assert all(not s['date1904'] for b in [original, values] for s in b.values())
    assert not any(c['has_formula'] for s in values.values() for c in s['cells'].values()), 'Values workbook contains formulas; review before treating as static'
    provenance = []
    for p in sources:
        provenance.append({'path': p.relative_to(ROOT).as_posix(), 'sha256': before[p][0], 'bytes': before[p][1],
                           'retrieved_at': 'UNKNOWN', 'document_created': (ometa if p == sources[0] else vmeta if p == sources[1] else {}).get('created', ''),
                           'document_modified': (ometa if p == sources[0] else vmeta if p == sources[1] else {}).get('modified', '')})
    save('master_source_inventory.csv', provenance)
    inventory, reconciliation, requests = [], [], []
    for label, book in [('formula', original), ('values', values)]:
        for name, s in book.items():
            types = Counter(c['type'] for c in s['cells'].values() if c['value'] is not None)
            inventory.append({'workbook': label, 'sheet': name, 'declared_range': s['declared_dimension'],
                              'stored_cells': len(s['cells']), 'nonempty_cells': sum(types.values()),
                              'numeric_cells': types['n'], 'string_cells': types['s'] + types['str'] + types['inlineStr'],
                              'error_cells': types['e'], 'formula_cells': sum(c['has_formula'] for c in s['cells'].values()),
                              'types': json.dumps(types, sort_keys=True)})
            if label == 'formula':
                for ref, c in s['cells'].items():
                    if c['has_formula']:
                        requests.append({'sheet': name, 'cell': ref, 'formula': c['formula'] or 'shared formula continuation',
                                         'cached_value_type': c['type'], 'cached_value': c['value'], 'array_range': c['formula_attributes'].get('ref', '')})
    for name, orig in original.items():
        v = values[name]
        stats = Counter()
        for ref in orig['cells'].keys() | v['cells'].keys():
            a, b = cell(orig, ref), cell(v, ref)
            na, nb = numeric(a['value']), numeric(b['value'])
            if a['type'] == 'n' and na is not None:
                stats['original_numeric'] += 1
                stats['numeric_equal' if b['type'] == 'n' and na == nb else 'numeric_mismatch_or_missing'] += 1
            if a['type'] == 'e' and b['value'] is not None and b['type'] != 'e':
                stats['original_error_replaced_by_static'] += 1
            if a['value'] is None and b['value'] is not None:
                stats['static_values_without_original_cache'] += 1
            if a['type'] in ['s', 'str', 'inlineStr'] and a['value'] is not None and a['value'] != b['value']:
                stats['text_mismatch'] += 1
        reconciliation.append({'sheet': name, **{k: stats[k] for k in ['original_numeric', 'numeric_equal', 'numeric_mismatch_or_missing', 'original_error_replaced_by_static', 'static_values_without_original_cache', 'text_mismatch']}})
    save('master_sheet_inventory.csv', inventory)
    save('master_workbook_reconciliation.csv', reconciliation)
    save('master_saved_requests.csv', requests)
    calendar_path = ROOT / 'reports/timing_diagnostics/exchange_sessions_2010_2025.csv'
    with calendar_path.open(encoding='utf-8-sig') as f:
        calendar = list(csv.DictReader(f))
    expected = {r['session_date'] for r in calendar}
    calendar_start, calendar_end = min(expected), max(expected)
    summary, flags, gaps, series = [], [], [], {}
    for name, field in [('action_volume', 'OFFICIAL_CLOSE_AUCTION_VOLUME'), ('daily_volume', 'PX_VOLUME')]:
        s = values[name]
        maxrow = last_row(s)
        for col in instrument_columns(s, 2):
            security = cell(s, f'{colname(col)}1')['value']
            assert security and 'EQUITY' in security.upper(), (name, col, security)
            formula = cell(original[name], f'{colname(col)}2')['formula']
            assert formula and field in formula
            obs = []
            for row in range(2, maxrow + 1):
                dr, vr = f'{colname(col)}{row}', f'{colname(col+1)}{row}'
                dc, vc = cell(s, dr), cell(s, vr)
                if dc['value'] is None and vc['value'] is None:
                    continue  # format-only blanks are not observations
                d, n = serial_date(dc['value']), numeric(vc['value'])
                require(d is None or calendar_start <= d <= calendar_end,
                        'Volume date outside saved calendar bounds: extend documented calendar before audit')
                obs.append({'date': d, 'value': n, 'raw_value': vc['value'], 'date_cell': dr, 'value_cell': vr})
                reasons = []
                if d is None: reasons.append('invalid_or_missing_date')
                if n is None: reasons.append('missing_or_error_volume')
                if n is not None and n <= 0: reasons.append('nonpositive_volume')
                if d and d not in expected: reasons.append('non_session_date')
                if security == 'SPY UP EQUITY' and n == 100: reasons.append('SPY_100_likely_invalid_support_H1342549641')
                for reason in reasons:
                    flags.append({'sheet': name, 'security': security, 'date': d or '', 'date_cell': dr, 'value_cell': vr, 'raw_value': vc['value'], 'reason': reason})
            dates = [o['date'] for o in obs if o['date']]
            counts = Counter(dates)
            lo, hi = min(dates), max(dates)
            missing = sorted({d for d in expected if lo <= d <= hi} - set(dates))
            before_start = {d for d in expected if '2013-05-01' <= d < lo}
            after_end = {d for d in expected if hi < d <= '2025-12-31'}
            for d in missing:
                gaps.append({'sheet': name, 'security': security, 'date': d, 'classification': 'interior_missing_session'})
            for d in sorted(after_end):
                gaps.append({'sheet': name, 'security': security, 'date': d, 'classification': 'after_delivered_coverage_before_requested_end'})
            numeric_values = [o['value'] for o in obs if o['value'] is not None]
            summary.append({'sheet': name, 'security': security, 'field': field, 'date_column': colname(col), 'value_column': colname(col+1),
                            'schema': 'Excel date serial; numeric volume (units/adjustments unverified)', 'rows': len(obs), 'first_date': lo, 'last_date': hi,
                            'duplicate_dates': sum(n-1 for n in counts.values()), 'invalid_dates': sum(o['date'] is None for o in obs),
                            'missing_error_values': sum(o['value'] is None for o in obs), 'zeros': sum(n == 0 for n in numeric_values),
                            'negative': sum(n < 0 for n in numeric_values), 'non_session_dates': len(set(dates)-expected),
                            'interior_missing_sessions': len(missing), 'before_delivered_start': len(before_start), 'after_delivered_end': len(after_end),
                            'most_frequent_value_count': max(Counter(numeric_values).values(), default=0)})
            require((name,security.split()[0]) not in series, 'Multiple venue lines for one symbol: explicit identity mapping required')
            series[name, security.split()[0]] = obs
    save('master_series_summary.csv', summary)
    save('master_flagged_observations.csv', flags, ['sheet','security','date','date_cell','value_cell','raw_value','reason'])
    save('master_calendar_gaps.csv', gaps, ['sheet','security','date','classification'])
    # Source-consistency counts only, never persist a final auction-share variable.
    compatibility = []
    for a in [x for x in summary if x['sheet'] == 'action_volume']:
        symbol = a['security'].split()[0]
        daily = {o['date']: o for o in series['daily_volume', symbol] if o['date']}
        c = Counter()
        for o in series['action_volume', symbol]:
            den = daily.get(o['date'])
            if den is None or den['value'] is None: c['missing_denominator'] += 1; continue
            if den['value'] <= 0: c['nonpositive_denominator'] += 1; continue
            if o['value'] is None: c['missing_numerator'] += 1; continue
            c['comparable_pairs'] += 1
            c['numerator_gt_denominator'] += o['value'] > den['value']
        compatibility.append({'symbol': symbol, 'auction_identifier': a['security'], 'daily_identifier': next(x['security'] for x in summary if x['sheet']=='daily_volume' and x['security'].split()[0]==symbol),
                              **{k:c[k] for k in ['comparable_pairs','missing_denominator','nonpositive_denominator','missing_numerator','numerator_gt_denominator']},
                              'units_adjustments_venue_boundaries': 'NOT VERIFIED'})
    save('master_volume_compatibility.csv', compatibility)
    actions=[]
    s=values['corporate_actions']
    for col in instrument_columns(s, 7):
        security=cell(s,f'{colname(col)}1')['value']
        rows=[]
        for row in range(2,last_row(s)+1):
            v=[cell(s,f'{colname(col+j)}{row}')['value'] for j in range(7)]
            if not any(x is not None for x in v):continue
            rows.append((serial_date(v[1]), v[4], v[6], sum(serial_date(x) is None for x in v[:4])))
        dd=[x[0] for x in rows if x[0]]
        actions.append({'security':security,'range':f'{colname(col)}2:{colname(col+6)}{last_row(s)}','events':len(rows), 'candidate_ex_date_min':min(dd) if dd else '', 'candidate_ex_date_max':max(dd) if dd else '',
                        'event_types':json.dumps(dict(Counter(x[2] for x in rows))), 'duplicate_candidate_date_type':len(rows)-len({(x[0],x[2]) for x in rows}), 'missing_event_value':sum(numeric(x[1]) is None for x in rows),
                        'missing_invalid_positional_dates':sum(x[3] for x in rows), 'semantic_status':'Returned headers absent: four positional dates, event value, frequency, event type. Column 2 candidate ex/effective date only.'})
    save('master_corporate_actions_summary.csv',actions)
    price=[]
    for security,col,start,end in validate_price_layout(values['price_pilot'], original['price_pilot']):
        s=values['price_pilot'];rows=[[cell(s,f'{colname(col+j)}{i}')['value'] for j in range(4)] for i in range(start,end+1)]
        dates=[serial_date(v[0]) for v in rows]
        price.append({'security':security,'range':f'{colname(col)}{start}:{colname(col+3)}{end}','rows':len(rows),'first_date':min(d for d in dates if d),'last_date':max(d for d in dates if d),
                      'fields':'PX_OFFICIAL_CLOSE;PX_LAST;PX_OPEN','duplicate_dates':len(dates)-len(set(dates)), 'missing_invalid_dates':sum(d is None for d in dates),
                      'missing_error_prices':sum(numeric(x) is None for v in rows for x in v[1:]),'nonpositive_prices':sum(numeric(x) is not None and numeric(x)<=0 for v in rows for x in v[1:]),
                      'non_session_dates':sum(d is not None and d not in expected for d in dates),
                      'close_last_equal':sum(numeric(v[1]) is not None and numeric(v[1])==numeric(v[2]) for v in rows)})
    save('master_price_pilot_summary.csv',price)
    membership=values['SP500_membership']
    require(all(colnum(ref) in {1,2,4} for ref in populated(membership)), 'New membership columns: review schema')
    weighted_rows=column_rows(membership,{1,2})
    historical_rows=column_rows(membership,{4})
    weighted=[cell(membership,f'A{i}')['value'] for i in weighted_rows]
    historical=[cell(membership,f'D{i}')['value'] for i in historical_rows]
    weights=[cell(membership,f'B{i}')['value'] for i in weighted_rows]
    require(all(weighted) and all(historical), 'Missing membership identifier: review source rows')
    memb={'rows_2025':len(weighted),'rows_purported_2013':len(historical),'duplicate_identifiers_2025':len(weighted)-len(set(weighted)), 'duplicate_identifiers_2013':len(historical)-len(set(historical)),
          'lists_identical_in_order':weighted==historical,'shared_identifiers':len(set(weighted)&set(historical)), 'identifiers_only_2025':len(set(weighted)-set(historical)), 'identifiers_only_2013':len(set(historical)-set(weighted)), 'distinct_weights':len(set(weights)), 'negative_weights':sum(numeric(w) is not None and numeric(w)<0 for w in weights),'missing_weights':sum(numeric(w) is None for w in weights),
          'ABNB_in_2013':'ABNB UW' in historical, 'BX_in_2013':'BX UN' in historical,'returned_effective_dates':0,'classification':'REJECT as historical point-in-time universe; weights suspicious/unusable'}
    save('master_membership_diagnostics.csv',[memb])
    tracked=subprocess.run(['git','ls-files','--','data/raw_bloomberg/','outputs/diagnostics/',
                            'presentation/progress_update/MMF_2026_Project_Progress_Update_Template.pptx'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    assert not tracked, f'Licensed data already tracked: {tracked}'
    ignored=subprocess.run(['git','check-ignore','--',*[str(p.relative_to(ROOT)) for p in sources],'outputs/diagnostics/master_series_summary.csv'],cwd=ROOT,capture_output=True,text=True,check=True)
    require(len(ignored.stdout.splitlines())==len(sources)+1,'Evidence or template not Git-ignored')
    assert sha(ROOT/'design_decisions.md')==design_before
    assert all((sha(p),p.stat().st_size,p.stat().st_mtime_ns)==before[p] for p in sources),'Source changed during audit'
    write_report(inventory,reconciliation,summary,compatibility,actions,price,memb,series)
    require(all((sha(p),p.stat().st_size,p.stat().st_mtime_ns)==before[p] for p in sources),
            'Source changed during evidence/template review')
    (OUT/'master_audit_run.json').write_text(json.dumps({
        'completed_at_local_with_offset':datetime.now().astimezone().isoformat(),
        'timestamp_role':'audit execution only; not Bloomberg retrieval',
        'python_version':sys.version,'script':'src/validate_bloomberg_workbook.py',
        'source_checksums_verified':len(sources),'raw_and_design_unchanged':True,
        'manual_review_reproduced_by_ocr':False,
        'reviewed_evidence_hashes_checked':True,
        'panel_or_returns_or_models_created':False,
    },indent=2),encoding='utf-8')
    print('Audit complete: raw hashes/size/mtime and design unchanged; raw/diagnostics ignored and untracked.')


def write_report(inventory,reconciliation,summary,compatibility,actions,price,memb,series):
    from review_terminal_evidence import review
    terminal=review(series,actions,OUT)
    text='''# Bloomberg master source audit

Offline ZIP/XML audit of both Master workbooks, local field_definitions notes,
Help Desk ticket H1342549641 and membership screenshot. No Excel refresh or
formula execution, downloads of Bloomberg data, research returns, panel or models.
All workbook/support/template SHA256/size/mtime checks and the research-design checksum are
unchanged after audit. Raw files and observation-level diagnostics are ignored
and untracked by Git. Retrieval timestamps and unspecified Bloomberg defaults
remain unknown. Checksums/document timestamps are in master_source_inventory.csv.

Reproduce with `.venv/Scripts/python.exe src/validate_bloomberg_workbook.py`.
Dependencies: Python stdlib, scripts/xlsx_readonly.py, the saved validated
exchange calendar, Git and the four delivered source files. The screenshot was
visually reviewed; the script does not perform OCR or reproduce that judgment.
Public announcement facts below are fixed source notes, not network dependencies.
Diagnostics are in ignored outputs/diagnostics/master_*.csv.

## Evidence types and audit boundaries

- **Automated on each run:** workbook parsing, numeric/cached comparisons,
  dynamic volume/action/member boundaries, duplicate/error/gap checks, SPY value
  flags, checksums, design immutability and Git exclusion checks. These checks
  do not read the meaning of support prose, images or external announcements.
- **Manually reviewed local evidence:** Help Desk ticket H1342549641, membership
  screenshot and five new HP screenshots. The ten transcribed numeric rows and
  WMT UN blank range were visually verified, not OCR validated. Screenshot field
  labels are truncated; full PQ817 identity still relies on the user's selection
  report. Re-runs check reviewed image hashes and compare eight rows to workbook
  values; two UW rows have no corresponding workbook series.
- **User-transcribed FLDS/DPDF evidence:** terminal_field_notes_2026-11-02.md,
  under support/bloomberg_hp_evidence_2026-11-02/. Text was reviewed but no full
  FLDS/DPDF/settings screenshots were supplied. Do not promote it to screenshot-
  verified settings or settings proven to apply to each original request.
- **Previously reviewed public documentation:** linked Walmart/Nasdaq and S&P
  announcements below. These contextual facts are not fetched or revalidated
  by this offline script. Manual interpretations apply to the supplied delivery;
  changed support files require renewed manual review.
- **Still unverified:** full selected-field setup, saved-request adjustment
  compatibility, instrument-specific auction endpoints and historical membership
  query behavior. See
  [follow-up checklist](bloomberg_followup_checklist.md).

Volume and corporate-action instrument columns/rows are discovered from actual
populated cells; membership lengths are independent. Unmapped block cells fail
explicitly. Price-pilot ranges remain intentionally mapped: appended/moved data
or changed request anchors/field order trigger a ValueError instead of silent
truncation. Dates beyond the saved calendar bounds also require explicit review.
Empty/format-only cells do not expand observation counts. Historical descriptive
prose below describes the reviewed Master delivery; tables are regenerated.

## Workbook structure and export fidelity

| Workbook | Sheet | Declared range | Nonempty cells | Numeric cells | Error cells | Formula cells |
| --- | --- | --- | ---: | ---: | ---: | ---: |
'''
    for a in inventory:text+=f"| {a['workbook']} | {a['sheet']} | {a['declared_range']} | {a['nonempty_cells']} | {a['numeric_cells']} | {a['error_cells']} | {a['formula_cells']} |\n"
    text+='''
Declared dimensions include blank formatting and are not observation counts.
The Values workbook has no formula cells. Volume blocks have row-1 instrument
labels, date serials and numeric values in paired columns every third column;
corporate actions have seven positional fields every eighth column. Price blocks
have date plus PX_OFFICIAL_CLOSE, PX_LAST, PX_OPEN, with no returned field headers;
their order comes from saved requests. AMZN E14:E21 is a saved close-minus-last
check, not an additional price series. Blank formatting cells are excluded;
observations with one missing member of a date/value pair are retained and flagged.
No field or exchange identity is inferred from numeric resemblance.

| Sheet | Original numeric cells | Equal numeric cells | Mismatch/missing in Values | Error anchors replaced by static values | Values without original cache |
| --- | ---: | ---: | ---: | ---: | ---: |
'''
    for a in reconciliation:text+=f"| {a['sheet']} | {a['original_numeric']} | {a['numeric_equal']} | {a['numeric_mismatch_or_missing']} | {a['original_error_replaced_by_static']} | {a['static_values_without_original_cache']} |\n"
    text+='''
The original contains #NAME? request anchors and missing result caches. Equality
checks cover only numeric cells actually retained there. Faithful preservation
of all downloaded values CANNOT be certified from this pair: many static dates,
values and complete price/member blocks have no original numeric counterpart.
No formulas were evaluated to manufacture a comparison. Shared cached data,
formula intent and static source plausibility are separate evidence. In this
delivery the eight equal numeric cells are AMZN E14:E21 cached difference checks,
not original price/volume observations: none of the Bloomberg observation values
has a numeric original cache to compare against. Zero mismatches is not proof
that all observations were faithfully exported.

## Volume coverage and merge-key checks

OFFICIAL_CLOSE_AUCTION_VOLUME uses venue lines UP/UW/UN; PX_VOLUME uses US
composite identifiers. Full identifiers are preserved in diagnostics. Calendar
checks use saved 2010–2025 exchange sessions, restricted to actual coverage for
interior gaps and to requested May 1, 2013–December 31, 2025 for boundary counts.
Pre-coverage dates are not called interior missing observations.

| Field | Identifier | Rows | First date | Last date | Duplicate dates | Missing/errors | Zero/negative | Interior gaps | Uncovered sessions after end |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
'''
    for a in summary:text+=f"| {a['field']} | {a['security']} | {a['rows']} | {a['first_date']} | {a['last_date']} | {a['duplicate_dates']} | {a['missing_error_values']} | {a['zeros']}/{a['negative']} | {a['interior_missing_sessions']} | {a['after_delivered_end']} |\n"
    text+='''
Schema: Excel 1900-system date serials, numeric volume; no units, currency or
adjustment settings returned. Saved requests have no explicit adjustment options.
Absence of options is not evidence of unadjusted shares. Unique dated keys are
necessary but not sufficient for merging: match identities across venue/composite
lines explicitly and retain original security, field and request provenance.
Do not merge by worksheet row number or silently replace exchange suffixes.
All 16 daily series have 3,188 valid sessions, May 1, 2013–December 31, 2025,
with no duplicate dates, missing/error values, nonpositive values or interior
gaps. Auction gaps are concentrated on August 12, 2019 (JPM, JNJ, XOM, WMT,
PG, KO, HD and MA); JNJ additionally lacks October 29, 2019. These are true
interior session gaps, distinct from WMT's final coverage cutoff. No gap is filled.

### SPY: likely invalid source observations retained

'''
    spy=series['action_volume','SPY'];hundred=[o['date'] for o in spy if o['value']==100]
    text+=f"Independently found **{len(hundred)} observations equal to 100**, {min(hundred)}–{max(hundred)}. "
    cal=list(csv.DictReader((ROOT/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv').open()))
    mid={r['session_date'] for r in cal if min(hundred)<=r['session_date']<=max(hundred)}
    text+=f"They occupy {len(mid)} expected sessions; interruption(s): {', '.join(sorted(mid-set(hundred)))}.\n"
    text+='''The ticket's “87 consecutive” description is therefore inaccurate. It calls
the observations almost certainly non-genuine and lists possible causes, rather
than confirming a specific placeholder mechanism. Workbook field_definitions
overstates this as confirmed placeholder/default fill and says NaN; the actual
numeric entries are audited as delivered. All 87 are explicitly flagged as likely
invalid, preserved unchanged and never imputed/deleted. Ticket says no corrected
series currently surfaced through BQL and suggests HP/PQ817 verification, not a
guaranteed correction. New HP screenshots visually corroborate all seven
transcribed SPY rows, including four 100 values, the September 7 interruption
and non-100 neighbors on May 9 and September 14. All seven match the static
workbook exactly. These selected rows corroborate stored values, not every one
of the 87 observations or their cause. The full field label/setup is not visible.
No automatic exclusion, replacement or claim of a proven sentinel is made.

### Walmart: endpoint and listing-line issue

'''
    w=[a for a in summary if a['security'].startswith('WMT ')]
    for a in w:text+=f"- {a['security']}, {a['field']}: {a['first_date']}–{a['last_date']}; {a['after_delivered_end']} requested sessions after its delivered end.\n"
    text+='''Walmart's transfer from NYSE to Nasdaq took effect December 9, 2025;
Nasdaq instructed redistributors to update listing market after December 8 close.
This supports a venue-line discontinuity, not a corporate disappearance. Sources:
[Walmart's announcement](https://stock.walmart.com/sec-filings/all-sec-filings/content/0000104169-25-000177/pressrelease-transfertonas.htm)
and [Nasdaq technical notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2025-35).
New HP images show a populated closing-auction-labelled column on WMT UW Equity
from December 9 through December 31, 2025, including both endpoints; WMT UN
shows the December 8 value and blank auction cells on subsequent in-range trading
dates. The three transcribed numeric Walmart rows match their images. UN's
December 8 value also matches the workbook; UW observations are absent from
the workbook, not verified numerical continuations of it. UN's separate Volume
column remains populated on some later dates, so UN Volume must not be used as
a consolidated US denominator by assumption. Empty holiday/grid rows are not
missing trading sessions.

Status: UW continuation observed on HP, not yet a validated joined history.
Still require stable security/share-class identity and effective UN→UW mapping,
untruncated field setup, consistent units/adjustments and a provenance-preserved
dated UW segment with per-session overlap/gap/duplicate checks at the boundary.
No data were downloaded or spliced. A later narrowly targeted segment export
would be conditional on retaining those WMT dates, not a full re-download.

### Auction share compatibility

'''
    text+=f"Across all {len(compatibility)} symbols, source-consistency diagnostics find {sum(a['numerator_gt_denominator'] for a in compatibility)} auction values exceeding daily volume, {sum(a['missing_denominator'] for a in compatibility)} missing denominators and {sum(a['nonpositive_denominator'] for a in compatibility)} nonpositive denominators. No final share variable is saved.\n"
    text+='''Intended construct: **primary-exchange closing-auction shares divided by
consolidated U.S. daily shares**. This is not auction share of primary-exchange
daily volume. User-transcribed FLDS notes describe PQ817 and PX_VOLUME in these
share units for SPY/AAPL/MSFT/JPM; that supports conditional economic feasibility,
not identical market scope. Help Desk separately ties PQ817 to local-venue
publication. Arithmetic bounds do not certify measurement compatibility.

User-transcribed DPDF findings say split adjustment YES / SpltAdj=Y, cash
dividends unadjusted. No settings screenshot or per-request adjustment evidence
establishes that these defaults governed each saved series, that PQ817 and
PX_VOLUME adjust identically, or that adjusted share counts agree with RiskLab
minute volume. Confirm denominator auction inclusion, trade filters/session
boundaries and identical split basis. No perfect-match claim, rescaling or final
share variable is authorized. The two market scopes must remain explicit.

## Prices and corporate actions

| Price identifier | Rows | First date | Last date | Missing/error prices | Duplicate dates | Official close equals last |
| --- | ---: | --- | --- | ---: | ---: | ---: |
'''
    for a in price:text+=f"| {a['security']} | {a['rows']} | {a['first_date']} | {a['last_date']} | {a['missing_error_prices']} | {a['duplicate_dates']} | {a['close_last_equal']} |\n"
    text+='''These are validation observations only. The AMZN June 2022 window is an
additional action-period pilot, not authorization to choose an adjustment rule.
Equal closes do not establish official auction identity or full-history
equivalence. No nominal Bloomberg/adjusted RiskLab prices are combined.

Supplied field descriptions (user transcriptions, not FLDS screenshots):

- PX_OFFICIAL_CLOSE: exchange-calculated/published official price, potentially
  different from last trade; exceptions depend on market. Reported current and
  historical API availability does not guarantee U.S. auction execution on every
  instrument/date or rule out official-mark fallback.
- PX_LAST: last exchange-provided equity price, not necessarily official close.
- PX_OPEN: first traded price for the day (last open day when closed). Transcript
  mentions PX_NASDAQ_OPEN on UQ for NASDAQ Global Exchange securities; this does
  not certify opening-auction identity for every US/UW line.

Exact instrument-specific auction endpoints, adjustment basis and the applicable
NASDAQ line/fallback rules remain unresolved. No design decision is frozen here.

| Corporate-action identifier | Events | Candidate ex/effective start | End | Date/type duplicates | Missing event values | Missing/invalid positional dates | Raw event types |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
'''
    for a in actions:text+=f"| {a['security']} | {a['events']} | {a['candidate_ex_date_min']} | {a['candidate_ex_date_max']} | {a['duplicate_candidate_date_type']} | {a['missing_event_value']} | {a['missing_invalid_positional_dates']} | {a['event_types']} |\n"
    text+='''DVD_HIST_ALL saved requests now specify 20130101–20260131. Actual static
coverage must be read from results, not assumed to honor current saved overrides;
prior dates can persist in an exported workbook. Four positional dates, an event
value, frequency and event type are present but returned column headers absent.
The newly supplied DVD_HIST_ALL description supports this ordered schema:
Declared Date / EX-Date / Record Date / Pay Date / Net Amount (or Terms for
noncash distributions) / Frequency / Dividend Type. Column 2 therefore has
documentary support as EX-Date; actual export headers and noncash terms/ratio
direction still require confirmation. Diagnostics retain their original
candidate labels rather than silently reinterpreting source fields.

The transcript specifies the most recent **275 records** within the requested
range, with DVD_START_DT/DVD_END_DT overrides; BDS returns net when net and gross
are both shown. Cash/stock distributions are capital-change adjusted, and date
overrides restrict that adjustment window. Thus a number is not automatically
nominal historical cash or a directly usable split factor; changing the request
range can affect comparability. Split record/pay dates may be absent unless
published. Reported API availability is current-value bulk history, not proof of
point-in-time event availability. No completeness or look-ahead claim follows.
'''
    text+=f"Current exports contain at most {terminal['max_events']} events per security, below 275; the cap is not visibly reached. This does not prove exhaustive event scope or correct request settings. A future count at the cap stops the audit for review.\n"
    text+='''Corporate actions remain validation evidence, not an approved complete event
calendar or adjustment policy. No actions were filtered at the research end date;
2026 events and missing non-ex dates remain visible in diagnostics.

## Membership: reject for historical universe

'''
    text+=f"A:B contains {memb['rows_2025']} purported 2025-12-31 identifiers/weights. D contains {memb['rows_purported_2013']} purported 2013-05-02 members from INDX_MEMBERS. Lists identical in order: {memb['lists_identical_in_order']}; they share {memb['shared_identifiers']} identifiers and have {memb['identifiers_only_2025']} / {memb['identifiers_only_2013']} unique to the 2025 / purported-2013 list. Both have no duplicate identifiers. Weights have {memb['distinct_weights']} distinct value(s), with {memb['negative_weights']} negative weights near zero; unusable without correction. No returned effective dates exist.\n"
    text+='''The screenshot displays END_DATE_OVERRIDE=20130502 on the worksheet query,
with modern identifiers such as ABNB in its result, alongside a MEMB terminal
window visibly set to 02/05/2013 showing a different historical list. Its date
display convention is not independently established, so the screenshot alone
does not prove a date-exact match to the formula. It does corroborate a mismatch
between worksheet extraction and historical terminal display.
Airbnb and Blackstone appear in the purported 2013 result but were added to the
S&P 500 effective September 18, 2023, per the
[index provider's announcement](https://www.spglobal.com/spdji/en/documents/indexnews/announcements/20230901-1465959/1465959_sept2023shuf.pdf).
Thus it cannot be a valid 2013 constituent universe. Substantially overlapping modern-style lists
suggest the override was ignored or the results are stale; exact cause is not
proven. INDX_MEMBERS and INDX_MWEIGHT_HIST are different fields and must be
validated separately. Do not normalize the weights, call this point-in-time
history, or use it to define the cross-sectional sample.

## Readiness and minimum follow-up

- **Validated structural data:** static, dated volume and price records and
  corporate-action source blocks, with key/error/coverage diagnostics. Usable
  for further validation and explicit identity mapping; no blanket certification
  of Bloomberg market definitions or original-export fidelity.
- **Partially usable:** daily volumes and most closing-volume history, pending
  units/adjustment/venue review; corporate-action histories pending bulk schema;
  small price pilots pending endpoint definitions. Retain coverage limitations.
- **Likely invalid/suspicious:** 87 SPY auction entries; historical membership
  result and constant negative weights. Preserve evidence but do not approve use.
- **Minimum blockers before cleaning/merging:** verify documented units/settings
  apply to original requests, denominator auction inclusion and trade/session
  scope, common split basis and full security mapping; resolve/document
  SPY treatment; obtain WMT new-venue missing auction dates if retaining those
  dates; document the other interior auction gaps without filling them; confirm
  bulk action schema and endpoints. Confirm full export fidelity
  from a saved, populated original or an independent checksum-controlled export
  if numerical source reconciliation is required. No full duplicate re-download
  is justified solely to reproduce already covered dates.
- **Conditional extension:** a validated historical membership source with stable
  identifiers is essential only for a historical S&P universe. It is not needed
  for a fixed-symbol pilot. Signed imbalance is not supplied and would be a
  separately defined mechanism extension, not a substitute for auction volume.

No pre-specified research decision was changed; no cleaning policy was silently
applied. These findings supersede earlier delivery-specific readiness claims for
the Master files only; earlier raw deliveries remain untouched.
'''
    (ROOT/'reports/bloomberg_source_audit.md').write_text(text,encoding='utf-8')


if __name__ == '__main__':
    main()
