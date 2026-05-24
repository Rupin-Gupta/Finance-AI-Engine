import pandas as pd


def compute_sma(df: pd.DataFrame, window: int = 20, price_col: str = "close") -> pd.Series:
    return df[price_col].rolling(window).mean()


def compute_ema(df: pd.DataFrame, window: int = 20, price_col: str = "close") -> pd.Series:
    return df[price_col].ewm(span=window, adjust=False).mean()


def compute_rsi(df: pd.DataFrame, window: int = 14, price_col: str = "close") -> pd.Series:
    delta = df[price_col].diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def compute_volatility(df: pd.DataFrame, window: int = 20, price_col: str = "close") -> pd.Series:
    return df[price_col].pct_change().rolling(window).std() * (252 ** 0.5)


def compute_momentum(df: pd.DataFrame, period: int = 10, price_col: str = "close") -> pd.Series:
    return df[price_col].pct_change(periods=period)


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["sma_20"] = compute_sma(df)
    df["ema_20"] = compute_ema(df)
    df["rsi_14"] = compute_rsi(df)
    df["volatility_20"] = compute_volatility(df)
    df["momentum_10"] = compute_momentum(df)
    return df
