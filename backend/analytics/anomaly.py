import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest


def zscore_anomalies(df: pd.DataFrame, col: str = "close",
                      threshold: float = 3.0) -> pd.DataFrame:
    z = (df[col] - df[col].mean()) / df[col].std()
    return df[z.abs() > threshold].copy()


def isolation_forest_anomalies(df: pd.DataFrame, features: list[str],
                                 contamination: float = 0.05) -> pd.DataFrame:
    X = df[features].dropna()
    clf = IsolationForest(contamination=contamination, random_state=42)
    preds = clf.fit_predict(X)
    return df.loc[X.index[preds == -1]].copy()


def rolling_threshold_anomalies(df: pd.DataFrame, col: str = "volume",
                                  window: int = 20, sigma: float = 2.5) -> pd.DataFrame:
    roll_mean = df[col].rolling(window).mean()
    roll_std = df[col].rolling(window).std()
    upper = roll_mean + sigma * roll_std
    return df[df[col] > upper].copy()
