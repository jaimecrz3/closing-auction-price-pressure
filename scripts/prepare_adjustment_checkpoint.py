"""Render adjustment findings and a non-executable Bloomberg FLDS plan.

Reads repository diagnostics only. Contains no Bloomberg connection/download code.
Same-timestamp price/volume differences versus published documentation examples
are measurement checks, not time-series returns or replacement provider data.
"""
import csv
import json
from decimal import Decimal
from pathlib import Path
from collections import Counter
from datetime import datetime

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'reports'/'adjustment_diagnostics'
MAN=BASE/'manifests'
MAN.mkdir(exist_ok=True)


def readcsv(path):
    return list(csv.DictReader(path.open(encoding='utf-8',newline='')))


def writecsv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(v).replace('|','/') for v in row)+' |' for row in rows])


events=readcsv(OUT/'event_cases.csv')
availability=readcsv(OUT/'variant_availability.csv')
raw=readcsv(OUT/'corporate_action_raw_excerpts.csv')
inventory=json.loads((OUT/'variant_inventory.json').read_text())
actions=json.loads((OUT/'local_action_candidates.json').read_text())


def action_date(value):
    if '/' in value:
        return datetime.strptime(value,'%m/%d/%Y').date().isoformat()
    return value[:10]


action_summary=[]
for a in actions:
    dates_in_rows=[action_date(r['Date']) for r in a['pilot_rows']]
    counts=Counter(r['Ticker'].split()[0] for r in a['pilot_rows'])
    action_summary.append({'id':a['id'],'relative_path':a['relative_path'],'pilot_rows':len(dates_in_rows),'pilot_min_date':min(dates_in_rows),'pilot_max_date':max(dates_in_rows),'AAPL_rows':counts['AAPL'],'MSFT_rows':counts['MSFT'],'SPY_rows':counts['SPY'],'full_history_verified':False})
writecsv(OUT/'local_action_summary.csv',action_summary)
corroboration=[]
for e in events:
    hits=[]
    for a in actions:
        for r in a['pilot_rows']:
            if r['Ticker'].split()[0]==e['symbol'] and action_date(r['Date'])==e['event_date']:
                hits.append({'id':a['id'],'raw_date':r['Date'],'event_label':r.get('Description',r.get('Stock Splits',''))})
    corroboration.append({'case_id':e['case_id'],'local_event_date_matches':hits})
(OUT/'event_date_corroboration.json').write_text(json.dumps(corroboration,indent=2),encoding='utf-8')
assert all(r['local_event_date_matches'] for r in corroboration)
# Public provider documentation examples; not local unadjusted/split-only files.
references=[
 {'symbol':'AAPL','timestamp':'2020-08-28 19:59:00','reference_variant':'vendor-published unadjusted example','reference_close':'501.98','reference_volume':'5786'},
 {'symbol':'AAPL','timestamp':'2020-08-28 19:59:00','reference_variant':'vendor-published split-adjusted example','reference_close':'125.495','reference_volume':'23144'},
 {'symbol':'AAPL','timestamp':'2020-11-05 19:59:00','reference_variant':'vendor-published unadjusted example','reference_close':'118.0000','reference_volume':'15203'},
]
comparisons=[]
for r in references:
    match=next(x for x in raw if x['symbol']==r['symbol'] and x['timestamp']==r['timestamp'])
    comparisons.append({**r,'source_url':'https://firstratedata.com/about/price_adjustment','reference_retrieved_date':'2026-10-27','reference_data_vintage':'not specified; published illustrative example','local_close':match['close'],'local_volume':match['volume'],'local_source_line':match['source_line_number'],'local_risklab_id':match['risklab_id'],'local_minus_reference_close':str(Decimal(match['close'])-Decimal(r['reference_close'])),'local_minus_reference_volume':str(Decimal(match['volume'])-Decimal(r['reference_volume'])),'scope':'SAME_TIMESTAMP_DOCUMENTATION_CHECK_ONLY; not a local variant comparison; differences may include later adjustments or corrections; no return'})
writecsv(OUT/'documentation_example_comparison.csv',comparisons)

