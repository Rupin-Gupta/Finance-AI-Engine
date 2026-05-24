import pandas as pd
import numpy as np
import pytest
from backend.analytics.indicators import compute_sma, compute_rsi, compute_volatility


def make_df(n=50):
    prices = np.cumsum(np.random.randn(n)) + 100
    return pd.DataFrame({"close": prices, "volume": np.random.randint(1000, 5000, n)})


def test_sma_length():
    df = make_df(50)
    sma = compute_sma(df, window=20)
    assert len(sma) == 50
    assert sma.iloc[:19].isna().all()


def test_rsi_bounds():
    df = make_df(50)
    rsi = compute_rsi(df, window=14)
    valid = rsi.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_volatility_non_negative():
    df = make_df(50)
    vol = compute_volatility(df, window=20)
    assert (vol.dropna() >= 0).all()
