"""
BIST Weighted Strategy - Gösterge ve sinyal motoru
Orijinal: AlbertoCuadra/algo_trading_weighted_strategy (Pine Script, 5 gösterge)

Bu modül saf hesaplama yapar; veri çekme veya bildirim burada yoktur.
Her gösterge için SON bar'da (günlük) taze bir long/short sinyali olup
olmadigini tespit eder, sonra ağırlıklı skoru hesaplar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# Temel göstergeler
# ----------------------------------------------------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def wilder_rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder'in üssel yumuşatması (RSI/ATR için)."""
    alpha = 1.0 / period
    return series.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = wilder_rma(gain, period)
    avg_loss = wilder_rma(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss != 0, 100.0)  # tamamen kayıpsız -> 100
    return out


def stoch_rsi(close: pd.Series, rsi_len: int, stoch_len: int, smooth_k: int) -> pd.Series:
    r = rsi(close, rsi_len)
    lo = r.rolling(stoch_len).min()
    hi = r.rolling(stoch_len).max()
    stoch = (r - lo) / (hi - lo).replace(0.0, np.nan) * 100.0
    k = stoch.rolling(smooth_k).mean()  # SMA(smoothK)
    return k


def macd_lines(close_fast_src: pd.Series, close_slow_src: pd.Series,
               fast: int, slow: int, signal: int):
    macd_line = ema(close_fast_src, fast) - ema(close_slow_src, slow)
    signal_line = sma(macd_line, signal)
    return macd_line, signal_line


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return wilder_rma(tr, period)


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int, multiplier: float) -> pd.Series:
    """
    Standart Supertrend. trend = +1 (yukarı) / -1 (aşağı) döndürür.
    """
    n = len(close)
    hl2 = (high + low) / 2.0
    atr = atr_wilder(high, low, close, period)
    up = hl2 - multiplier * atr
    dn = hl2 + multiplier * atr

    trend = pd.Series(1, index=close.index, dtype="float64")
    final_up = pd.Series(np.nan, index=close.index, dtype="float64")
    final_dn = pd.Series(np.nan, index=close.index, dtype="float64")
    final_up.iloc[0] = up.iloc[0]
    final_dn.iloc[0] = dn.iloc[0]

    for i in range(1, n):
        # Üst bant
        if close.iloc[i - 1] > final_up.iloc[i - 1]:
            final_up.iloc[i] = max(up.iloc[i], final_up.iloc[i - 1])
        else:
            final_up.iloc[i] = up.iloc[i]
        # Alt bant
        if close.iloc[i - 1] < final_dn.iloc[i - 1]:
            final_dn.iloc[i] = min(dn.iloc[i], final_dn.iloc[i - 1])
        else:
            final_dn.iloc[i] = dn.iloc[i]
        # Trend yönü
        if close.iloc[i] > final_up.iloc[i - 1]:
            trend.iloc[i] = 1
        elif close.iloc[i] < final_dn.iloc[i - 1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1]
            if trend.iloc[i] == 1 and final_dn.iloc[i] > final_dn.iloc[i - 1]:
                final_dn.iloc[i] = final_dn.iloc[i - 1]
            if trend.iloc[i] == -1 and final_up.iloc[i] < final_up.iloc[i - 1]:
                final_up.iloc[i] = final_up.iloc[i - 1]
    return trend


