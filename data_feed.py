"""
BIST veri akışı - Yahoo Finance (yfinance)
BIST hisseleri '.IS' soneki ile çekilir (THYAO.IS, GARAN.IS ...).
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

# Likit BIST 30 (yedek liste). watchlist boşsa kullanılır.
BIST30 = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "SISE.IS",
    "EREGL.IS", "TUPRS.IS", "BIMAS.IS", "AKBNK.IS", "YKBNK.IS",
    "SAHOL.IS", "FROTO.IS", "TCELL.IS", "MGROS.IS", "ARCLK.IS",
    "PETKM.IS", "SASA.IS", "TOASO.IS", "FENER.IS", "GUBRF.IS",
    "KOZAA.IS", "KOZAL.IS", "TTRAK.IS", "AGHOL.IS", "DOHOL.IS",
    "ISCTR.IS", "VAKBN.IS", "HALKB.IS", "TMSK.IS", "PGSUS.IS",
]


def fetch(ticker: str, interval: str = "1d", period: str = "2y") -> pd.DataFrame | None:
    """
    Tek bir hisse için OHLCV çeker. Başarısızsa None döner.
    """
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as e:  # ağ/veri hatası
        print(f"  [HATA] {ticker} indirilemedi: {e}")
        return None

    if df is None or len(df) == 0:
        print(f"  [UYARI] {ticker} için veri yok.")
        return None

    # Çok seviyeli kolonları düzelt
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    return df


def get_tickers(cfg: dict) -> list[str]:
    wl = cfg.get("watchlist") or []
    if wl:
        return [t.strip() for t in wl if t.strip()]
    if cfg.get("use_bist30_if_empty", True):
        return BIST30
    return []
