# Project 2 design decisions

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
| Adjustment convention | UNRESOLVED | Local daily duplicates add partial AAPL/MSFT action evidence but no SPY rows or usable Adj Close/factors. The 2010–2025 event calendar is incomplete, including late 2025. Do not freeze cash/split-crossing exclusions, reconstruct variants or mix nominal and adjusted endpoints. See reports/corporate_action_coverage.md. |
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
ex-dates but no pilot cash amounts; CE-102 is change-only. The CE-104/sp500_histories review is complete; see the coverage checkpoint below.
Resolve remaining source definitions and event-date gaps before requesting
overlapping corporate-action history.

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
