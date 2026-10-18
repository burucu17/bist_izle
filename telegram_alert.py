"""
Telegram bildirim gönderici (Bot API, tek yönlü).
Token ve chat_id: .env veya config.yaml -> telegram altından alınır.
"""
from __future__ import annotations

import os

import requests


def _resolve_credentials(cfg: dict):
    token = os.getenv("TELEGRAM_TOKEN") or cfg.get("telegram", {}).get("bot_token", "")
    chat_id = os.getenv("CHAT_ID") or cfg.get("telegram", {}).get("chat_id", "")
    return token, chat_id


def send_message(text: str, cfg: dict) -> bool:
    """
    Mesajı Telegram'a gönderir. Başarılıysa True döner.
    Token/chat_id eksikse False döner (çağıran konsola yazar).
    """
    token, chat_id = _resolve_credentials(cfg)
    if not token or not chat_id:
        print("[Telegram] Token veya chat_id eksik -> mesaj gönderilemedi.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print(f"[Telegram] Hata {r.status_code}: {r.text}")
            return False
        return True
    except Exception as e:
        print(f"[Telegram] Gönderim hatası: {e}")
        return False


def format_signal(ticker: str, res: dict) -> str:
    """Sinyal sonucunu okunabilir Telegram mesajına çevirir."""
    d = res["direction"]
    emoji = "📈" if d == "LONG" else "📉"
    title = "UZUN (AL)" if d == "LONG" else "KISA (SAT)"
    fired = res["fired_long"] if d == "LONG" else res["fired_short"]

    lines = [
        f"{emoji} BIST SİNYALİ: {ticker}",
        f"Yön: {title}",
        f"Skor: {res['score']:.0f} / 5   (eşik {res['trigger']})",
        f"Fiyat: {res['price']:.2f}  ({res['date']})",
        f"Tetikleyen: {', '.join(fired) if fired else '-'}",
    ]

    if res["sl_price"] is not None:
        lines.append(f"Referans SL: {res['sl_price']:.2f}")
        tp_str = " | ".join(f"TP{i+1}: {p:.2f}" for i, p in enumerate(res["tp_prices"]))
        lines.append(f"Referans {tp_str}")

    lines.append("—")
    lines.append("Bilgi amaçlıdır, yatırım tavsiyesi değildir.")
    return "\n".join(lines)