lines=['# Local adjustment audit and provisional measurement recommendation','',
       'Audit date: 2026-10-27. Scope: SPY/AAPL/MSFT. Provider files were opened read-only. No returns, analysis panel or model results were constructed.','',
       '## Local variants actually identified','',
       f'Searched all {inventory["inventory_rows_scanned"]:,} intraday inventory records for the three stock/ETF symbols and inspected their physical filename matches and intraday top-level directories. Only the following files exist in that catalog/directory scope:', '',
       table(['Symbol','RiskLab ID','Root-relative path'],[[r['symbol'].split('_')[0],r['id'],'`'+r['path']+'`'] for r in inventory['matching_records']]),'',
       '**Unadjusted and split-only minute variants: not identified locally for any of the three symbols.** No IDs or paths are invented for missing variants. [variant_availability.csv](adjustment_diagnostics/variant_availability.csv) records all nine symbol/convention combinations; [variant_inventory.json](adjustment_diagnostics/variant_inventory.json) retains exact records, physical names and local documentation excerpts. This is not a claim about other machines, uncataloged archives or the vendor entitlement.','',
       'Local `stock.txt` and `etf.txt` notes (lines 13–17) define unadjusted as historical traded prices, split-adjusted as split/reverse-split adjusted, and split+dividend-adjusted as adjusted for both. They do not provide file-specific factors or explicitly map suffixes. Thus `adjsplitdiv` is a **documentation-supported convention label**, not proof of this snapshot’s exact factors. Advertised product variants are not evidence that those variants are mounted locally.','',
       'The [provider adjustment page](https://firstratedata.com/about/price_adjustment) describes backward split adjustment and dividend rebasing of prior prices using the last traded price before ex-date, potentially after hours. It says volume is adjusted, although its dividend illustration leaves volume unchanged. This ambiguity prevents assuming a dividend-volume formula. Current documentation also does not certify every detail of the January 2026 local snapshot. The [provider FAQ](https://firstratedata.com/about/FAQ) says adjusted history is recalculated when actions occur, so snapshot vintage matters.','',
       '## Corporate-action raw-row checks','',
       'Events were selected from documented dates, not price behavior. Rows below are exact strings from the only local variant. The previous-session 15:59 row is a diagnostic sample, not a chosen research close. The machine-readable excerpts also contain first/last available rows, 16:00 and 19:59 where present.','',
       table(['Case','Event date','Type / terms','Date evidence'],[[e['case_id'],e['event_date'],e['event_type']+'; '+e['terms'],'[source]('+e['date_source']+')'] for e in events]),'',
       'Apple split dates are supported by its [issuer history](https://investor.apple.com/dividend-history/default.aspx). Microsoft’s [split FAQ](https://www.microsoft.com/en-us/investor/faq.aspx?CollectionId=null) identifies new-price trading on 2003-02-18, and its [dividend announcement](https://news.microsoft.com/source/2023/11/29/microsoft-announces-quarterly-dividend-21/) confirms 2024-02-14. The [SPY issuer notice](https://www.ssga.com/library-content/announcements/etfs/au/20200320-SPY-Distribution-Announcement.pdf) explicitly gives the US ex-date 2020-03-20; Australian payment dates are not substituted. The 2003 MSFT case is outside the 2010–2025 timing pilot and is diagnostic only.','']
for e in events:
    sample=[]
    for role,label in [('previous_session','15:59'),('event_date','09:30'),('next_session','09:30')]:
        r=next(r for r in raw if r['case_id']==e['case_id'] and r['session_role']==role and r['timestamp'][11:16]==label)
        sample.append([role,r['timestamp'],r['source_line_number'],r['open'],r['close'],r['volume']])
    lines += ['### '+e['case_id'],'',table(['Session role','Raw timestamp','Source line','Open','Close','Volume'],sample),'']
