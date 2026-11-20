"""Render source-validation findings from repository diagnostics (no source reads)."""
import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'reports' / 'source_diagnostics'


def load(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def mdtable(headers, rows):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---']*len(headers)) + ' |'] +
                     ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows])


search = load('catalog_search.json')
mm = load('mm04.json')
pilots = [load(s+'.json') for s in ['spy', 'aapl', 'msft']]
ap = load('constituent_candidate.json')
zero = load('zero_volume_review.json')
unique = {}
for record in search['matches']:
    key = record['id']
    if key not in unique:
        unique[key] = {**record, 'found_in': []}
    unique[key]['found_in'].append(record['inventory'])

annex = ['# Catalog search evidence', '',
         'Searched all records, case-insensitively with punctuation and CamelCase normalization, plus broad auction, imbalance, NOII, paired-share, constituent, membership, and members terms. Similar names establish candidate status only.', '',
         mdtable(['Inventory', 'Rows scanned'], [[k,v['rows_scanned']] for k,v in search['inventories'].items()]), '',
         'Queries: '+', '.join('`'+t+'`' for t in search['terms'])+'.', '',
         f'{len(search["matches"])} inventory hits represent {len(unique)} distinct dataset IDs. All broad matches are retained below, including false positives. No imbalance/NOII/paired-share match was found. Catalog values are reported verbatim; unknown or blank frequency/coverage is not filled by inference.', '']
for record in unique.values():
    coverage = f'{record.get("start") or "unspecified"} to {record.get("end") or "unspecified"}'
    if record['id']=='RL-ED340E2FF91E':
        assessment = 'Confirmed open/close auction-volume fields after parsing the source; no imbalance field. Catalog fields describe the preamble incorrectly. Date alignment and units require review.'
    elif record['id']=='RL-0A4026EAEC53':
        assessment = f'Inspected price/volume panel: {ap["rows"]:,} rows, {ap["unique_symbols"]} symbols, {ap["unique_dates"]:,} distinct dates, {ap["min_date"]} to {ap["max_date"]}. Not a membership entry/exit table; no membership flag. Title alone does not establish a historical S&P 500 universe. Catalog coverage/frequency are unspecified.'
    elif 'constituentsdata' in record['path']:
        assessment = 'Broad constituent candidate only. Metadata exposes Ticker, Name, Price and Shrt Int:D-1, without effective membership dates. Not verified as S&P 500 membership or imbalance; contents were not scanned.'
    else:
        assessment = 'Broad-search false positive for this purpose: corporate transaction data with index-constituent attributes, not evidence of a complete dated membership history or auction imbalance. Contents were not scanned.'
    annex.extend(['## '+record['id'], '', '- Path: `'+record['path']+'`',
                  '- Found in: '+', '.join(record['found_in']),
                  '- Description: '+record.get('description',''),
                  '- Fields (catalog): `'+record.get('fields','')+'`',
                  '- Frequency (catalog): `'+(record.get('frequency') or 'unspecified')+'`',
                  '- Coverage (catalog): '+coverage,
                  '- Assessment: '+assessment, ''])
annex.extend(['## Exact pilot inventory records', '',
              mdtable(['Symbol', 'ID', 'Path', 'Inventory frequency', 'Coverage'],
                      [[r['path'].split('/')[-1].split('_')[0],r['id'],'`'+r['path']+'`',r['frequency'],'not supplied by this inventory'] for r in search['pilot_records']]), '',
              'Observed minute frequency, schema and date coverage are reported in the checkpoint from full file scans. These are not retroactive modifications to the inventory.', ''])
(BASE/'reports'/'catalog_search_matches.md').write_text('\n'.join(annex), encoding='utf-8')