def _src(df: pd.DataFrame, name: str) -> pd.Series:
    name = (name or "close").lower()
    if name == "hl2":
        return (df["High"] + df["Low"]) / 2.0
    if name == "ohlc4":
        return (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4.0
    if name in ("open", "high", "low", "close"):
        return df[name.capitalize()]
    return df["Close"]


# ----------------------------------------------------------------------
# Sinyal üretimi
# ----------------------------------------------------------------------
def _cross_up(a: pd.Series, b: pd.Series) -> bool:
    """a, b'yi son bar'da yukarı kırdı mı?"""
    return bool(a.iloc[-1] > b.iloc[-1] and a.iloc[-2] <= b.iloc[-2])


def _cross_down(a: pd.Series, b: pd.Series) -> bool:
    return bool(a.iloc[-1] < b.iloc[-1] and a.iloc[-2] >= b.iloc[-2])


def _cross_above_level(s: pd.Series, level: float) -> bool:
    """Seri son bar'da seviyeyi aşağıdan yukarı kırdı mı?"""
    return bool(s.iloc[-1] > level and s.iloc[-2] <= level)


def _cross_below_level(s: pd.Series, level: float) -> bool:
    return bool(s.iloc[-1] < level and s.iloc[-2] >= level)


def evaluate(df: pd.DataFrame, cfg: dict) -> dict:
    """
    Son bar için 5 göstergenin long/short sinyallerini ve ağırlıklı skoru döndürür.
    Yetersiz veri varsa {'valid': False} döner.
    """
    min_bars = 120  # en uzun MA (82) + tampon
    if df is None or len(df) < min_bars:
        return {"valid": False, "reason": f"Yetersiz bar ({len(df) if df is not None else 0} < {min_bars})"}

    s = cfg["strategy"]
    price = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])

    signals_long = {}
    signals_short = {}

    # --- 1) MACD ---
    if s["macd"]["enabled"]:
        fast_src = _src(df, s["macd_params"]["fast_source"])
        slow_src = _src(df, s["macd_params"]["slow_source"])
        mp = s["macd_params"]
        macd_line, signal_line = macd_lines(
            fast_src, slow_src, mp["fast_period"], mp["slow_period"], mp["signal_period"]
        )
        signals_long["MACD"] = _cross_up(macd_line, signal_line)
        signals_short["MACD"] = _cross_down(macd_line, signal_line)

    # --- 2) Stochastic RSI ---
    if s["stoch_rsi"]["enabled"]:
        sp = s["stoch_rsi_params"]
        k = stoch_rsi(df["Close"], sp["rsi_length"], sp["stoch_length"], sp["smooth_k"])
        # Long: aşırı satımdan (oversold) yukarı kırılım
        signals_long["StochRSI"] = _cross_above_level(k, sp["oversold"])
        # Short: aşırı alımdan (overbought) aşağı kırılım
        signals_short["StochRSI"] = _cross_below_level(k, sp["overbought"])

    # --- 3) RSI ---
    if s["rsi"]["enabled"]:
        rp = s["rsi_params"]
        r = rsi(df["Close"], rp["length"])
        signals_long["RSI"] = _cross_above_level(r, rp["oversold"])
        signals_short["RSI"] = _cross_below_level(r, rp["overbought"])

    # --- 4) Supertrend ---
    if s["supertrend"]["enabled"]:
        stp = s["supertrend_params"]
        src = _src(df, stp["source"])
        trend = supertrend(df["High"], df["Low"], src, stp["atr_period"], stp["multiplier"])
        # Flip yukarı: önceki -1, şimdi +1
        signals_long["Supertrend"] = bool(trend.iloc[-1] == 1 and trend.iloc[-2] == -1)
        signals_short["Supertrend"] = bool(trend.iloc[-1] == -1 and trend.iloc[-2] == 1)

    # --- 5) MA Cross ---
    if s["ma_cross"]["enabled"]:
        mcp = s["ma_cross_params"]
        f = ema if mcp["fast_type"].upper() == "EMA" else sma
        sl = ema if mcp["slow_type"].upper() == "EMA" else sma
        ma_fast = f(_src(df, mcp["fast_source"]), mcp["fast_period"])
        ma_slow = sl(_src(df, mcp["slow_source"]), mcp["slow_period"])
        signals_long["MACross"] = _cross_up(ma_fast, ma_slow)
        signals_short["MACross"] = _cross_down(ma_fast, ma_slow)

    # --- Ağırlıklı skor ---
    # Sinyal sözlüğü anahtarları -> config anahtarları
    NAME_TO_CFG = {
        "MACD": "macd",
        "StochRSI": "stoch_rsi",
        "RSI": "rsi",
        "Supertrend": "supertrend",
        "MACross": "ma_cross",
    }

    def _score(direction_signals: dict) -> float:
        total = 0.0
        for name, sig in direction_signals.items():
            key = NAME_TO_CFG.get(name)
            if key is None:
                continue
            w = s[key]["weight"]
            if sig:
                total += w
        return total

    long_score = _score(signals_long) if s.get("allow_longs", True) else -1
    short_score = _score(signals_short) if s.get("allow_shorts", True) else -1

    trigger = s["weight_trigger"]
    direction = None
    score = 0.0
    if s.get("allow_longs", True) and long_score >= trigger:
        direction = "LONG"
        score = long_score
    elif s.get("allow_shorts", True) and short_score >= trigger:
        direction = "SHORT"
        score = short_score

    # --- Risk referans seviyeleri ---
    rp_risk = cfg.get("risk", {})
    sl_pct = rp_risk.get("stoploss_pct", 6.0) / 100.0
    tp_pct = rp_risk.get("take_profit_pct", 6.8) / 100.0
    max_tp = int(rp_risk.get("max_tp", 6))

    if direction == "LONG":
        sl_price = price * (1 - sl_pct)
        tp_prices = [price * (1 + i * tp_pct) for i in range(1, max_tp + 1)]
    elif direction == "SHORT":
        sl_price = price * (1 + sl_pct)
        tp_prices = [price * (1 - i * tp_pct) for i in range(1, max_tp + 1)]
    else:
        sl_price = None
        tp_prices = []

    fired_long = [k for k, v in signals_long.items() if v]
    fired_short = [k for k, v in signals_short.items() if v]

    return {
        "valid": True,
        "price": price,
        "prev_close": prev_close,
        "date": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        "direction": direction,
        "score": score,
        "trigger": trigger,
        "long_score": long_score,
        "short_score": short_score,
        "signals_long": signals_long,
        "signals_short": signals_short,
        "fired_long": fired_long,
        "fired_short": fired_short,
        "sl_price": sl_price,
        "tp_prices": tp_prices,
    }