lines += [
       '**Observed versus unidentifiable:** the split excerpts stay on broadly comparable adjusted price scales, consistent with split normalization, but market moves and dividend effects cannot be separated from one series. Cross-variant price and volume differences are **not computable locally**. Neither exact continuity corrections, within-day factor constancy, dividend pre/post effects nor volume multipliers are independently identified. The vendor describes retrospective adjustment; a single vintage cannot demonstrate historical revisions. MSFT’s next session after the 2003 split also coincides with its first cash-dividend ex-date, so that three-day check is not a clean split-only experiment.','',
       '### Supplementary same-timestamp documentation checks','',
       'These are published illustrative benchmarks, **not missing local variants** and not research inputs. Comparing the same instant avoids calculating a temporal return. Different vintages and possible corrections prevent attributing every difference to one corporate action.', '',
       table(['Timestamp','Published example','Example close / volume','Local close / volume','Local minus example close / volume'],[[r['timestamp'],r['reference_variant'],r['reference_close']+' / '+r['reference_volume'],r['local_close']+' / '+r['local_volume'],r['local_minus_reference_close']+' / '+r['local_minus_reference_volume']] for r in comparisons]),'',
       'The local historical prices and volumes differ from both the published raw example and, at the split example, its split-only counterpart. This supports a retrospective-adjustment interpretation without identifying individual factors or proving the dividend-volume formula. See [documentation_example_comparison.csv](adjustment_diagnostics/documentation_example_comparison.csv).','',
       '## Additional local corporate-action records','',
       'A catalog metadata search found 60 broad dividend/split-related candidates (many are return-series descriptions, not event tables; no return values were inspected). Four small event-related files were read, retaining only AAPL/MSFT/SPY records:', '',
       table(['RiskLab ID','Root-relative path','AAPL / MSFT / SPY rows','Pilot-record date bounds'],[[a['id'],'`'+a['relative_path']+'`',f"{a['AAPL_rows']} / {a['MSFT_rows']} / {a['SPY_rows']}",a['pilot_min_date']+' to '+a['pilot_max_date']] for a in action_summary]),'',
       '- CE-08 contains five AAPL/MSFT split events with `Stock Splits` values, including all three selected split dates and ratios. Its `Close` column is not used as an unadjusted comparator; provenance/adjustment is not established.',
       '- CE-05/CE-06 contain `Dividend Ex-Date` descriptions for all three selected dividend/distribution dates. They contain the same 71 pilot symbol/date events, with different date formatting. CE-06 adds 10:00 timestamps without established timezone/meaning; those times are **not** used as ex-date intraday cutoffs or dissemination times. Amount-related fields are blank for the inspected pilot records.',
       '- CE-102 is a dividend-change history, not every dividend. It has 18 AAPL and 23 MSFT rows, no SPY, and does not contain the selected 2020-11-06 or 2024-02-14 ex-dates. It cannot alone support a complete ex-dividend exclusion calendar.',
       '- The larger daily panels `RL-C3503DB43BF9` (`bloomberg/03_fundamental/CE-104_SP500Constitutes_Pirce_History_Daily.csv`) and `RL-4DC331F6CC26` (`bloomberg/03_fundamental/sp500_histories.csv`) advertise `Dividends`, `Stock Splits`, OHLC and `Adj Close` fields. Their contents were not opened in this phase; check their pilot records and provenance **before requesting overlapping Bloomberg action history**. A local minute unadjusted/split-only variant still was not identified.',
       'All six event dates are therefore independently observable in local event tables as well as the sampled minute sessions. [event_date_corroboration.json](adjustment_diagnostics/event_date_corroboration.json) links cases to exact records. These tables add date evidence, not file-specific First Rate Data factors or proof of complete action coverage. See [local_action_summary.csv](adjustment_diagnostics/local_action_summary.csv) and [local_action_candidates.json](adjustment_diagnostics/local_action_candidates.json).','',
       '## Provisional convention: measurement logic only','',
       '**Within day t:** provisionally prefer split-only prices for transparent comparison with traded-price references. Any date-constant multiplicative adjustment would cancel in a same-day percentage construction before rounding; therefore the existing split+dividend series may also be adequate within day if factor constancy and rounding are confirmed. That condition has not been empirically checked against another local variant. Do not mix fields from different scales.','',
       '**Across sessions:** a split-neutral scale is essential; unadjusted prices spanning a split create a mechanical share-unit discontinuity. For a price-pressure question, the provisional target is split-only prices with corporate-action flags and an explicit ex-dividend-interval policy, such as excluding those intervals. Exclusion is a recommendation for approval, not an implemented/frozen rule. Split-only prices still carry the economic cash-dividend ex-date drop; treating it as reversal would contaminate the pressure measurement.','',
       'Split+dividend prices are a possible dividend-neutralized alternative, but they change the measured object. Vendor back-adjustment is not automatically exact cash-inclusive overnight wealth, especially when its factor uses an after-hours reference while the research endpoint might be at the regular close. Do not dividend-adjust twice or combine adjusted minute data with unadjusted daily prices. Later corporate actions can retrospectively alter levels; pin the snapshot and factors.','',
       '**Operational adjustment choice remains unresolved.** The preferred split-only input is not locally identified; exact adjustment factors, dividend treatment, endpoint identity and scale matching require confirmation. No adjusted series was reconstructed. Obtain access to already-owned variants if available, or verify documented action records/factors before considering any new data request. Do not choose a convention from predictive results.','',
       '## Decisions and next step','',
       'No new substantive research choice can be frozen from these observations. [design_decisions.md](../design_decisions.md) retains all nine research decisions as NOT YET FROZEN, with the adjustment recommendation and evidence gap recorded. Read-only access, no invented variants, no later-bar substitution, no mixing scales and no result-driven selection are operational safeguards already authorized.','',
       'The next external step is **FLDS metadata review only**, using [bloomberg_pilot_plan.md](bloomberg_pilot_plan.md) and [bloomberg_pilot_spec.csv](../manifests/bloomberg_pilot_spec.csv). No terminal connection or Bloomberg data retrieval was attempted.','',
       'Reproduce source diagnostics with `scripts/audit_adjustments.py` and `scripts/audit_local_action_candidates.py` after configuring the read-only RiskLab root. `scripts/prepare_adjustment_checkpoint.py` renders this report/specification from saved diagnostics. Source size/mtime checks passed for all three minute files; raw excerpts are diagnostic samples only.','']
