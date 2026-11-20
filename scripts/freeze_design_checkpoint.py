"""Apply the user's ex-ante freeze and supplied FLDS evidence, offline only.

No provider reads, Bloomberg connections, formula execution or research variables.
Idempotent: preserves prior field candidates and updates/adds supplied evidence.
"""
import csv
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
MAN=BASE/'manifests'
REPORTS=BASE/'reports'
RECORDED='2026-10-27'
SOURCE='User-provided manually observed Bloomberg FLDS/reference evidence; pasted request recorded '+RECORDED+'; observation date not supplied; not independently rechecked by agent'


def writecsv(path,rows,fields=None):
    fields=fields or list(rows[0])
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)


design='''# Project 2 design decisions

Ex-ante freeze recorded 2026-10-27, explicitly instructed by the user before
research results. **Six choices are FROZEN; four source-dependent choices remain
UNRESOLVED.** No returns, final analysis panel, models or predictive relationships
have been constructed or inspected in this step.

| Decision | Status | Fixed rule or remaining source question |
| --- | --- | --- |
| Primary closing window | FROZEN | 10 minutes before the calendar's scheduled close: 15:50–15:59 on a normal 16:00-close session; 12:50–12:59 on a 13:00-close session. |
| Robustness closing windows | FROZEN | 5, 15 and 30 minutes only as pre-specified robustness windows; none may replace the 10-minute primary based on significance, effect size, model performance or appearance. |
| Primary outcome horizon | FROZEN | Close-to-next-open, following the research question. Close-to-next-close is reserved for a pre-specified robustness/alternative-horizon analysis. Neither is constructed yet. |
| Early-close sessions | FROZEN | Include valid sessions using the same calendar-relative construction. Pre-specify a robustness analysis excluding early closes. Missing 15:xx labels after a 13:00 close are not missing core-session bars. |
| Incomplete closing windows | FROZEN | Exclude the security-session from that window specification if any required bar is absent or invalid. No interpolation, fill, shortening or neighboring-minute substitution. Record every exclusion. |
| Missing next-session 09:30 observation | FROZEN | Exclude if the required next-calendar-session 09:30 bar is absent or invalid. Never substitute 09:31, the first available bar, a previous close or another proxy. |
| Exact close price | UNRESOLVED | Final pre-close minute close as an explicitly labeled continuous-trading proxy, a verified historical official closing-auction execution price, or another documented matching endpoint. A 16:00 OHLC bar is not automatically an auction print. |
| Exact next-open price | UNRESOLVED | Open of the next valid session's 09:30 minute bar as an explicitly labeled proxy versus a verified historical official opening-auction execution price. Bar presence is not proof of auction identity. |
| Adjustment convention | UNRESOLVED | Only split+dividend-labeled minute files were identified locally. Split-neutral treatment is necessary; split-only is conceptually preferable for pure price pressure, but dividend-crossing policy, factors and endpoint scale compatibility remain unresolved. Do not reconstruct missing variants. |
| Final cross-sectional universe | UNRESOLVED | Pilot remains SPY/AAPL/MSFT. A historical large-cap/S&P sample requires point-in-time membership and stable identifiers; current constituents or MM-04 columns alone do not define it. |

## Rationale and timing boundaries

Ten minutes is fixed ex ante because the question concerns pressure in the final
minutes of trading. Coverage did not select the horizon: all four tested lengths
had identical 100% label coverage in the three-symbol 2010–2025 pilot. Do not
change the primary horizon after predictive results are inspected.

For scheduled close C, an L-minute window requires bar-start labels C-L through
C-1. Candidate signal endpoints are provisionally the open of the first required
bar and the close of the final pre-close bar. **Freezing the window does not
freeze those endpoint prices.** The documented bar-start convention identifies
the represented interval, not official auction-print inclusion.

Use the documented exchange calendar and its next valid session, not consecutive
dates observed in a file. Preserve raw labels. On early closes shift the entire
window to the scheduled close; do not search for normal-session late labels.
Future exclusions must retain symbol, anchor session, window, absent/invalid
required label, next expected session when relevant, and reason. No exclusion
panel or return series is created now.

## Adjustment evidence retained

The [adjustment audit](reports/adjustment_comparison.md) identified only
split-and-dividend-adjusted-labeled minute files for SPY, AAPL and MSFT. It did not
identify local unadjusted or split-only minute counterparts or certify the exact
file-specific price/volume adjustment factors.

Within-day percentage measurement would be invariant to a date-constant
multiplicative adjustment before rounding, but factor constancy and compatibility
with any official endpoint still require source verification. Across splits,
share units must be consistent. Dividend-crossing intervals require an explicit
policy; no exclusion or dividend-neutralization policy is frozen here. Existing
combined-adjusted prices may be usable only after their behavior is established.
Do not mix nominal Bloomberg prices and adjusted minute prices without verified
scale compatibility, and do not reconstruct a split-only series.

CE-08 corroborates sampled split dates/ratios; CE-05/06 contain selected dividend
ex-dates but no pilot cash amounts; CE-102 is change-only. Review already-owned
CE-104/sp500_histories event columns and provenance before requesting overlapping
corporate-action history.

## Design-freeze statement and next work

The six choices above are now frozen by explicit user instruction, independently
of research results. The four unresolved choices depend on source definitions
and data availability. Resolve them using metadata and measurement evidence,
without predictive results. The project is **not awaiting supervisor response**.

Next is the [minimal Bloomberg Terminal metadata checklist](reports/bloomberg_terminal_checklist.md).
Historical auction-imbalance availability and definition also remain unresolved.
Only metadata verification is planned initially. No Bloomberg production
retrieval, formula execution, provider modification, return calculation or model
estimation is authorized in this step.
'''
(BASE/'design_decisions.md').write_text(design,encoding='utf-8')

