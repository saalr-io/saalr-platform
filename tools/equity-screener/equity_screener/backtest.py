import pandas as pd


def sharpe(daily_returns: pd.Series, rf_annual: float = 0.0, periods: int = 252) -> float:
    if len(daily_returns) == 0:
        return 0.0
    excess = daily_returns - rf_annual / periods
    sd = excess.std(ddof=0)
    if sd == 0 or pd.isna(sd):
        return 0.0
    return float(excess.mean() / sd * (periods ** 0.5))


def max_drawdown(value: pd.Series) -> float:
    if len(value) == 0:
        return 0.0
    running_max = value.cummax()
    drawdown = value / running_max - 1.0
    return float(drawdown.min())


def cagr_from_value(value: pd.Series) -> float:
    if len(value) < 2 or value.iloc[0] <= 0:
        return 0.0
    years = (value.index[-1] - value.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return float((value.iloc[-1] / value.iloc[0]) ** (1 / years) - 1)


def equal_weight_value(
    prices: pd.DataFrame,
    holdings: dict,
    start_cash: float = 1000.0,
) -> pd.Series:
    """Walk the trading calendar; at each rebalance date in `holdings` (date -> [tickers]),
    re-allocate the current portfolio value equally across those tickers (cash if empty)."""
    dates = prices.index
    rebal_dates = sorted(holdings)
    value = pd.Series(index=dates, dtype=float)
    cash = start_cash
    units: dict[str, float] = {}

    def portfolio_value(row) -> float:
        held = sum(u * row[t] for t, u in units.items() if t in row and not pd.isna(row[t]))
        return cash + held

    next_rebal = 0
    for d in dates:
        if next_rebal < len(rebal_dates) and d >= rebal_dates[next_rebal]:
            row = prices.loc[d]
            current = portfolio_value(row)
            tickers = [t for t in holdings[rebal_dates[next_rebal]] if t in row and not pd.isna(row[t])]
            units = {}
            cash = current
            if tickers:
                each = current / len(tickers)
                for t in tickers:
                    units[t] = each / row[t]
                cash = 0.0
            next_rebal += 1
        value.loc[d] = portfolio_value(prices.loc[d])
    return value


def daily_returns(value: pd.Series) -> pd.Series:
    return value.pct_change().dropna()