(BASE/'reports'/'adjustment_comparison.md').write_text('\n'.join(lines),encoding='utf-8')

# Ten fixed dates: five paired contexts, not selected on outcomes.
dates=[('2018-11-23','early_close','13:00 close; ordinary open/close definition check','all three'),
       ('2018-11-26','next_session','next calendar session after early close; ordinary full session','all three'),
       ('2020-03-19','pre_distribution','session before SPY ex-distribution','SPY'),
       ('2020-03-20','ex_distribution','SPY US ex-distribution','SPY'),
       ('2020-08-28','pre_split','session before AAPL 4-for-1 split trading date','AAPL'),
       ('2020-08-31','split_effective','AAPL 4-for-1 new-price trading','AAPL'),
       ('2020-11-05','pre_dividend','session before AAPL dividend ex-date','AAPL'),
       ('2020-11-06','ex_dividend','AAPL dividend ex-date','AAPL'),
       ('2024-02-13','pre_dividend','session before MSFT dividend ex-date','MSFT'),
       ('2024-02-14','ex_dividend','MSFT dividend ex-date','MSFT')]
calendar={r['session_date']:r for r in readcsv(BASE/'reports/timing_diagnostics/exchange_sessions_2010_2025.csv')}
date_rows=[]
for d,kind,purpose,action_security in dates:
    assert d in calendar
    s=calendar[d]
    date_rows.append({'date_set_id':'PILOT10','date':d,'context':kind,'purpose':purpose,'action_security':action_security,'security_scope':'AAPL US Equity|MSFT US Equity|SPY US Equity','scheduled_close_local':s['close_local'],'next_calendar_session':s['next_session'],'selection_basis':'calendar and documented event; no return inspection'})
writecsv(MAN/'bloomberg_pilot_dates.csv',date_rows)

SEC='AAPL US Equity|MSFT US Equity|SPY US Equity'
PRIMARY='REQUIRED FOR PRIMARY REVERSAL TEST'
MECH='REQUIRED FOR AUCTION-MECHANISM TEST'
VALID='USEFUL VALIDATION ONLY'
OPTIONAL='OPTIONAL ROBUSTNESS'
spec=[]