path=MAN/'bloomberg_pilot_spec.csv'
with path.open(encoding='utf-8',newline='') as f:
    reader=csv.DictReader(f);fields=list(reader.fieldnames);rows=list(reader)
extras=['evidence_source','evidence_recorded_date','evidence_observation_date','metadata_verification_status','current_value_availability','historical_value_availability','preference','reference_formula_example']
for name in extras:
    if name not in fields:fields.append(name)
for r in rows:
    for name in extras:r.setdefault(name,'')
lookup={r['item_id']:r for r in rows}
scope='AAPL US Equity|MSFT US Equity|SPY US Equity'


def supplied(item,mnemonic,description,classification,*,history=False,formula='',units='Not supplied; verify only if later required',function='BDP',note='Already documented; do not repeat definition/current-availability checks in next session'):
    r=lookup.get(item)
    if r is None:
        r={k:'' for k in fields};rows.append(r);lookup[item]=r
    r.update(item_id=item,bloomberg_mnemonic=mnemonic,mnemonic_status='USER_OBSERVED_BLOOMBERG_DOCUMENTATION',
             bloomberg_field_description=description,intended_construct='Optional quote reference; never a primary endpoint or mechanism measure' if mnemonic in ['PX_BID','PX_ASK'] else 'Instrument/reference validation only',
             applicable_security_type_exchange='Equities definition supplied by user; per-security outputs not supplied' if mnemonic in ['PX_BID','PX_ASK'] else 'Reference field; definition supplied by user; per-security values not mapped',
             security_scope=scope,historical_availability='User reports current and historical availability; security/date coverage and frequency not established' if history else 'Current availability reported by user; historical availability not supplied',
             frequency='Current quote; historical frequency not supplied' if history else 'Current reference value',units=units,currency='Not supplied; no field/value mapping inferred',
             adjustment_behavior='Not supplied; unresolved, not relevant to current metadata-only reference record',appropriate_function=function,
             function_status='User-supplied BDP reference example; not executed' if formula else 'Proposed BDP current / BDH historical route; no request executed',
             construct_match_status='REFERENCE ONLY; not an auction execution price or signed imbalance',classification=classification,
             classification_condition='No bid/ask production request unless a later pre-specified spread/liquidity robustness requires it' if history else 'Small reference validation only; no execution authorized now',
             pilot_stage='USER_METADATA_RECORDED_NO_RETRIEVAL',date_set_id='PILOT10' if history else 'CURRENT_REFERENCE_ONLY',
             local_overlap_action='Use supplied evidence; no new data access',terminal_questions=note,retrieval_authorized_now='NO; metadata update only',
             evidence_source=SOURCE,evidence_recorded_date=RECORDED,evidence_observation_date='',metadata_verification_status='USER_OBSERVED_DEFINITION_AND_AVAILABILITY; not independently checked',
             current_value_availability='AVAILABLE per user-observed Bloomberg API flag',historical_value_availability='AVAILABLE per user-observed Bloomberg API flag; coverage unspecified' if history else 'NOT REPORTED; do not infer',
             preference='REFERENCE_ONLY_NOT_A_PRIMARY_ENDPOINT',reference_formula_example=formula)
    return r

