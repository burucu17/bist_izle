"""
Tarayıcı: tüm izlenen hisseleri tara, sinyal üretenleri topla.
"""
from __future__ import annotations

import time

from data_feed import fetch, get_tickers
from strategy import evaluate


def scan_all(cfg: dict, interval: str | None = None, period: str | None = None,
             progress: bool = True) -> list[tuple[str, dict]]:
    """
    Tüm hisseleri tarar ve sinyal verenleri (direction != None) döndürür.
    Dönüş: [(ticker, result_dict), ...]
    """
    tickers = get_tickers(cfg)
    if not tickers:
        print("[Tarayıcı] İzlenecek hisse bulunamadı (watchlist boş ve BIST30 kapalı).")
        return []

    interval = interval or cfg.get("timeframe", {}).get("interval", "1d")
    period = period or cfg.get("timeframe", {}).get("period", "2y")

    signals = []
    total = len(tickers)
    for i, tk in enumerate(tickers, 1):
        if progress:
            print(f"  ({i}/{total}) {tk} taranıyor...")
        df = fetch(tk, interval=interval, period=period)
        if df is None:
            continue
        res = evaluate(df, cfg)
        if not res.get("valid", False):
            if progress:
                print(f"    -> geçersiz: {res.get('reason')}")
            continue
        if res["direction"] is not None:
            signals.append((tk, res))
            if progress:
                print(f"    -> SİNYAL: {res['direction']} (skor {res['score']:.0f})")
        else:
            if progress:
                ls, ss = res["long_score"], res["short_score"]
                print(f"    -> sinyal yok (L={ls:.0f}, S={ss:.0f})")
        # Yahoo rate-limit'e takılmamak için küçük bekleme
        time.sleep(0.3)

    return signals
