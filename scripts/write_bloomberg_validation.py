"""Write aggregate-only delivery reports and append provenance manifest rows."""
import csv,json
from pathlib import Path
from import_validate_bloomberg import ROOT,DIAG,write_csv

s=json.loads((DIAG/'summary.json').read_text());blocks=list(csv.DictReader((DIAG/'block_reconciliation.csv').open()))
audit=json.loads((DIAG/'workbook_audit.json').read_text());r=ROOT/'reports'
mm_path=DIAG/'mm04_summary.json';mm=json.loads(mm_path.read_text()) if mm_path.exists() else None
intro='''# Bloomberg import validation

The two user-delivered workbooks were parsed offline as ZIP/XML, without Excel,
formula execution, refresh or external connections. Raw SHA256 checksums were
verified again after import. Provider files were read-only. No returns, analysis
panel, models or predictive relationships were constructed. Reproduce with
`.venv/Scripts/python.exe scripts/import_validate_bloomberg.py`, then (with the
mounted RISKLAB_DATA_ROOT available) `scripts/compare_bloomberg_mm04.py`, then
`scripts/write_bloomberg_validation.py` using the same Python executable.

## Delivery provenance

`manifests/bloomberg_source_log.csv` records both filenames, sizes, SHA256,
sheet ranges and document properties. Actual retrieval time is UNKNOWN; saved
document creation/modification times are not retrieval timestamps. Literal
saved request formulas establish identifiers, fields and requested dates only.
Unspecified defaults, DPDF settings, units and adjustment settings remain UNKNOWN.
The full cell/formula inventory is local in ignored diagnostics.

## Worksheet inventory

| Workbook | Sheet | Declared range | Stored cells | Formula anchors | Error cells |
| --- | --- | --- | ---: | ---: | ---: |
'''
for a in audit['sheets']:intro+=f"| {'Values' if 'Values' in a['file'] else 'Formulas'} | {a['sheet']} | {a['range']} | {a['stored_cells']} | {a['formula_cells']} | {a['error_cells']} |\n"
intro+='''
Array-formula anchors and their complete output blocks are treated as formula
results, including spilled cells without their own formula tag. They are used
only for reconciliation. Genuine static copies in the Values workbook are
imported once. Every copied cell exactly matches its corresponding cached cell
in BOTH workbooks. Matching copies establish extraction fidelity, not independent
verification of Bloomberg source correctness. Date serials are decoded using
the workbook's 1900 date system in known date columns; raw serials are preserved.

## Imported block provenance

| Worksheet | Symbol | Static copy imported | Formula/cached block excluded | Rows |
| --- | --- | --- | --- | ---: |
'''
for b in blocks:intro+=f"| {b['sheet']} | {b['symbol']} | {b['static_range']} | {b['source_range']} | {b['rows']} |\n"
intro+='''| SP500_membership | SPX Index request | D1:E503 | A1:B503 | 503 |

`field_definitions!A1:D8` is delivery-authored metadata, not observations.
Its descriptions do not substitute for verified FLDS definitions or returned
bulk-field column headers. All other populated observation ranges are accounted
for above; no duplicate copy is counted twice. The intentionally named worksheet
`action_volume` contains auction volume, not corporate actions.

Ignored interim tables: `daily_volume.csv`, `closing_auction_volume.csv`,
`price_pilot.csv`, `corporate_actions.csv`, `dividends.csv`, `stock_splits.csv`,
and `membership_reference.csv` under `data/interim/bloomberg/`. Each retains
original identifier, raw date/value, source range and delivery checksum where
applicable. Missing values are not filled. Bulk dates retain positional names
because actual returned column headers are absent. Membership requested-as-of
is request provenance, not a returned effective date.

## Price pilot

SPY/AAPL/MSFT US Equity each have 10 dates, December 1–12, 2025, and fields
PX_OFFICIAL_CLOSE, PX_LAST, PX_OPEN: 90 numeric, positive field observations,
zero duplicate keys, missing/error values or non-session dates. All 30 comparable
PX_LAST/PX_OFFICIAL_CLOSE pairs agree exactly. None is an early-close session.
This is not the previously planned corporate-action pilot and provides no
split/dividend-date endpoint validation or proof of full-history equivalence.
The supplied notes describe PX_OFFICIAL_CLOSE as primary-exchange official close;
they do not independently establish auction execution inclusion. PX_OPEN has no
distinct opening-auction execution definition here. Exact close/open choices and
adjustment compatibility with RiskLab minute prices remain unresolved. No
nominal/adjusted price series were combined.

## Corporate actions

DVD_HIST_ALL requests specify DVD_START_DT=20100101 and DVD_END_DT=20260102.
Four positional dates, numeric event value, frequency and explicit event type
are present; no returned column headers document their order. Column 2 is a
candidate ex/effective date, strongly corroborated by local event-date matches,
but must be verified rather than promoted silently. Declaration, record and
payment dates are preserved separately without assuming column labels.

| Symbol | Events | Types | Candidate ex/effective coverage | Local dates matched | Local-only dates | Newly supplied dates |
| --- | ---: | --- | --- | ---: | ---: | ---: |
'''
for sym,a in s['corporate_actions'].items():intro+=f"| {sym} | {a['rows']} | {', '.join(f'{v} {k}' for k,v in a['types'].items())} | {a['start']} to {a['end']} | {a['shared_dates']}/{a['local_candidate_dates']} | {len(a['local_only_dates'])} | {a['new_only_date_count']} |\n"
intro+='''
No duplicate candidate date/type keys, missing or nonpositive event values occur.
AAPL Stock Split rows give candidate effective dates 2014-06-09 and 2020-08-31,
with numeric values 7 and 4. No SPY/MSFT split rows are supplied in this interval;
the known 2003 MSFT split is outside the request. SPY supplies 64 distribution
events across 16 years, including the previously checked 2020-03-20 date.
AAPL/MSFT add November 2025 candidate ex-dates, SPY adds December 2025.
Coverage now looks substantially stronger, but equal local matches and quarterly
counts cannot establish absence of every omitted special event. Confirm returned
date-column order, split-ratio direction, cash-amount adjustment basis, and scope
(special distributions included) before freezing a corporate-action exclusion
policy. The action decision remains unresolved; no research exclusions are made.

## Membership

INDX_MWEIGHT_HIST was requested for SPX Index with END_DATE_OVERRIDE=20251231.
There are 503 unique exchange-qualified identifiers, no duplicate identifiers,
and no returned dates, entry dates, exit dates or stable security identifiers.
All 503 weights are the same tiny negative value near zero. They are suspicious
and unusable as verified weights; no normalization or repair was applied.
This is a single requested-as-of snapshot of unverified date effectiveness,
not historical point-in-time membership or effective membership history.

## MM-04 reconciliation

'''
if mm:
    for sym,a in mm['comparisons'].items():intro+=f"- {sym}: {a['dated_numeric_rows']} dated numeric MM-04 closing-auction observations; {a['same_date_equal']} equal same-date pairs; {a['unique_value_matches']} values uniquely match a new dated observation. First MM-04 date {a['first_mm04_date']}; its value maps to new date(s) {', '.join(a['first_value_new_dates']) or 'none'}. First 20 values identical in sequence: {a['first_20_sequence_equal']}. Index-offset counts: {a['new_row_index_minus_mm04_row_index']}.\n"