def field(item,mnemonic,intended,function,classification,questions,*,units='UNKNOWN; verify units/scaling in FLDS',frequency='UNKNOWN; daily historical target',currency='UNKNOWN; expected USD for price fields, verify; not applicable if share/count field',condition='No production retrieval until FLDS and design confirmation',scope=SEC,match='UNVERIFIED',local='No equivalent verified locally',stage='FLDS_ONLY',adjustment='UNKNOWN; verify field-specific adjustment behavior and DPDF/explicit request settings'):
    spec.append({'item_id':item,'bloomberg_mnemonic':mnemonic,'mnemonic_status':'KNOWN_CANDIDATE_NOT_TERMINAL_VERIFIED' if mnemonic else 'UNRESOLVED_IN_FLDS_DO_NOT_INVENT',
                 'bloomberg_field_description':'UNKNOWN: exact Bloomberg FLDS text not inspected',
                 'intended_construct':intended,'applicable_security_type_exchange':'US listed common equities: AAPL/MSFT Nasdaq-primary; US listed ETF SPY NYSE Arca; verify per security and historical venue',
                 'security_scope':scope,'historical_availability':'UNVERIFIED: confirm history flag, first/last date, all PILOT10 dates and eventual 2010-2025 coverage per security',
                 'frequency':frequency,'units':units,'currency':currency,'adjustment_behavior':adjustment,
                 'appropriate_function':function,'function_status':'PROPOSED; confirm supported data type/history in FLDS',
                 'construct_match_status':match,'classification':classification,'classification_condition':condition,
                 'pilot_stage':stage,'date_set_id':'PILOT10','local_overlap_action':local,'terminal_questions':questions,'retrieval_authorized_now':'NO; specification only'})

