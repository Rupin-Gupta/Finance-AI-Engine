import pandas as pd


def sector_summary(df: pd.DataFrame, sector_col: str = "sector",
                    price_col: str = "close") -> pd.DataFrame:
    """Aggregate mean close & volatility per sector."""
    return (
        df.groupby(sector_col)[price_col]
        .agg(mean_close="mean", std_close="std", count="count")
        .reset_index()
    )