else:intro+='Read-only mounted-source comparison pending; do not claim reconciliation.\n'
intro+='''
MM-04 stable ID is RL-ED340E2FF91E. Both sources request AAPL/MSFT UW Equity
and OFFICIAL_CLOSE_AUCTION_VOLUME. The comparison uses the explicit closing field,
not the adjacent OFFICIAL_OPEN_AUCTION_VOLUME field. Equal sequences under
different shared date labels support date misalignment for matching observations;
they do not certify all unmatched values, adjustments or full mappings. Full
same-date/value-match diagnostics are ignored local files. MM-04 has not been
shifted, repaired or merged. New per-security dates are preferable for pilot
provenance, conditional on their own unresolved quality/metadata checks.
'''
(r/'bloomberg_import_validation.md').write_text(intro,encoding='utf-8')
coverage='''# Bloomberg data coverage

Coverage uses the previously validated 4,024-session US equity exchange calendar
for 2010–2025, including early closes and exceptional closures. Dates preceding
the first delivered auction observation are outside observed field coverage,
not labeled interior missing days. This does not prove Bloomberg has no earlier
history for another field or identifier.

| Series | Symbol | Observations | Start | End | Interior missing sessions | Sessions outside delivered coverage | Duplicate dates | Missing/errors | Zero | Negative |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
'''
for table in ['daily_volume','closing_auction_volume']:
    for sym,a in s[table].items():coverage+=f"| {table} | {sym} | {a['rows']} | {a['start']} | {a['end']} | {a['missing_inside_coverage']} | {a['outside_field_coverage']} | {a['duplicate_dates']} | {a['nonnumeric_or_missing']} | {a['zero']} | {a['negative']} |\n"