field('daily_open','PX_OPEN','Daily opening price benchmark; not assumed official opening auction','BDH if historical',VALID,'Is it first eligible consolidated trade, primary-exchange open or official auction? Is it core-session only? Confirm price source, trade filters, delayed opening rules and adjustments.',units='Expected native-currency price per share; confirm scale',match='PROXY until exact opening definition verified',local='Minute 09:30 open available; daily benchmark only',stage='AFTER_FLDS_TINY_BENCHMARK')
field('daily_last','PX_LAST','Daily closing/last-price benchmark; not assumed official closing auction','BDH if historical',VALID,'Does historical PX_LAST equal official primary close, consolidated last eligible regular trade, or another mark? Does it exclude late trading? Verify each listing, date and adjustment setting.',units='Expected native-currency price per share; confirm scale',match='PROXY until exact closing definition verified',local='Minute pre-close and close-time bar fields already available; no broad duplicate price download',stage='AFTER_FLDS_TINY_BENCHMARK')
field('official_open','','Distinct historical official opening auction execution price','BDH only if daily history is supported; BDP snapshot is insufficient',PRIMARY,'Find exact mnemonic; verify primary venue auction execution versus indicative/opening reference; exchange and timestamp; delayed opens; no-auction days; currency; history retention and adjustment controls.',units='Target: price per share; FLDS verification required',condition='Required for exact official-auction endpoint version; not required merely to build a bar-proxy pilot',local='No official opening print identified locally')
field('official_close','','Distinct historical official closing auction execution price','BDH only if daily history is supported; BDP snapshot is insufficient',PRIMARY,'Find exact mnemonic; distinguish execution price from indicative match/last trade/NAV; verify close time including early closes, primary venue, late corrections, history and adjustments.',units='Target: price per share; FLDS verification required',condition='Required for exact closing-print version unless PX_LAST is verified to be identical; do not retrieve both when redundant',local='16:00 OHLCV does not identify official auction print')
field('close_auction_volume','OFFICIAL_CLOSE_AUCTION_VOLUME','Official executed closing auction volume','BDH candidate; historical availability not confirmed',MECH,'Mnemonic exists in prior RiskLab header, not verified in current FLDS. Confirm shares vs lots/notional, executed/matched vs orders, primary venue coverage, adjustments, early-close handling and history dates.',units='UNKNOWN: shares/lots/notional and scaling must be verified',currency='N/A if share quantity; verify if notional',local='MM-04 candidate exists but units/date alignment unresolved; not opened or used in this phase')
field('signed_close_imbalance','','Signed closing auction order imbalance at a specified pre-close observation time or final dissemination','BDH only if dated historical snapshot exists; otherwise determine supported history service',MECH,'Find exact mnemonic and retained history. Define buy-minus-sell or sell-minus-buy, shares/units, cutoff relative to scheduled close, paired/matched exclusions, revisions and exchange differences. Is it live-only? Historical daily cannot be assumed.',units='Target signed share quantity; verify definition/scaling',currency='Normally N/A for shares; verify',frequency='UNVERIFIED; timestamped dissemination stream vs daily snapshot',local='No local signed imbalance source identified')
field('imbalance_side','','Buy/sell side paired with unsigned auction imbalance magnitude','BDH if historical paired snapshot exists; BDP current side is insufficient',MECH,'Needed only if magnitude is unsigned. Verify side-code dictionary, zero/balanced codes and that side and magnitude refer to exactly the same event/time/version. Do not download if already signed magnitude suffices.',units='Categorical side codes; dictionary required',currency='N/A',frequency='Same timestamp/frequency as matched magnitude',condition='Conditional: required only if unsigned magnitude must be signed; do not duplicate a confirmed signed field')
field('paired_shares','','Auction matched/paired shares; not signed imbalance','BDH only if historical snapshot supported',OPTIONAL,'Find exchange-specific field, exact matched/paired definition, snapshot time, units and retained history; explicitly distinguish executed volume and unpaired signed imbalance.',units='Target share count; verify scaling',currency='N/A if shares',frequency='UNVERIFIED; timestamped snapshot vs daily',match='DIFFERENT CONSTRUCT; never substitute for signed imbalance')
field('indicative_imbalance','','Indicative auction imbalance as separately defined by exchange','BDH only if history exists; confirm service otherwise',OPTIONAL,'Is this indicative/net order imbalance, paired shares, indicative clearing size or price? Is NOII a dissemination feed rather than one field? Confirm exact component, side, time and history; no equivalence assumed.',units='UNKNOWN; must distinguish price from shares/side',frequency='UNVERIFIED; often dissemination snapshots',match='NOT EQUIVALENT unless definition and timing prove required signed construct')
field('dividend_events','','Historical cash distributions with ex-date, amount, currency and event type','BDS event history candidate; exact mnemonic and response columns unresolved',PRIMARY,'Find historical dividend/distribution event table for equities and ETF; verify ex-date vs record/pay date, ordinary vs special, split basis, gross/net cash, currency and revisions. First inspect locally owned CE-104/sp500_histories event columns; retrieve only verified gaps.',units='Cash per then-current or adjusted share; verify',frequency='Event-based',condition='Required to flag/resolve dividend-crossing intervals only where complete documented local records are unavailable',local='CE-05/06 already contain selected ex-dates, with amounts blank; CE-102 is change-only. CE-104/sp500_histories require pilot-record review before any duplicate request.')
field('split_events','','Historical split effective dates and new/old share ratios','BDS event history candidate; exact mnemonic unresolved',PRIMARY,'Find effective trading date and split/reverse-split ratio, numerator/denominator convention, revisions and any historical adjustment factors. Verify CE-08 pilot split records first; do not infer actions solely from price jumps.',units='Dimensionless new-shares/old-shares ratio; verify orientation',currency='N/A',frequency='Event-based',condition='Required only for gaps/verification if complete documented local action calendar/factors cannot be established',local='CE-08 RL-41A9B2151B06 already contains all three selected split dates/ratios; do not re-download those merely to obtain dates.')
field('current_members','INDX_MEMBERS','Current S&P 500 constituent list only; not historical effective membership','BDS candidate on SPX Index',OPTIONAL,'Verify exact field and identifier columns. Does it support an as-of date? Current members alone cannot establish past membership or avoid survivorship bias.',units='Security identifiers/list, not prices',currency='N/A',frequency='Current bulk snapshot unless history override documented',scope='SPX Index: FLDS metadata context only; not a fourth price-pilot security',match='CURRENT MEMBERSHIP ONLY; not the required historical construct',condition='Only for reference/mapping; do not retrieve current snapshot as historical universe')
field('historical_membership','','Historical S&P 500 constituent as-of membership and effective entry/exit dates','BDS/as-of bulk candidate; confirm historical data service and supported date override',PRIMARY,'Identify exact historical field(s), effective-date semantics, stable IDs and supported as-of override. Can complete dated constituents or entry/exit events be returned? No current-list backfill.',units='Identifiers plus dates/membership flags; verify',currency='N/A',frequency='Effective-date events or historical snapshots; verify',scope='SPX Index: FLDS metadata context only; outside initial three-security price retrieval',condition='Conditional on eventual historical S&P 500 cross-sectional universe; not needed for the fixed three-security pilot',local='AP15 price/volume panel is not verified membership history')
field('currency','CRNCY','Security native currency for scale validation','BDP current reference; verify historical constancy',VALID,'Confirm USD for all three securities. No currency conversion override without explicit approval.',units='Currency code',currency='N/A; this field is the currency identifier',frequency='Reference snapshot',stage='AFTER_FLDS_REFERENCE_ONLY')
field('primary_exchange','EQY_PRIM_EXCH','Primary exchange reference for matching venue-specific auction fields','BDP reference; historical venue changes require separate check',VALID,'Confirm field text/code and listing: AAPL/MSFT Nasdaq, SPY NYSE Arca; US composite security does not itself identify primary-venue auction data.',units='Exchange name/code',currency='N/A',frequency='Reference snapshot',stage='AFTER_FLDS_REFERENCE_ONLY')
field('stable_security_id','ID_BB_GLOBAL','Stable Bloomberg identifier for future cross-source mapping','BDP reference',OPTIONAL,'Confirm share class, composite vs exchange-level identifier and mapping to local tickers. Not needed to duplicate existing minute prices.',units='Identifier string',currency='N/A',frequency='Reference snapshot')
for r in spec:
    if r['item_id'] in ['current_members','historical_membership']:
        r['applicable_security_type_exchange']='S&P 500 index reference context (SPX Index), not an equity/ETF price field; FLDS only in current pilot'