supplied('bid_reference','PX_BID','If the market is closed, it returns the last bid from the last day the market was open. If the market is open and there is no bid in the market, it returns N.A.','OPTIONAL / REFERENCE VALIDATION ONLY',history=True,function='BDP for current; BDH for historical subject to frequency/coverage verification',note='Do not spend priority terminal time on this field; verify outstanding quote units/adjustments/history detail only if pre-specified spread/liquidity robustness later requires it.')
supplied('ask_reference','PX_ASK','If the market is closed, it returns the last ask from the last day the market was open. If the market is open and there is no ask in the market, it returns N.A.','OPTIONAL / REFERENCE VALIDATION ONLY',history=True,function='BDP for current; BDH for historical subject to frequency/coverage verification',note='Do not spend priority terminal time on this field; verify outstanding quote units/adjustments/history detail only if pre-specified spread/liquidity robustness later requires it.')
supplied('security_type','SECURITY_TYP','Description of the specific instrument type within its market sector.','USEFUL REFERENCE VALIDATION ONLY',formula='=BDP($A2,"SECURITY_TYP")',units='Descriptive category; actual value not supplied')
supplied('market_sector','MARKET_SECTOR_DES','Market Sector refers to the Bloomberg yellow key assigned to the instrument.','USEFUL REFERENCE VALIDATION ONLY',formula='=BDP($A2,"MARKET_SECTOR_DES")',units='Market-sector description; actual value not supplied')
supplied('primary_exchange_short','EQY_PRIM_EXCH_SHRT','Exchange code for the main exchange on which the security is listed.','USEFUL VALIDATION ONLY',formula='=BDP($A2,"EQY_PRIM_EXCH_SHRT")',units='Exchange code; actual code/value not supplied',note='Definition/current availability already supplied. Prefer over generic EQY_PRIM_EXCH for primary-venue reference. Only seek additional historical venue evidence if needed for auction matching.')['preference']='PREFERRED_USER_DOCUMENTED_PRIMARY_EXCHANGE_REFERENCE'
if 'primary_exchange' in lookup:
    lookup['primary_exchange']['preference']='RETAINED_UNVERIFIED_ALTERNATIVE; prefer EQY_PRIM_EXCH_SHRT'
    lookup['primary_exchange']['terminal_questions']='Retained candidate, not user-documented. Do not repeat generic primary-exchange search if EQY_PRIM_EXCH_SHRT satisfies the reference need; historical venue changes remain a separate question.'
    lookup['primary_exchange']['pilot_stage']='RETAINED_ALTERNATIVE_NOT_PRIORITY'
for item in ['daily_open','daily_last','official_open','official_close','close_auction_volume','signed_close_imbalance']:
    lookup[item]['metadata_verification_status']='UNRESOLVED; no definition/history evidence supplied in this update'
for r in rows:r['retrieval_authorized_now']='NO; metadata only; no formulas or retrieval authorized'
writecsv(path,rows,fields)

unmapped=['SS SPDR S&P 500 ETF TRUST-US','USD','US78462F1030','SPY US','78462F103','BBG000BDTBL9']
writecsv(MAN/'bloomberg_unmapped_reference_values.csv',[{'associated_security':'SPY (user association only)','raw_user_value':value,'exact_bloomberg_field':'','mapping_status':'UNMAPPED_REFERENCE_VALUES; confirm exact field/value pairing in saved evidence or terminal','evidence_source':SOURCE} for value in unmapped])
writecsv(MAN/'bloomberg_source_log_template.csv',[],['filename','retrieval_datetime_with_timezone','exact_request','adjustment_settings_including_DPDF','sha256','row_count','value_count','errors_and_NA_responses'])

