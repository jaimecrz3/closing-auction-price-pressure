"""Render coverage narrative/figure using repository diagnostics only."""
import csv
import json
from pathlib import Path
from validate_pilot_timing import figure, table

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'reports'/'timing_diagnostics'


def readcsv(name):
    return list(csv.DictReader((OUT/name).open(encoding='utf-8',newline='')))


meta=json.loads((OUT/'calendar_metadata.json').read_text())
summary=readcsv('coverage_summary.csv')
detail=readcsv('coverage_by_session.csv')
behavior=readcsv('close_bar_behavior_counts.csv')
annual=readcsv('coverage_by_year.csv')
annual_typed=[{**r,'year':int(r['year']),'window_minutes':int(r['window_minutes']), 'percent_complete':float(r['percent_complete'])} for r in annual]
figure(annual_typed)

lines=['# Project 2 pilot timing validation','',
       'Validation date: 2026-10-26. Scope: SPY, AAPL and MSFT; anchor sessions 2010–2025. **No return variables, regressions, predictive comparisons or MM-04 use.** Current design status is recorded in [design_decisions.md](../design_decisions.md).','',
       '## Calendar and provenance','',
       'Used installed `exchange_calendars==4.13.2`, calendar `XNYS`, with schedule timestamps converted from UTC to `America/New_York`. Dates were generated from calendar rules, not inferred from adjacent price-file dates. Package/source hash and a complete session snapshot are saved. In this package `XNAS` is an alias for `XNYS`, so the Nasdaq mapping is a shared US-equity session assumption rather than an independent venue-calendar comparison. The implementation and its holiday/early-close rules are documented in the [pinned calendar source](https://github.com/gerrymanoim/exchange_calendars/blob/4.13.2/exchange_calendars/exchange_calendar_xnys.py).','',
       '**4,024 expected sessions = 3,990 normal + 34 early-close sessions.** All open at 09:30 Eastern; normal close is 16:00 and early close is 13:00. The [NYSE reference](https://www.nyse.com/markets/hours-calendars) documents core hours and 13:00 early closes. Historical dates here come from the pinned package, not an extrapolation of the current exchange webpage.','',
       'Checks include the 2012-10-29/30 closures, 2018-12-05, 2025-01-09, the 2022 Juneteenth closure and 2021-06-18 remaining open. Known early-close examples separately checked: 2013-07-03, 2018-11-23 and 2025-12-24. The calendar links 2012-10-26 to 2012-10-31 and 2025-12-31 to 2026-01-02. The latter next-session follow-up is included using existing local rows; it does not add a 2026 anchor session.','',
       'Files: [full calendar](timing_diagnostics/exchange_sessions_2010_2025.csv), [early-close list](timing_diagnostics/early_close_sessions.csv), [year counts](timing_diagnostics/calendar_by_year.csv), [version/source hash](timing_diagnostics/calendar_metadata.json). Calendar snapshots identify scheduled core trading, not security-specific halts.','',
       '## Timestamp and close/open interpretation','',
       'Local stock/ETF metadata establishes the column order `timestamp, open, high, low, close, volume`, US Eastern time and **bar-start labels**. The source strings have no offset and were preserved. There was no relabeling, interpolation, price adjustment or source rewrite. Calendar timezone conversion affects only the generated schedule.','',
       table(['Raw label on a normal session','Documented one-minute interval','What it can establish'],[
           ['09:30','09:30:00 through 09:30:59','Open is the first eligible trade represented by this bar; not separately certified as the official opening auction price.'],
           ['15:59','15:59:00 through 15:59:59','Close is a last-pre-close-minute price proxy. No evidence that it contains the official 16:00 auction print.'],
           ['16:00','16:00:00 through 16:00:59','A distinct close-time minute bar. Auction and post-close trades could coexist; OHLC do not identify which trade is the official print.']]),'',
       'On a 13:00-close session, the corresponding final pre-close bar is 12:59 and the close-time bar is 13:00. A 15:59 or 16:00 observation that day is outside core hours; its absence is **not** missing core-session coverage. Such raw observations, when present, are retained.','',
       '### Endpoint observations and price behavior','',
       'The following are bar-structure diagnostics only: exact price equalities/inequalities within or across adjacent minutes. No signed price move, return, overnight difference, correlation or regression was calculated.','',
       table(['Symbol','Session type','Expected','Final pre-close bar','Close-time bar','Close+1 minute bar','Close-time H>L','Close-time O differs C'],
             [[r['symbol'],r['session_type'],r['expected_sessions'],r['last_preclose_present'],r['bar_at_close_present'],r['bar_one_minute_after_close_present'],r['close_bar_positive_high_low_range'],r['close_bar_open_differs_close']] for r in behavior]),'',
       'A 16:00 bar is systematic on normal sessions: SPY 3,990/3,990; AAPL and MSFT 3,989/3,990. Both missing cases are 2014-10-28. The frequent nonzero high–low ranges and open/close differences establish that these are often multi-price trading intervals, not scalar official-closing-price records. Nearby 16:01 bars and later observations support post-close trading being represented. This is consistent with a separate minute that may mix the closing auction and subsequent trades; it does **not** prove auction exclusion or establish that any one OHLC field equals the official closing price.','',
       'For example, MSFT 2025-06-16 has a 15:59 close of `477.46`, a 16:00 open of `477.46` and 16:00 close of `476.1347`. AAPL 2015-06-15 has 16:00 open `28.3065`, high `28.3199`, low `28.3065` and close `28.3132`. Equality in one case or a large close-time volume is not official-auction identification. Raw lineage is in the hand-checks. Neither 15:59 nor 16:00 has been designated the research close.','',
       '### Next-session open and missing bars','',
       'All 4,024 anchor sessions for each symbol have a valid next-calendar-session 09:30 bar, including 2025-12-31 → 2026-01-02. Every expected 2010–2025 session itself also has 09:30. Thus the older SPY missing-09:30 issue does not occur within this coverage period. A historical control (SPY 2000-01-03 → 2000-01-04) demonstrates the safeguard: the required next 09:30 is absent, even though later opening bars exist, so eligibility is false. That control is outside all 2010–2025 tables and the figure.','',
       '**No later-bar substitution is permitted in this diagnostic.** A missing 09:30 would be excluded under the candidate timing rule, not replaced by the first observed bar. Even a present 09:30 bar cannot certify an official opening auction price or resolve a delayed security-specific auction.','',
       'There are real absent calendar-expected labels elsewhere: each symbol lacks 09:35 on 2020-03-09 and 09:31–09:35 on 2020-03-16. These are inside scheduled core hours. They do not affect the last-30-minute or next-09:30 requirements. The package calendar cannot assign a cause such as a halt, no trades or provider omission. Local documentation says no-trade bars are omitted, so “absent required label” should not be confused with a proven missing transaction. Conversely, sparse 15:30–15:59 observations on 13:00-close dates are outside core hours, not incomplete final windows.','',
       '## Candidate-window coverage comparison','',
       'For scheduled close C and window L, the required bar-start labels are **C-L through C-1**. For normal sessions: 15:55–15:59, 15:50–15:59, 15:45–15:59 or 15:30–15:59. For early closes: 12:55–12:59, 12:50–12:59, 12:45–12:59 or 12:30–12:59.','',
       '“Usable pre-close proxy” means every required label has finite, positive, internally consistent OHLC and nonnegative volume, plus a valid next-session 09:30 observation. The hypothetical endpoint fields would be the first required bar’s open, the final pre-close bar’s close and the next 09:30 bar’s open; **none were assembled into research variables or returns**. “Usable close-time proxy” additionally requires the C-labeled bar. These are endpoint-availability scenarios, not adopted close definitions. Positive-volume-only counts are also saved and coincide with pre-close-proxy counts.','',
       table(['Symbol','Window (min)','Expected sessions','Complete labels','Missing ≥1 bar','Early closes','Valid next 09:30','Usable pre-close proxy','Usable close-time proxy'],
             [[r['symbol'],r['window_minutes'],r['expected_sessions'],r['complete_required_labels'],r['missing_at_least_one_label'],r['early_close_sessions'],r['valid_next_session_0930'],r['usable_preclose_proxy'],r['usable_close_time_proxy']] for r in summary if r['session_type']=='all']),'',
       'Each symbol/window has 3,990/3,990 complete normal sessions and 34/34 complete early-close sessions. **The zero missing-window count is specific to these three liquid symbols and 2010–2025, with calendar-relative early closes.** It does not validate other symbols or the oldest data. Missing-minute cases in the hand-checks concern opening labels or the outside-period SPY control, not an invented incomplete closing window.','',
       'The table reports combined calendar-relative coverage only; early-close inclusion/exclusion in the research sample remains unfrozen. Do not select a primary length from these identical coverage counts. Detailed [coverage summary with normal/early strata](timing_diagnostics/coverage_summary.csv), [session diagnostics](timing_diagnostics/coverage_by_session.csv) and [yearly coverage](timing_diagnostics/coverage_by_year.csv) are saved.','',
       '![Coverage-only figure](pilot_coverage.png)','',
       'All four candidate lengths have 100% label coverage in every year for each symbol; the four plotted series overlap. The denominator includes early closes using their actual scheduled close. This figure contains no research outcome or predictive result.','',
       '## Ten hand-checks and manifest','',
       '[Ten human-readable traces](timing_hand_checks.md) cover three normal sessions, three early closes, two opening-gap cases, a next-session link across the Sandy closures and one historical missing-09:30 control. Reviewed the source line numbers, exact numeric strings, final-window label ranges and next-calendar-session mappings for all ten. Small raw-row diagnostic excerpts are saved per symbol; the original files were not copied or altered.','',
       '[data_manifest.csv](../data_manifest.csv) records RiskLab IDs and root-relative paths. The MM-04 and AP15 rows are prior-checkpoint provenance only: neither source was opened or used in this phase. Catalog/utilities and documentation without assigned stable IDs have blank IDs rather than invented ones. The installed calendar is separately identified by package version and source hash.','',
       '## Recommendation and decisions still requiring approval','',
       '**Technically feasible:** an explicitly labeled continuous-trading proxy using the last pre-close minute’s close, a calendar-relative 5/10/15/30-minute window and the next valid session’s 09:30 bar open. All four lengths pass this pilot’s coverage requirements. Keep the no-substitution safeguard and distinguish scheduled early closes from absent required labels. This establishes technical feasibility, not approval to construct returns.','',
       '**Not established:** an exact official closing-auction or opening-auction price from these OHLCV fields. Obtain provider documentation on auction inclusion/trade filters and, ideally, validate against a small official-price reference before claiming a closing-print test. No 16:00-bar OHLC field is automatically an official auction price.','',
       'The user has now frozen six choices ex ante in [design_decisions.md](../design_decisions.md), including a 10-minute primary window independent of coverage. Exact endpoints, adjustment convention and final universe remain source-dependent; no supervisor-response blocker applies. Adjustment compatibility remains unresolved, including the fractional and zero volumes already documented at the source checkpoint.','',
       '## Reproduction and verification','',
       'Run `. .\\scripts\\use_risklab.ps1`, then `.\\.venv\\Scripts\\python.exe -B scripts\\validate_pilot_timing.py`. Mounted-root read access outside the sandbox may be necessary. Dependencies are pinned in `requirements-timing.txt`. The calendar is generated locally; package installation was the only software download in this phase. No Bloomberg data were downloaded.','',
       '`scripts/write_timing_report.py` regenerates this narrative and figure from repository diagnostics without provider access. Verification reconciles all 12,072 symbol-session rows and 36 symbol/window/stratum summaries, nested label windows, known calendar closures, ten trace dates and unchanged source sizes/modification times. See [validation_checks.json](timing_diagnostics/validation_checks.json). Source file modes were read-only. Raw observations were preserved, and no final research variables or model outputs were created.','']
(BASE/'reports'/'pilot_timing_validation.md').write_text('\n'.join(lines),encoding='utf-8')
print('Wrote timing report and coverage figure from saved diagnostics.')
