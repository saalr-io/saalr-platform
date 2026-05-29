from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "prices"


def _cache_key(tickers: list[str], start: str, end: str, kind: str) -> Path:
    return _CACHE / f"{'_'.join(sorted(tickers))[:60]}_{start}_{end}.{kind}.parquet"


def get_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Adjusted-close prices for tickers in [start, end]; cached per (tickers,start,end)."""
    _CACHE.mkdir(parents=True, exist_ok=True)
    path = _cache_key(tickers, start, end, "close")
    if path.exists():
        return pd.read_parquet(path)
    data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    close = data["Close"] if "Close" in data else data
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close = close.dropna(how="all")
    close.to_parquet(path)
    return close


def get_splits(tickers: list[str], start: str, end: str) -> dict[str, list[tuple[date, float]]]:
    """Split events per ticker as [(date, ratio), ...] (ratio 4.0 == 4:1 forward split).

    Needed to put SEC raw share counts on a common basis so splits aren't mistaken
    for dilution. Cached as a tidy (ticker, date, ratio) parquet.
    """
    _CACHE.mkdir(parents=True, exist_ok=True)
    path = _cache_key(tickers, start, end, "splits")
    if path.exists():
        tidy = pd.read_parquet(path)
    else:
        data = yf.download(
            tickers, start=start, end=end, auto_adjust=False, actions=True, progress=False
        )
        if "Stock Splits" in data:
            splits = data["Stock Splits"]
        else:
            splits = pd.DataFrame(index=data.index)
        if isinstance(splits, pd.Series):
            splits = splits.to_frame(tickers[0])
        rows = []
        for ticker in splits.columns:
            col = splits[ticker]
            for ts, ratio in col[col > 0].items():
                rows.append({"ticker": ticker, "date": pd.Timestamp(ts).date().isoformat(),
                             "ratio": float(ratio)})
        tidy = pd.DataFrame(rows, columns=["ticker", "date", "ratio"])
        tidy.to_parquet(path)

    out: dict[str, list[tuple[date, float]]] = {}
    for row in tidy.itertuples(index=False):
        out.setdefault(row.ticker, []).append((date.fromisoformat(row.date), row.ratio))
    return out
