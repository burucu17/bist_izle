#!/usr/bin/env python3
"""
BIST Weighted Strategy - Çalıştırma giriş noktası

Kullanım:
  python run_scan.py                 # normal tarama (Telegram'a gönderir)
  python run_scan.py --dry-run       # sadece konsola yazar, Telegram'a GÖNDERMEZ
  python run_scan.py --test-telegram # Telegram bağlantısını test eder
  python run_scan.py --once          # tek seferlik tarama

Zamanlanmış çalıştırma (önerilen):
  - Windows Görev Zamanlayıcı veya cron ile günde 1 kez (seans kapanışı sonrası) çalıştır.
  - Örnek cron (TSI ~18:30): 30 18 * * 1-5 cd /yol/bist_weighted_strategy && python run_scan.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import yaml
from dotenv import load_dotenv

import telegram_alert as tg
from scanner import scan_all

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_summary(signals: list[tuple[str, dict]]) -> str:
    if not signals:
        return "🔍 BIST Taraması\nBugün sinyal oluşmadı."
    lines = [f"🔍 BIST Taraması — {len(signals)} sinyal\n"]
    for tk, res in signals:
        d = "AL 📈" if res["direction"] == "LONG" else "SAT 📉"
        lines.append(f"• {tk}: {d}  (skor {res['score']:.0f})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="BIST Weighted Strategy Tarayıcı")
    parser.add_argument("--dry-run", action="store_true", help="Telegram'a gönderme, sadece konsol")
    parser.add_argument("--test-telegram", action="store_true", help="Telegram bağlantısını test et")
    parser.add_argument("--once", action="store_true", help="Tek seferlik tarama")
    args = parser.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    cfg = load_config()

    # dry-run config üzerinden mi?
    dry_run = args.dry_run or cfg.get("run", {}).get("dry_run", False)

    if args.test_telegram:
        ok = tg.send_message("✅ Telegram bağlantısı çalışıyor! BIST Weighted Strategy hazır.", cfg)
        print("Test mesajı gönderildi." if ok else "Test mesajı GÖNDERİLEMEDİ (token/chat_id kontrol et).")
        return

    print("=== BIST Weighted Strategy taraması başladı ===")
    signals = scan_all(cfg)

    if not signals:
        msg = build_summary(signals)
        print(msg)
        if not dry_run:
            tg.send_message(msg, cfg)
        return

    print(f"\n{len(signals)} sinyal bulundu.")
    for tk, res in signals:
        text = tg.format_signal(tk, res)
        print("\n" + text)
        if not dry_run:
            tg.send_message(text, cfg)
            time.sleep(0.5)  # Telegram rate-limit

    # Özet mesaj
    summary = build_summary(signals)
    if not dry_run:
        tg.send_message(summary, cfg)

    print("\n=== Tarama bitti ===")


if __name__ == "__main__":
    sys.exit(main())
