# Closing Auction & Overnight Reversal

---

## Research Question

When a stock moves sharply just before the market closes, how much of that move reverses by the next opening? Is the relationship different on days when a larger share of trading takes place in the closing auction?

Closing auctions bring eligible buy and sell orders together at an exchange-determined closing price. They may help absorb temporary trading pressure, but auction-related imbalances could also move prices. This project tests those competing explanations rather than assuming either is correct.

## Research Design

- **Closing-window return:** Primarily the final 10 minutes of the scheduled session; 5-, 15-, and 30-minute windows for robustness.
- **Overnight return:** From the closing price to the next valid trading session's opening price.
- **Auction participation:** Primary-exchange closing-auction volume divided by consolidated U.S. daily share volume.
- **Empirical test:** The relationship between closing-window returns and overnight returns, including an interaction with auction participation.
- **Validation:** Exchange-calendar alignment, early closes, corporate actions, venue changes, missing observations, and alternative measurement choices.

> The intended final analysis uses official closing prices where the source history and adjustment conventions permit. Continuous-minute price proxies are clearly identified as provisional.

## Data

The analysis combines RiskLab one-minute equity/ETF data with Bloomberg historical prices, closing-auction volumes, and daily volumes. Source histories have different coverage: auction-volume inventory begins in **May 2013**, while the downloaded U.S. official-close price series begins in **January 2016**. The final estimation window and eligible securities will be determined by documented measurement and coverage checks, not by statistical significance.

The underlying data are licensed and are not redistributed here. Screenshots, terminal exports, source workbooks, local paths, intermediate panels, and private presentation material are deliberately excluded.

## Status

**Work in progress — November 2026.**

- **Completed:** A provisional three-instrument panel (`SPY`, `AAPL`, `MSFT`) and its validation checks have been built. Bloomberg source data for a broader 16-instrument inventory and additional official-close histories have been collected.
- **Next steps:** Cross-sectional validation, final endpoint alignment, and empirical estimation.
- **Note:** No hypothesis-test results are claimed at this stage.

## Repository Scope

This public repository is intended to hold the research source code, tests, and curated methodological documentation. It does not contain the private datasets or generated research outputs.

The processing scripts require access to the corresponding licensed inputs and the user's local environment. A public reproduction guide and aggregate results will be added after the final methodology is validated.

---

## Disclaimer

*Academic research project. Not investment advice.*