plan='''# Bloomberg pilot plan — metadata-only next session

Updated 2026-10-27 from explicit user instructions and user-observed Bloomberg
FLDS/reference evidence. No external Bloomberg access or data retrieval occurred.
The observation date of the supplied evidence was not provided; 2026-10-27 is its
recording date here. The agent did not independently reverify it.

## Frozen design and remaining questions

Six choices are FROZEN: primary 10-minute window; robustness 5/15/30-minute
windows; primary close-to-next-open horizon; calendar-relative inclusion of valid
early closes (with exclusion as robustness); complete-window requirement; and no
substitution for missing/invalid next-session 09:30. See
[design_decisions.md](../design_decisions.md).

Exact close price, exact next-open price, adjustment convention and final
cross-sectional universe remain UNRESOLVED because of source definitions and
availability. Historical signed auction-imbalance availability/definition also
remains unresolved. Resolve these without predictive results. The project is not
blocked pending supervisor response.

## Next session: five metadata priorities

Use [bloomberg_terminal_checklist.md](bloomberg_terminal_checklist.md): PX_OPEN,
PX_LAST, distinct official auction execution prices, OFFICIAL_CLOSE_AUCTION_VOLUME,
and historical signed closing imbalance (or magnitude plus matching side).
Do not repeat reference definitions already supplied below. Record unknown
mnemonics as unresolved; do not invent descriptions or infer historical coverage.
BDP current values cannot replace historical observations.

The [field specification](../manifests/bloomberg_pilot_spec.csv) preserves prior
candidates and adds evidence provenance/status columns. Unknown descriptions,
units, currency, adjustment behavior and security/date coverage stay unresolved
unless explicitly supplied. A reported history flag is not proof of coverage on
the pilot dates or of a usable sampling frequency.

## User-provided metadata already recorded

| Field | Supplied definition / API availability | Project role |
| --- | --- | --- |
| PX_BID | Equities: when closed, last bid from the last open day; when open with no bid, N.A. Current and historical values available per user-reported API flags. | OPTIONAL / REFERENCE VALIDATION ONLY; not a primary endpoint or auction-mechanism input. |
| PX_ASK | Equities: when closed, last ask from the last open day; when open with no ask, N.A. Current and historical values available per user-reported API flags. | OPTIONAL / REFERENCE VALIDATION ONLY; no production bid/ask request absent later pre-specified spread/liquidity robustness. |
| SECURITY_TYP | Description of the specific instrument type within its market sector. Current available. | USEFUL REFERENCE VALIDATION ONLY; BDP expected. |
| MARKET_SECTOR_DES | Market Sector refers to the Bloomberg yellow key assigned to the instrument. Current available. | USEFUL REFERENCE VALIDATION ONLY; BDP expected. |
| EQY_PRIM_EXCH_SHRT | Exchange code for the main exchange on which the security is listed. Current available. | USEFUL VALIDATION ONLY; preferred user-documented primary-venue reference, BDP expected. |

The exact supplied definitions are retained in the CSV. EQY_PRIM_EXCH is retained
as an unverified alternative, not silently deleted or elevated to observed status.
No specific reference outputs have been mapped to these definitions.

Reference formulas supplied by the user, **recorded only; do not execute now**:

```excel
=BDP($A2,"SECURITY_TYP")
=BDP($A2,"MARKET_SECTOR_DES")
=BDP($A2,"EQY_PRIM_EXCH_SHRT")
```

## UNMAPPED_REFERENCE_VALUES

Associated with SPY by the user; exact Bloomberg field/value pairings were not
supplied. Preserve each literally and confirm its mapping from saved evidence or
the terminal. Do not assign instrument-name, currency, identifier or ticker labels
solely from appearance.

- `SS SPDR S&P 500 ETF TRUST-US`
- `USD`
- `US78462F1030`
- `SPY US`
- `78462F103`
- `BBG000BDTBL9`

Also saved in [bloomberg_unmapped_reference_values.csv](../manifests/bloomberg_unmapped_reference_values.csv).

## Retained tiny pilot — not authorized for execution

Initial securities remain AAPL US Equity, MSFT US Equity and SPY US Equity.
[The ten-date manifest](../manifests/bloomberg_pilot_dates.csv) is unchanged:
2018-11-23/26; 2020-03-19/20; 2020-08-28/31; 2020-11-05/06;
2024-02-13/14. These span an early close and documented corporate actions; they
were not selected using outcomes. SPX Index is only a membership-metadata context,
not an added price-pilot security.

After metadata verification and a later retrieval instruction, the existing
baseline ceiling remains 3 securities × 10 dates × 2 daily fields = 60 values
(PX_OPEN/PX_LAST). Only if needed, action-pair adjustment checks add at most 32
values. No bid/ask values are added. Do not download duplicate official fields if
PX_OPEN/PX_LAST are proven equivalent, and do not request a continuous multi-year
range merely to select ten dates. Keep nominal and adjusted scales separate.

Primary-test requirements remain conditional on the unresolved endpoint and
universe definitions; PX_OPEN/PX_LAST are validation benchmarks until their
constructs are established. The auction mechanism needs executed volume and a
defined historical signed imbalance; paired shares/indicative constructs remain
distinct optional measures, never automatic substitutes.

Secondary work: corporate-action history only for verified local gaps;
historical S&P membership/effective entry-exit dates; stable identifier mappings.
Local CE-08 supplies sampled split dates/ratios; CE-05/06 contain selected ex-dates
without pilot cash amounts, and CE-102 is change-only. Inspect locally owned
CE-104/sp500_histories event columns/provenance before duplicating them. Do not
spend time on current constituents unless needed to understand historical access.

## Future raw-file checksum and source log

Example only, for a file that actually exists after a future authorized retrieval:

```powershell
Get-FileHash "<raw Bloomberg pilot file>" -Algorithm SHA256
```

Do not execute the placeholder or hard-code a nonexistent raw file. Preserve
filename, retrieval date/time with timezone, exact request, adjustment settings
(including DPDF interaction), SHA256 checksum, row/value counts and errors/N.A.
responses. [bloomberg_source_log_template.csv](../manifests/bloomberg_source_log_template.csv)
is header-only; no retrieval or checksum is fabricated.

**Current authorization is metadata documentation only.** No Bloomberg production
retrieval, BDP formula execution, return calculation, final panel, regression,
predictive inspection or provider modification is authorized.
'''
(REPORTS/'bloomberg_pilot_plan.md').write_text(plan,encoding='utf-8')