# Extract the verified root from the recorded Windows source path.
root = mm['path'].split('\\bloomberg\\')[0]
lines = ['# Project 2: source-validation checkpoint', '',
         '**Price Pressure at the Close: Closing-Print Reversal and the Role of the Auction**', '',
         'Inspection date: 2026-10-26. Source inventory and integrity validation only; no research variables or model results.', '',
         '## Verified access checkpoint', '',
         'Verified `RISKLAB_DATA_ROOT`:', '', '```text', root, '```', '',
         'The catalog path is always `<RISKLAB_DATA_ROOT>\\_catalog`. The previously configured C: root was stale.', '',
         'Read-only commands outside the sandbox verified the mounted root, catalog, `data_paths.py`, `catalog.csv`, `intraday_inventory.csv.gz`, and `bloomberg/inventory.csv`. The mounted utility resolved MM-04 with `get(id=...)` and the three pilot files with `resolve(relative_path)`. `.vscode/settings.json` configures new Windows terminals; `. .\\scripts\\use_risklab.ps1` configures an existing PowerShell session. Python bytecode writes are disabled. No provider files were written or copied.', '',
         '## Source classification', '',
         mdtable(['Class', 'Observed evidence'], [
             ['AVAILABLE','SPY, AAPL and MSFT OHLCV: complete-file integrity scans passed structural/numeric checks; local format documentation found. Inventories and path utility are accessible. MM-04 exists and its two volume fields are identified.'],
             ['PARTIAL','Minute-window coverage is incomplete on some observed dates; early SPY opening labels are often absent. MM-04 has blanks/error cells and starts in 2013 despite a 2010 request. AP15 is a 205-symbol price/volume panel, not established full historical index coverage.'],
             ['METADATA REVIEW','MM-04 security/date alignment, volume units and adjustment basis; bar-to-official-auction-price mapping; zero-volume rows contrary to documentation; historical membership/identifier mappings and exchange-calendar alignment.'],
             ['MISSING','No signed closing-auction imbalance/NOII/paired-share source or dated S&P 500 membership history identified in the searched inventories. This is a search finding, not proof that no such file exists elsewhere. Official closing/opening auction prices are not established by the inspected fields.']]), '',
         '## Catalog searches', '',
         f'Scanned {search["inventories"]["catalog"]["rows_scanned"]:,} catalog records, {search["inventories"]["bloomberg_inventory"]["rows_scanned"]:,} Bloomberg inventory records, and {search["inventories"]["intraday_inventory"]["rows_scanned"]:,} intraday inventory records. Broad searches returned 18 distinct dataset IDs, each present in both non-intraday inventories; no relevant intraday imbalance or membership candidate was found.', '',
         'Exact IDs, paths, descriptions, fields, frequencies and coverage for every match are in [catalog_search_matches.md](catalog_search_matches.md); unabridged inventory records are in [catalog_search.json](source_diagnostics/catalog_search.json). No construct equivalence is inferred from a name.', '',
         '- `RL-ED340E2FF91E`: MM-04; source contains official open/close auction-volume fields, not imbalance.',
         '- `RL-0A4026EAEC53`: `bloomberg/02_market/factors/AP15_All S&P Composite Constituents_PXLAST_PXVOLUME (4).csv`; fields `Ticker, Date, PX_LAST, PX_VOLUME`. Catalog frequency/coverage unknown. Direct scan: 1,058,875 rows, 205 symbols, 9,040 distinct dates, 1990-01-02 to 2025-10-20. No membership-effective-date or membership flag field.',
         '- Twelve `*_constituentsdata_*` candidates expose `Ticker, Name, Price, Shrt Int:D-1`; metadata does not establish dated membership. Four corporate-transaction candidates contain index-constituent attributes but are not membership histories. See the exact records in the annex.', '',
         '## MM-04 actual contents', '',
         '- Dataset ID: `RL-ED340E2FF91E`.', '- Physical path: `'+mm['path']+'`.',
         f'- File size: {mm["size_bytes"]:,} bytes.',
         '- Physical CSV: **3,114 rows × 1,007 columns**, including six preamble/header rows. Parsed observation table: **3,108 rows × 1,007 columns** (one date plus 1,006 values). The catalog row count of 3,113 includes five non-observation rows after treating the first physical row as a header.',
         '- Header: row 1 `Start Date,1/1/2010`; row 2 blank end date; row 3 blank; row 4 security labels; row 5 human-readable field labels; row 6 `Dates` and repeated Bloomberg field mnemonics.',
         '- Schema: date strings `M/D/YYYY`; numeric value columns with blank and `#N/A N/A` cells. Typed interpretation is date + nullable numeric, not uniformly integer. No pandas dataframe was required; shape and types were established directly from CSV.',
         '- Fields: `OFFICIAL_OPEN_AUCTION_VOLUME` / `Official Open Auction Volume` and `OFFICIAL_CLOSE_AUCTION_VOLUME` / `Official Close Auction Volume`.',
         '- Securities: 503 distinct Bloomberg-form strings, for example `A UN Equity`, `AAPL UW Equity`, `MSFT UW Equity`, `BRK/B UN Equity`. Each security label spans the following open/close pair; within-header propagation was used solely to interpret those two columns. Security suffixes and slash tickers must be mapped explicitly, not stripped blindly.',
         '- Exact 1,007 logical column names, raw field names and every column\'s coverage/missingness are saved in [mm04.json](source_diagnostics/mm04.json) and [mm04_columns.csv](source_diagnostics/mm04_columns.csv).',
         '- Date-column bounds: **2013-05-08 to 2025-09-15**, 3,108 unique dates. Zero duplicate date rows and zero duplicate `(security, field)` columns, hence zero repeated `(date, security, field)` keys in the parsed wide table.', '',
         'First/last meaningful rows (selected value columns; all are numeric where shown):', '',
         mdtable(['Date label','A open','A close','AAPL open','AAPL close','Numeric cells / 1,006'],
                 [[r['date'],*r['first_three_securities_values'][:4],r['numeric_values']] for r in mm['first_meaningful_rows']+mm['last_meaningful_rows']]), '',
         f'Missingness across {3108*1006:,} value cells: **{mm["blank_values"]:,} blanks**, **1,320 `#N/A N/A` cells**, and **{mm["numeric_values"]:,} finite numeric values**. There are no zero or negative numeric values. AAPL and MSFT each have all 3,108 numeric observations for both fields; that does not independently certify date alignment.', '',
         '**Units/adjustments remain ambiguous.** The catalog says `units=unknown`, `adjustment=unknown`. Labels identify auction volume but do not explicitly specify shares, lots, scaling or adjustment. There are 700 fractional values (350 in each field); for example IRM open `5950.4147` and close `53964.4382` on the 2013-05-08 row. Do not coerce to integer or assume unadjusted shares. No imbalance, buy/sell side, indicative-price, NOII or paired-share field exists in the parsed header.', '',
         '**2010 discrepancy:** every row and every date-like cell was scanned. There are no observation dates before 2013-05-08, no extra data blocks, and no non-date rows after the field header. The only earlier date anywhere is `1/1/2010` in the start-date preamble. Thus the filename/preamble record an earlier requested start, while actual delivered rows start in 2013. Why earlier observations were not delivered is not established by this file.', '',
         '**Security/date alignment concern:** ABNB has 1,195 numeric rows under the shared date labels 2013-05-08 through 2018-02-02, then 1,913 blanks per field. COIN has 1,111 numeric rows under 2013-05-08 through 2017-10-03, then 1,997 blanks per field. The local First Rate Data ticker listing starts ABNB at 2020-12-10 and COIN at 2021-04-14. These independent local records conflict with a literal common-date interpretation. This is consistent with a possible export/alignment problem but does not prove its cause; do not repair, shift, or use the broad auction panel until original per-security dates are verified. Missing cells cannot simply be read as an unbalanced calendar panel.', '',
         '## Intraday pilot', '',
         'Local format metadata was found in `intraday_data/_documentation/.archive/stock.txt` and `etf.txt`. It specifies **timestamp, open, high, low, close, volume**, comma-separated and headerless; **US Eastern Time**, **bar-start labels**, and volume in **individual shares**. A 09:30 bar covers 09:30:00–09:30:59. Raw timestamp strings have no timezone offset; no localization or DST conversion was applied. Exact metadata excerpts and selected local ticker-listing dates are in [local_metadata.json](source_diagnostics/local_metadata.json).', '',
         'The notes describe unadjusted, split-adjusted and split+dividend-adjusted variants. The selected filenames identify the last variant; precise adjustment factors and the relationship between adjusted prices, volume and official auction quantities still require verification.', '',
         mdtable(['Symbol / exact inventory ID','Relative physical path','Bytes','Rows','First timestamp','Last timestamp'],
                 [[p['symbol']+' / '+next(r['id'] for r in search['pilot_records'] if r['path']==p['relative_path']), '`'+p['relative_path']+'`',f'{p["size_bytes"]:,}',f'{p["counts"]["total_rows"]:,}',p['min_timestamp'],p['max_timestamp']] for p in pilots]), '',
         'Each file has six fields on every row and timestamp format `YYYY-MM-DD HH:MM:SS`. All rows parse, all timestamps are minute-aligned and sorted, and all OHLCV values are finite numeric. OHLC are floating-point prices; volume is numeric and must not be forced to integer: SPY has 1,280 fractional-volume rows and MSFT has 1,127, while AAPL volume is integer-valued throughout. This requires adjustment/units review despite the documentation describing individual shares; the cause is not established. Each file has 6,541 observed dates. The inventory itself says frequency `unknown` and supplies no start/end coverage; the one-minute grid is verified from contents and local format notes.', '',
         mdtable(['Symbol','Duplicate timestamps','Malformed width/timestamp/OHLCV','OHLC violations','Zero volume','Fractional volume','Negative volume / nonpositive prices'],
                 [[p['symbol'],p['counts']['duplicate_timestamps'],'0 / 0 / 0',p['counts']['ohlc_consistency_violations'],p['counts']['zero_volume_observations'],p['numeric_integrality_by_field']['volume'].get('noninteger',0),'0 / 0'] for p in pilots]), '',
         'OHLC consistency check: `low ≤ open ≤ high`, `low ≤ close ≤ high`, and `low ≤ high`. No offending rows were found. Zero-volume rows contradict the notes\' claim that such bars are omitted; they are retained and flagged, not discarded or filled.', '',
         'Clock-window coverage over all 6,541 observed dates per file:', '',
         mdtable(['Symbol','09:30 present','09:31 present','09:30–09:35 all 6','15:30–15:59 all 30','15:59 present','16:00 present','16:01 present'],
                 [[p['symbol'],p['key_label_date_counts']['has_0930'],p['key_label_date_counts']['has_0931'],p['window_complete_date_counts']['0930_0935'],p['window_complete_date_counts']['1530_1559'],p['key_label_date_counts']['has_1559'],p['key_label_date_counts']['has_1600'],p['key_label_date_counts']['has_1601']] for p in pilots]), '',
         'The documented bar-start convention makes 15:30–15:59 the 30 clock minutes before 16:00; 16:00 is a separate following bar. Presence of a 16:00 bar does **not** establish that its close equals the official auction print. Likewise the 09:30 bar is not itself proof of the official opening auction price. Both 15:30–15:59 and 15:31–16:00 diagnostics are saved for transparency; no research convention or return definition has been selected.', '',
         'Next-observed-date opening checks (6,540 consecutive observed-date pairs per symbol):', '',
         mdtable(['Symbol','Next observed date has 09:30','Next observed date has 09:31','Pairs without next-date 09:30'],
                 [[p['symbol'],p['next_observed_date_with_0930_count'],p['next_observed_date_with_0931_count'],p['date_pair_count']-p['next_observed_date_with_0930_count']] for p in pilots]), '',
         'Next observed date is a diagnostic link, not a certified next exchange session. All three files share calendar gaps of 1 day (5,117 pairs), 2 days (66), 3 days (1,183), 4 days (171), 5 days (2), and 7 days (1). No holiday, early-close, halt or expected-session calendar was imposed; entirely absent sessions therefore cannot yet be classified.', '',
         'Observed gap patterns:', '',
         '- SPY often lacks early opening labels in the oldest data: 145 observed dates lack only 09:30 within 09:30–09:35; 127 lack 09:30 and 09:31. The first date starts at 09:31; 2000-01-04 starts at 09:33. Do not silently substitute a later bar as the open.',
         '- Partial late windows include SPY 2000-01-12 missing 15:32; AAPL 2000-04-07 missing 15:56–15:59; MSFT 2004-04-13 missing 15:30–15:34. These are observed absent labels, not attributed causes.',
         '- Entire 15:30–15:59 windows are absent on 18 SPY dates, 17 AAPL dates, and 21 MSFT dates. Some sparse late windows occur on dates such as 2007-11-23 and 2007-12-24; early-close/calendar explanations must be checked before flagging missing regular trading.',
         '- Opening-window gaps also occur in recent data, for example AAPL and MSFT on 2020-03-16 lack 09:31–09:35. No cause was assigned without a local event/calendar source.', '',
         'The documentation says zero-trade minutes are omitted, but that rule alone cannot explain every absence or the observed zero-volume rows. Exact daily absent-label lists, first/last timestamps, date links and minute-label counts are saved for each symbol in `source_diagnostics/*_clock_windows.csv` and `*_minute_label_counts.csv`. No missing minutes were filled.', '',
         'Zero-volume follow-up:', '',
         mdtable(['Symbol','First zero-volume timestamp','Last zero-volume timestamp','Zeros 09:30–09:35','Zeros 15:30–15:59','Zeros at 16:00'],
                 [[s,z['first_zero_volume_timestamp'],z['last_zero_volume_timestamp'],z['zero_volume_in_clock_windows'].get('0930_0935',0),z['zero_volume_in_clock_windows'].get('1530_1559',0),z['zero_volume_in_clock_windows'].get('1600',0)] for s,z in zero.items()]), '',
         'Full row counts, diagnostic definitions, first/last OHLCV excerpts and opening/closing examples are in [spy.json](source_diagnostics/spy.json), [aapl.json](source_diagnostics/aapl.json), and [msft.json](source_diagnostics/msft.json).', '',
         '## Sufficiency and next validation step', '',
         '**Reversal-only:** yes, local minute data are sufficient to develop a small bar-based reversal pilot without obtaining more price bars. They are not yet certified for an exact official-closing-print to official-opening-print test. Confirm auction-print inclusion/bar labeling across history, adjustment treatment, calendar/early-close rules and the zero-volume discrepancies before constructing research variables. No full-stock-universe sufficiency claim follows from a three-symbol pilot.', '',
         '**Auction-volume moderation:** local open/close volume fields exist, but the full panel is not ready for research use until security/date alignment and units/adjustments are resolved. AAPL/MSFT complete columns are encouraging, not proof of correctness. SPY is not among the 503 MM-04 security labels.', '',
         '**Full auction-imbalance mechanism:** a documented historical signed closing-auction imbalance source would still need to be obtained or located, with security ID, dated dissemination timestamp, buy/sell sign or side, imbalance size and units, auction type, and field/exchange definitions. NOII or paired shares must not be substituted without verifying meaning and coverage. Verify Bloomberg availability and entitlement rather than assume a historical field exists. Official auction prices may also be needed for the exact-print version. For an S&P 500 panel, obtain/locate point-in-time membership entry/exit dates and stable identifier mappings; neither the 503 export labels nor AP15 supplies verified membership history.', '',
         'Recommended next step: review MM-04\'s original export with its data owner to recover/verify per-security dates and field units, then reconcile the three minute series against a documented local trading calendar and a small set of official auction-price records. Keep decisions about session/print definitions separate from results. Do not shift rows, fill gaps or select a specification at this checkpoint.', '',
         '## Reproducibility and scope', '',
         '`scripts/validate_sources.py` reproduces the inventory, MM-04 and complete three-file pilot scans using the standard library. Additional focused read-only checks produced `local_metadata.json`, `mm04_additional.json`, `constituent_candidate.json` and `zero_volume_review.json`. `scripts/write_validation_report.py` renders this report and the catalog annex from the saved diagnostics.', '',
         'All diagnostic writes are under this repository. No provider files were copied or changed; no packages or data were downloaded; no external Bloomberg access, regressions, final research variables, or model outputs were created.', '']
(BASE/'reports'/'source_validation_checkpoint.md').write_text('\n'.join(lines), encoding='utf-8')
print('Wrote checkpoint and catalog annex')