coverage+='''
All delivered dates are calendar sessions. Daily PX_VOLUME uses SPY/AAPL/MSFT US
Equity (composite identifiers). OFFICIAL_CLOSE_AUCTION_VOLUME uses SPY UP Equity
and AAPL/MSFT UW Equity. Share units, split adjustments, venue/trade filters,
and daily aggregation boundaries are not documented by saved request settings.
Different identifiers may be intentional (primary-venue auction / composite day),
but require definition review before interpreting their ratio as participation.

The diagnostic auction/daily ratio has zero missing or nonpositive denominators,
zero negative ratios and zero ratios above one for all three symbols. These
arithmetic checks do not establish unit, adjustment or venue compatibility. The
observation-level diagnostic is ignored and is not an analysis variable.

## SPY constant block

Exactly 87 of 88 expected sessions from 2016-05-10 through 2016-09-13 have
auction volume 100; 2016-09-07 is the sole intervening non-100 session. These values are identical in static copies and saved formula
caches in both deliveries, with nonmissing daily denominators. It is not an
import conversion or duplicate-block artifact. AAPL/MSFT have no auction values
equal to 100. SPY's most frequent repeated value occurs on these 87 dates; AAPL's maximum
value frequency is 2, MSFT's is 1. The constant SPY block is suspicious but not
declared valid or invalid: confirm vendor source/units/status before use. Do not
rescale, replace with MM-04, delete silently or treat bounded ratios as validation.

## Potential period versus approved sample

Daily volumes cover 2010-01-04–2025-12-31. Auction/daily raw overlap begins
2013-05-08 for SPY (3,183 sessions) and 2013-05-02 for AAPL/MSFT (3,187 each).
A balanced three-security volume overlap would have 3,183 sessions starting
2013-05-08; the 87 suspect SPY sessions remain flagged, not automatically removed.
If independently invalidated and excluded by an approved policy, that arithmetic
count would be 3,096; it is not a chosen sample. No effective research sample is
approved yet: endpoint prices, adjustment compatibility, event treatment and
required next-session observations still control feasibility. In particular,
the final 2025 close needs the 2026-01-02 open and must be checked against minute
coverage when construction is authorized. No panel join or return was built.
'''
(r/'bloomberg_data_coverage.md').write_text(coverage,encoding='utf-8')
issues='''# Bloomberg unresolved issues

The six frozen methodological decisions are preserved verbatim. None of the four
unresolved choices is resolved by this delivery, so design_decisions.md remains
unchanged. Updated evidence is recorded here rather than rewriting frozen rules.

| Item | Classification | Required next evidence |
| --- | --- | --- |
| Daily volume observations | AVAILABLE; METADATA REVIEW for ratio use | PX_VOLUME units, split adjustment, composite venue/trade and day boundary definitions |
| AAPL/MSFT closing auction volume | PARTIAL; numerically clean | OFFICIAL_CLOSE_AUCTION_VOLUME share units/adjustments and primary-venue definition, compatible daily denominator |
| SPY closing auction volume | PARTIAL | Same definitions plus source-status explanation for 87-session 2016 value-100 block |
| Price pilot | AVAILABLE validation only | Targeted action/early-close checks and documented auction-versus-last-trade endpoint definitions |
| Corporate-action calendar | PARTIAL; improved all three | DVD_HIST_ALL returned column headers, column-2 ex/effective date confirmation, event scope and completeness, cash/split basis |
| Historical membership | MISSING as usable history; supplied snapshot METADATA REVIEW | Date-effective history with stable identifiers if expanding to historical S&P sample; investigate constant negative weights |
| Signed imbalance | MISSING | Not required to test the stated auction-volume attenuation mechanism; required only for an explicitly added signed-imbalance mechanism |

## Required for the existing research question

1. Resolve the price measurement definition before construction: supervisor
   approval of clearly labeled minute-price proxies, or verified auction execution
   price fields and compatible history if official prints remain the target.
   PX_OPEN alone does not document an opening-auction execution price.
2. Verify local minute adjustment behavior and cross-session action handling.
   The new action dates improve feasibility but do not prove minute factors or
   justify mixing Bloomberg nominal endpoints with adjusted minutes. Confirm bulk
   schema and event coverage before adopting a pre-specified action exclusion policy.
3. Verify numerator/denominator definitions and the SPY constant block. Metadata
   confirmation is essential; another full duplicate download is not yet justified.
   If the block is a vendor defect, obtain a correction or approve an explicit
   limitation/exclusion policy before analysis.

## Optional or conditional requests

- No blanket new daily-volume or auction-volume request is needed: existing dated
  delivery coverage is complete within its observed ranges.
- A small replacement price pilot covering the originally planned action dates
  and early close would validate endpoint/adjustment definitions; it cannot alone
  certify full-history auction identity. Full auction-price history becomes
  required only if that endpoint definition is selected.
- Historical S&P membership is required for a historical index cross-section,
  not for the fixed three-security pilot or the core conceptual question.
- Signed imbalance, imbalance side, NOII and paired shares are extensions, not
  substitutes for volume or each other. They are not essential to the present
  volume-absorption hypothesis; require exact historical definitions if added.

## Readiness

Extraction is reproducible without Terminal access; raw files are unchanged and
licensed observations remain ignored. We can prepare further source-validation
work, but cannot yet call a three-security research panel defensible. Resolve
endpoint/adjustment choices and volume definitions first. Coverage and equality
checks have not been used to choose specifications or inspect predictive results.
'''
(r/'bloomberg_unresolved_issues.md').write_text(issues,encoding='utf-8')
manifest=ROOT/'data_manifest.csv'
rows=list(csv.DictReader(manifest.open(encoding='utf-8-sig')));fields=list(rows[0])
rows=[x for x in rows if not x['risklab_id'].startswith('PROJECT2-BBG-')]
for source in audit['sources']:
    rows.append(dict(zip(fields,[source['source_id'],source['relative_path'],'PROJECT_ROOT','Bloomberg user delivery','immutable raw workbook','SHA256 verified; offline static/cached reconciliation','no'])))
for name in ['daily_volume','closing_auction_volume','price_pilot','corporate_actions','dividends','stock_splits','membership_reference']:
    rows.append(dict(zip(fields,['PROJECT2-BBG-INTERIM-'+name.upper(),'data/interim/bloomberg/'+name+'.csv','PROJECT_ROOT','Bloomberg user delivery','static-copy normalized '+name,'source checksum and cells retained; see Bloomberg validation reports','no'])))
write_csv(manifest,rows,fields)
print('Three aggregate reports written; provenance manifest updated. Design unchanged.')