writecsv(MAN/'bloomberg_pilot_spec.csv',spec)

plan=['# Bloomberg pilot: FLDS verification first','',
      'Prepared 2026-10-27. **Not an executable request and not permission to retrieve data.** No Bloomberg terminal/API was accessed. Unknown mnemonics and exact descriptions remain blank/unknown rather than guessed.','',
      '## Scope and fixed dates','',
      'Initial price securities: **AAPL US Equity, MSFT US Equity, SPY US Equity**. All three are used on the same ten dates. `SPX Index` appears only as a FLDS context for the membership question; no index price or broad constituent download is proposed.','',
      table(['Date','Context'],[[r['date'],r['purpose']] for r in date_rows]),'',
      'Dates are calendar/event choices, not selected on returns. They form five pairs: early-close/next-session; SPY distribution; AAPL split; AAPL dividend; MSFT dividend. Dates and next-session links are in [bloomberg_pilot_dates.csv](../manifests/bloomberg_pilot_dates.csv). Event-date evidence is linked in [adjustment_comparison.md](adjustment_comparison.md).','',
      '## Stage 1: terminal metadata, no history retrieval','',
      '[bloomberg_pilot_spec.csv](../manifests/bloomberg_pilot_spec.csv) records every candidate/question, all four priority classes, proposed BDH/BDP/BDS route, expected construct, unresolved metadata and local overlap. Exact Bloomberg field descriptions, historical availability, units/currency and adjustment behavior are **not FLDS-verified**. A proposed daily field/function is not evidence that history exists.','',
      '- Inspect `PX_OPEN`, `PX_LAST`, `OFFICIAL_CLOSE_AUCTION_VOLUME`, `CRNCY`, `EQY_PRIM_EXCH`, `ID_BB_GLOBAL` and `INDX_MEMBERS`. The auction-volume mnemonic comes from a previously inspected local export, not a verified terminal field definition. Other named fields are candidates, not certified construct matches.',
      '- Search FLDS for distinct official opening/closing auction execution prices; signed closing imbalance or unsigned magnitude plus matching side; paired shares; indicative imbalance/NOII components; historical split and dividend event tables; and historical S&P 500 membership/effective dates. Mnemonics for these are intentionally unresolved.',
      '- For **each security and exchange**, preserve exact FLDS name/description, history flag/coverage, units/scaling, currency, corporate-action behavior, supported overrides and snapshot timing. Require the relevant date/time for every imbalance/side pair. BDP live values do not establish historical availability; a bulk current-member list does not establish past membership.',
      '- Do not substitute indicative price, paired shares, auction executed volume or a NOII component for signed imbalance. If history is unavailable or live-only, record that as a mechanism-data blocker rather than fill or proxy it silently.','',
      '## Stage 2: tiny daily-price validation, only after separate authorization','',
      'Baseline ceiling: **3 securities × 10 dates × 2 fields = 60 daily price values** (`PX_OPEN`, `PX_LAST`). Use date-limited BDH history, native currency, trading dates only and no forward/backward filling. Do not request a continuous multi-year range merely to select ten rows. Stop if FLDS shows either daily field is an inappropriate benchmark.','',
      'First validate an explicit unadjusted configuration for comparison to official nominal prints. Record the terminal’s effective normal-cash, abnormal-cash and capital-change/split adjustment settings and whether account-level DPDF preferences override them. Translate desired behavior into verified BDH/Excel/API options in the terminal; no guessed option names or defaults are provided here.','',
      'Then, only if needed, request split-only and split+dividend versions for the affected security on its own action pair: AAPL on Aug 28/31 and Nov 5/6 2020; SPY on Mar 19/20 2020; MSFT on Feb 13/14 2024. This adds at most **4 pairs × 2 dates × 2 fields × 2 extra conventions = 32 values** (92 including baseline). Compare like-for-like adjustment vintages; raw nominal Bloomberg prices cannot be directly equated to adjusted local levels.','',
      'If PX_OPEN/PX_LAST are confirmed identical to the desired official fields, do not duplicate them. Otherwise distinct official-price fields are conditionally required for the exact-auction endpoint version; a three-security, ten-date check would add at most 60 values. No field is substituted merely because it is easier to retrieve.','',
      '## Required versus optional','',
      '- **REQUIRED FOR PRIMARY REVERSAL TEST:** confirmed official endpoint prices for an exact-print design (conditional on that design); documented split/dividend event information where not locally available; historical membership only if the eventual universe is defined by historical S&P 500 membership.',
      '- **REQUIRED FOR AUCTION-MECHANISM TEST:** executed closing-auction volume and a defined historical signed imbalance; a separate side field only if the magnitude is unsigned. Local MM-04 is not research-ready and is not used here.',
      '- **USEFUL VALIDATION ONLY:** PX_OPEN/PX_LAST benchmarks and small currency/exchange reference checks; local minute prices already cover the pilot.',
      '- **OPTIONAL ROBUSTNESS:** paired shares, separately defined indicative constructs, current membership/mapping snapshots and additional identifiers. None replaces the required mechanism measure.','',
      'No broad daily-price, minute-price, all-constituent or 2010–2025 imbalance download is proposed now. Local CE-08 already contains the selected split dates/ratios; CE-05/06 contain selected ex-dates but no cash amounts, and CE-102 is change-only. First check the event columns/provenance of locally owned CE-104 and sp500_histories before any Bloomberg action-history request. Corporate-action retrieval should cover verified gaps only. Additional mechanism/universe requests wait for field verification and a frozen design.','',
      '## Acceptance checklist for later retrieval','',
      'Store security identifiers, exact fields, dates/timestamps, units, source venue, adjustment configuration, DPDF setting, request type, retrieval time, field exceptions and missing-value reasons. Keep unadjusted/split-only/split+dividend outputs separate. Never compare mixed scales or treat absent history as zero. Confirm early-close auction time and dividend ex-date versus payment date. A field is accepted as exact only after its definition and small pilot observations support the intended construct; similarity of names is insufficient.','',
      'No substantive design decision is frozen by this plan. A bar-proxy reversal pilot may need no additional Bloomberg production prices; an exact-auction test and the imbalance mechanism still require the metadata/data distinctions above.','']
(BASE/'reports'/'bloomberg_pilot_plan.md').write_text('\n'.join(plan),encoding='utf-8')
assert len(date_rows)==10 and len(set(r['date'] for r in date_rows))==10
assert {r['classification'] for r in spec}=={PRIMARY,MECH,VALID,OPTIONAL}
assert all(r['retrieval_authorized_now'].startswith('NO') for r in spec)
assert len([r for r in spec if not r['bloomberg_mnemonic']])==9
print('Wrote adjustment report, 10-date plan and',len(spec),'FLDS candidate/question rows; no Bloomberg request sent.')
# Preserve the later explicit user freeze and supplied FLDS evidence on regeneration.
import runpy
runpy.run_path(str(BASE/'scripts'/'freeze_design_checkpoint.py'),run_name='__main__')