checklist='''# Bloomberg Terminal — short metadata checklist

Next session: **metadata verification only**, initially for AAPL US Equity,
MSFT US Equity and SPY US Equity. No production retrieval or formula execution.
Record exact definitions/evidence; do not use predictive results to resolve them.

## Priority 1 — PX_OPEN

- [ ] Capture exact Equities definition and historical-availability flag.
- [ ] Determine whether history is official primary-exchange opening auction,
  first eligible trade, composite open or another convention; check delayed opens.
- [ ] Record adjustment behavior, DPDF interaction and explicit BDH controls.

## Priority 2 — PX_LAST

- [ ] Capture exact Equities definition and historical-availability flag.
- [ ] Determine whether history is official primary-exchange close, consolidated
  last eligible regular-session trade, last trade or another mark.
- [ ] Confirm whether after-hours trades are excluded; record adjustment behavior,
  DPDF interaction and explicit BDH controls.

## Priority 3 — distinct official auction execution prices

- [ ] Search for historical official opening-auction execution price and official
  closing-auction execution price. Do not invent mnemonics if unavailable.
- [ ] For each candidate save mnemonic, exact description, history availability,
  exchange applicability, units/currency, timestamp/session semantics (including
  early closes), and adjustment behavior. Establish whether it duplicates a
  verified PX_OPEN/PX_LAST definition before proposing additional requests.

## Priority 4 — OFFICIAL_CLOSE_AUCTION_VOLUME

- [ ] Verify exact description and history availability; the local-header mnemonic
  alone is not FLDS confirmation.
- [ ] Record shares versus lots/other units, primary-exchange coverage, adjustment
  behavior, coverage dates and early-close handling.

## Priority 5 — historical closing imbalance

- [ ] Find exact signed closing-auction imbalance mnemonic, or unsigned magnitude
  **plus matching buy/sell side**. Record definition, sign convention and units.
- [ ] Record dissemination/cutoff time relative to scheduled close, exchange,
  retention/coverage, revisions and whether history is actually available.
- [ ] Do not substitute executed volume, paired shares, indicative price or generic
  NOII components unless the definition exactly matches the intended signed
  construct. Record absent/live-only history explicitly, not as zero.

For priorities 1–5, verify applicability to each security/primary venue; preserve
the observation date and exact evidence. For price/volume candidates record units,
currency where applicable and available history dates/frequency. For imbalance,
side and magnitude must refer to the same event/time/revision. A history flag is
not proof that all ten pilot dates or 2010–2025 are retained.

## Secondary — only after the five priorities

- [ ] Dividend event history only if local sources remain incomplete; split
  information only for verified local gaps. Check owned event columns first.
- [ ] Historical S&P 500 membership/effective entry-exit dates, stable identifiers
  and supported as-of access. Avoid current constituent lists unless needed to
  understand historical functionality; SPX Index is a metadata context only.
- [ ] Confirm exact field/value mappings for the six SPY
  [UNMAPPED_REFERENCE_VALUES](bloomberg_pilot_plan.md#unmapped_reference_values)
  from saved evidence; do not label them by format.

## Already documented — do not repeat routine lookups

The user supplied PX_BID/PX_ASK Equities definitions and current/history flags;
SECURITY_TYP, MARKET_SECTOR_DES and EQY_PRIM_EXCH_SHRT definitions/current flags;
and the three BDP reference examples. These are recorded in the
[plan](bloomberg_pilot_plan.md) and [specification](../manifests/bloomberg_pilot_spec.csv).
Prefer EQY_PRIM_EXCH_SHRT for primary-venue reference; keep EQY_PRIM_EXCH only as
an unverified alternative. Bid/ask are optional reference validation, not primary
endpoints or mechanism inputs; no production quote request is proposed. Their
remaining units/adjustment/history details matter only if later robustness needs
them. No BDP formula is to be run now.

## Leave the terminal session with

- Exact metadata, recorded date, supported request type (BDH/BDP/BDS), field/history
  limitations and remaining gaps for the five priorities. Update evidence status
  without inventing answers or assuming live values are historical observations.
- No downloaded production data. Later authorized retrievals must retain filename,
  retrieval date/time, exact request, adjustment settings, SHA256, row/value counts
  and errors/N.A. responses; use the [source-log template](../manifests/bloomberg_source_log_template.csv).

Frozen: primary 10 minutes; robustness 5/15/30; close-to-next-open; valid early
closes included relative to the calendar; complete windows; no next-09:30
substitution. Unresolved: exact close/open prices, adjustment convention, final
universe and historical auction-imbalance availability/definition. Resolve source
questions using metadata, not returns, models or predictive relationships.
'''
(REPORTS/'bloomberg_terminal_checklist.md').write_text(checklist,encoding='utf-8')

