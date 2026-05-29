from pathlib import Path

import pandas as pd
import yfinance as yf

_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "prices"


def get_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Adjusted-close prices for tickers in [start, end]; cached per (tickers,start,end)."""
    _CACHE.mkdir(parents=True, exist_ok=True)
    key = f"{'_'.join(sorted(tickers))[:60]}_{start}_{end}.parquet"
    path = _CACHE / key
    if path.exists():
        return pd.read_parquet(path)
    data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    close = data["Close"] if "Close" in data else data
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close = close.dropna(how="all")
    close.to_parquet(path)
    return close