# Historical reports must not keep claiming that every current choice is unfrozen.
for report in ['pilot_timing_validation.md','adjustment_comparison.md']:
    p=REPORTS/report
    if p.exists():
        text=p.read_text(encoding='utf-8')
        text=text.replace('** All nine research design choices remain **NOT YET FROZEN** in [design_decisions.md](../design_decisions.md).','** Current design status is recorded in [design_decisions.md](../design_decisions.md).')
        text=text.replace('No new substantive research choice can be frozen from these observations. [design_decisions.md](../design_decisions.md) retains all nine research decisions as NOT YET FROZEN, with the adjustment recommendation and evidence gap recorded.','The adjustment audit itself did not identify a verified input convention. The subsequent user-directed ex-ante freeze fixes six choices; exact endpoints, adjustments and final universe remain unresolved in [design_decisions.md](../design_decisions.md).')
        text=text.replace('Supervisor approval is still needed for all nine entries in [design_decisions.md](../design_decisions.md): primary length; close price; next-open price; outcome horizon; early closes; incomplete windows; missing 09:30 policy; adjustments; eventual universe. Coverage alone provides no reason to favor a window.','The user has now frozen six choices ex ante in [design_decisions.md](../design_decisions.md), including a 10-minute primary window independent of coverage. Exact endpoints, adjustment convention and final universe remain source-dependent; no supervisor-response blocker applies.')
        p.write_text(text,encoding='utf-8')
assert len([r for r in rows if r['bloomberg_mnemonic'] in ['PX_BID','PX_ASK','SECURITY_TYP','MARKET_SECTOR_DES','EQY_PRIM_EXCH_SHRT']])==5
assert design.count('| FROZEN |')==6 and design.count('| UNRESOLVED |')==4
print('Applied six frozen / four unresolved choices; updated',len(rows),'field rows and metadata-only terminal checklist.')
# Reapply the subsequent saved local-action assessment when older documents are
# regenerated. This is offline reporting only; it never rescans provider data.
if (REPORTS/'corporate_action_diagnostics'/'coverage_assessment.json').exists():
    import runpy
    runpy.run_path(str(BASE/'scripts'/'report_corporate_action_coverage.py'),run_name='__main__')
