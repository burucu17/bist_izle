#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BIST interaktif Telegram botu.

izle.py'nin sadece "push" yapan halinin aksine bu, gercek bir Telegram botudur:
hem sohbet edilebilir (mesaj atarsin, o yanit verir) hem de her gun otomatik
sinyal ozeti gonderir.

Komutlar:
  /start            -> karsilama ve komut listesi
  /sinyal ASELS     -> o hissenin anlik sinyalini soyler (AL / SAT / NONE)
  /sinyal ASELS ema -> farkli stratejiyle (ema = trend_ema_adx)
  /list             -> izleme listesindeki hisselerin son sinyali
  /indir            -> tum liste icin (veya /indir ASELS) veriyi tazeler
  /gunluk           -> manuel olarak gunluk sinyal ozetini gonderir
  /durum            -> bot ve ayar ozeti
  /help             -> bu yardim

Kurulum:
  1) Telegram'da @BotFather -> /newbot ile bir bot olustur, token al.
  2) Bot'a bir kez mesaj yaz.
  3) izle_config.json icine:
       "telegram_bot_token": "<token>",
       "telegram_chat_id":  "<chat id>"   (bos birakirsan bot ilk /start'da ogrenir)
  4) Bot'u calistir:  .venv/Scripts/python.exe bot.py
     Gunluk otomatik ozet icin ayar: "gunluk_saat": "18:15" (varsayilan)

Not: BILGISAYARIN O SAATTE ACIK OLMALI. 7/24 icin ileride bulut sunucuya tasinabilir.
"""
from __future__ import annotations

import os
import sys
import json
import datetime
import threading
import time
import traceback

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

import pandas as pd
from strategy import get_strategy  # HyperView strateji cercevesi

# izle.py'deki hazir yardimcilar (config, liste, veri cekme, gonderme)
from izle import (
    load_config, load_watchlist, download, csv_path,
    send_telegram, build_message, load_json, save_json, STATE_PATH,
)

BOT_STATE_PATH = os.path.join(REPO, "bot_durum.json")

# Desteklenen stratejiler ve okunur adlari
STRATEJI_ADLARI = {
    "weighted": "weighted_ensemble",
    "ema": "trend_ema_adx",
}
STRATEJI_DEFAULT = "weighted"


def log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Sinyal hesabi (herhangi bir stratejiyle)
# ---------------------------------------------------------------------------

def get_signal(symbol: str, strategy_name: str, cfg: dict):
    """Sembolun son bardaki sinyalini hesaplar: ('AL'|'SAT'|None, detay_dict|hata)."""
    path = csv_path(symbol, cfg)
    if not os.path.exists(path):
        return None, "veri yok (once /indir ile veri cek)"
    df = pd.read_csv(path)
    if len(df) < 60:
        return None, "yeterli veri yok"
    try:
        strat = get_strategy(strategy_name)
    except KeyError:
        return None, f"strateji bulunamadi: {strategy_name}"
    settings = {
        "enable_long": True,
        "enable_short": True,
        "start": cfg.get("start"),
        "end": None,
    }
    out = strat.generate_signals(df, settings)
    if len(out) < 2:
        return None, "yeterli veri yok"
    last = out.iloc[-1]
    prev = out.iloc[-2]
    sig = None
    if bool(last["buy_signal"]) and not bool(prev["buy_signal"]):
        sig = "AL"
    elif bool(last["sell_signal"]) and not bool(prev["sell_signal"]):
        sig = "SAT"
    dt = datetime.datetime.fromtimestamp(int(last["time"]), datetime.timezone.utc).strftime("%Y-%m-%d")
    detay = {"signal": sig, "date": dt, "close": float(last["close"]), "symbol": symbol}
    return sig, detay


def resolve_symbol(text: str) -> str:
    s = text.strip().upper()
    if not s:
        return ""
    if ":" not in s:
        s = "BIST:" + s
    return s


def resolve_strategy(token_text: str) -> str:
    t = (token_text or "").strip().lower()
    return STRATEJI_ADLARI.get(t, STRATEJI_ADLARI[STRATEJI_DEFAULT])


# ---------------------------------------------------------------------------
# Gunluk ozet (push) - izle.py mantigi, secilen stratejiyle
# ---------------------------------------------------------------------------

def daily_digest(cfg: dict, strategy_key: str = STRATEJI_DEFAULT) -> str:
    strategy_name = STRATEJI_ADLARI.get(strategy_key, STRATEJI_ADLARI[STRATEJI_DEFAULT])
    symbols = load_watchlist()
    if not symbols:
        return "Izleme listesi bos (izle_liste.txt)."
    state = load_json(BOT_STATE_PATH, {})
    try:
        download(symbols, cfg)
    except Exception as e:
        log(f"[gunluk] veri indirme hatasi: {e}")
    buys, sells = [], []
    scanned = 0
    for sym in symbols:
        scanned += 1
        try:
            sig, detay = get_signal(sym, strategy_name, cfg)
        except Exception as e:
            log(f"[gunluk] {sym} hata: {e}")
            continue
        if isinstance(detay, str):  # hata mesaji
            continue
        cur = sig or "NONE"
        prev_state = state.get(sym, "NONE")
        if cur in ("AL", "SAT") and cur != prev_state:
            entry = {"symbol": sym, "close": detay["close"], "date": detay["date"]}
            (buys if cur == "AL" else sells).append(entry)
        state[sym] = cur
    save_json(BOT_STATE_PATH, state)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    msg = build_message(date_str, buys, sells, scanned)
    etiket = STRATEJI_ADLARI_INVERSE.get(strategy_name, strategy_name)
    msg = f"[{etiket}] " + msg
    return msg


STRATEJI_ADLARI_INVERSE = {v: k for k, v in STRATEJI_ADLARI.items()}


# ---------------------------------------------------------------------------
# Telegram bot
# ---------------------------------------------------------------------------

def build_bot(cfg: dict):
    token = str(cfg.get("telegram_bot_token", ""))
    if (not token) or ("BURAYA" in token):
        return None
    import telebot
    bot = telebot.TeleBot(token)

    allowed = str(cfg.get("telegram_chat_id", ""))
    allowed = None if (not allowed or "BURAYA" in allowed) else allowed

    def yetkili(msg) -> bool:
        if allowed is None:
            return True
        return str(msg.chat.id) == allowed

    @bot.message_handler(commands=["start", "help"])
    def cmd_start(msg):
        if not yetkili(msg):
            return
        metin = (
            "Merhaba! Ben BIST sinyal botuyum.\n"
            "Komutlar:\n"
            "  /sinyal ASELS  -> hissenin anlik sinyali (AL/SAT)\n"
            "  /sinyal ASELS ema -> baska stratejiyle\n"
            "  /list  -> izleme listesindeki hisselerin son sinyali\n"
            "  /indir  -> veriyi tazeler (tum liste)\n"
            "  /indir ASELS -> tek hisse verisi\n"
            "  /gunluk -> manuel gunluk ozet\n"
            "  /durum  -> ayar ozeti\n"
            "  /help   -> bu yardim"
        )
        if allowed is None:
            # ilk konusmadan chat id'yi ogren ve kaydet
            cid = str(msg.chat.id)
            cfg["telegram_chat_id"] = cid
            _save_cfg(cfg)
            metin += f"\n\n(chat id otomatik kaydedildi: {cid})"
        bot.reply_to(msg, metin)

    @bot.message_handler(commands=["sinyal"])
    def cmd_sinyal(msg):
        if not yetkili(msg):
            return
        parca = msg.text.split()
        if len(parca) < 2:
            bot.reply_to(msg, "Sembol yazin: /sinyal ASELS  (veya /sinyal ASELS ema)")
            return
        sym = resolve_symbol(parca[1])
        stra_key = parca[2] if len(parca) > 2 else STRATEJI_DEFAULT
        stra_name = resolve_strategy(stra_key)
        try:
            sig, detay = get_signal(sym, stra_name, cfg)
        except Exception as e:
            bot.reply_to(msg, f"Hata: {e}")
            return
        if isinstance(detay, str):
            bot.reply_to(msg, f"{sym}: {detay}")
            return
        if sig is None:
            yanit = f"{sym}\nSinyal: YOK (bekliyor)\nSon kapanis: {detay['close']:.2f}  ({detay['date']})"
        else:
            yanit = f"{sym}\nSinyal: {sig}\nKapanis: {detay['close']:.2f}  ({detay['date']})"
        yanit += f"\n(strateji: {stra_key})"
        bot.reply_to(msg, yanit)

    @bot.message_handler(commands=["list"])
    def cmd_list(msg):
        if not yetkili(msg):
            return
        symbols = load_watchlist()
        if not symbols:
            bot.reply_to(msg, "Izleme listesi bos.")
            return
        state = load_json(BOT_STATE_PATH, {})
        satirlar = [f"IZLEME LISTESI ({len(symbols)} hisse):"]
        for sym in symbols:
            son = state.get(sym, "-")
            satirlar.append(f"  {sym.split(':')[-1]:6s} -> {son}")
        bot.reply_to(msg, "\n".join(satirlar))

    @bot.message_handler(commands=["indir"])
    def cmd_indir(msg):
        if not yetkili(msg):
            return
        parca = msg.text.split()
        if len(parca) >= 2:
            syms = [resolve_symbol(parca[1])]
        else:
            syms = load_watchlist()
        if not syms:
            bot.reply_to(msg, "Indirilecek sembol yok.")
            return
        bot.reply_to(msg, f"Veri indiriliyor ({len(syms)} sembol)...")
        try:
            download(syms, cfg)
            bot.reply_to(msg, "Veri guncellendi.")
        except Exception as e:
            bot.reply_to(msg, f"Veri indirme hatasi: {e}")

    @bot.message_handler(commands=["gunluk"])
    def cmd_gunluk(msg):
        if not yetkili(msg):
            return
        bot.reply_to(msg, "Gunluk ozet hazirlaniyor...")
        try:
            metin = daily_digest(cfg)
        except Exception as e:
            bot.reply_to(msg, f"Hata: {e}")
            return
        # ayni zamanda push olarak da gonder
        send_telegram(cfg, metin)
        bot.reply_to(msg, metin)

    @bot.message_handler(commands=["durum"])
    def cmd_durum(msg):
        if not yetkili(msg):
            return
        stra = cfg.get("bot_strateji", STRATEJI_DEFAULT)
        saat = cfg.get("gunluk_saat", "18:15")
        metin = (
            "BOT DURUMU\n"
            f"  Strateji: {stra} ({STRATEJI_ADLARI.get(stra, STRATEJI_DEFAULT)})\n"
            f"  Gunluk ozet saati: {saat}\n"
            f"  Timeframe: {cfg.get('timeframe')} / {cfg.get('session')}\n"
            f"  Liste: {len(load_watchlist())} hisse\n"
            f"  Chat kilidi: {'var' if allowed else 'yok (herkese acik)'}"
        )
        bot.reply_to(msg, metin)

    return bot


def _save_cfg(cfg: dict) -> None:
    # izle_config.json'i guncelle (sadece bilinen anahtarlari koru)
    path = os.path.join(REPO, "izle_config.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"config kaydedilemedi: {e}")


# ---------------------------------------------------------------------------
# Gunluk otomatik push zamanlayici (basit thread)
# ---------------------------------------------------------------------------

def scheduler_loop(cfg: dict, stop_event: threading.Event):
    saat = str(cfg.get("gunluk_saat", "18:15"))
    try:
        hh, mm = saat.split(":")
        hh, mm = int(hh), int(mm)
    except Exception:
        hh, mm = 18, 15
    son_tetik_tarih = ""
    while not stop_event.is_set():
        now = datetime.datetime.now()
        bugun = now.strftime("%Y-%m-%d")
        if now.hour == hh and now.minute == mm and son_tetik_tarih != bugun:
            son_tetik_tarih = bugun
            log("[zamanlayici] gunluk ozet tetikleniyor...")
            try:
                stra = cfg.get("bot_strateji", STRATEJI_DEFAULT)
                metin = daily_digest(cfg, stra)
                ok = send_telegram(cfg, metin)
                log(f"[zamanlayici] gonderim: {ok}")
            except Exception as e:
                log(f"[zamanlayici] hata: {e}\n{traceback.format_exc()}")
        time.sleep(30)


# ---------------------------------------------------------------------------

def main() -> None:
    cfg = load_config()
    # bot'a ozel ayarlar (yoksa varsayilan ekle)
    cfg.setdefault("gunluk_saat", "18:15")
    cfg.setdefault("bot_strateji", STRATEJI_DEFAULT)
    # Bulut deploy icin: token/chat_id ortam degiskeninden de gelebilir
    # (dosyaya yazmak yerine gizli degisken olarak vermek daha guvenli).
    import os as _os
    ev_token = _os.environ.get("TELEGRAM_BOT_TOKEN")
    ev_chat = _os.environ.get("TELEGRAM_CHAT_ID")
    if ev_token:
        cfg["telegram_bot_token"] = ev_token
    if ev_chat:
        cfg["telegram_chat_id"] = ev_chat
    _save_cfg(cfg)

    token = str(cfg.get("telegram_bot_token", ""))
    if (not token) or ("BURAYA" in token):
        print("ONCE izle_config.json icine gercek bot token'ini yazin:")
        print('  "telegram_bot_token": "123456:ABC..."')
        print("Sonra: .venv/Scripts/python.exe bot.py")
        return

    bot = build_bot(cfg)
    if bot is None:
        print("Bot olusturulamadi (token gecersiz olabilir).")
        return

    # --- Sadece gunluk ozet modu (GitHub Actions / tek seferlik calistirma) ---
    # Uzun sureli poll YAPMAZ; ozeti gonderip cikar. Interaktif sohbet gerekmez.
    if "--digest" in sys.argv[1:]:
        log("Gunluk ozet modu: sadece ozet gonderiliyor, cikiliyor.")
        try:
            stra = cfg.get("bot_strateji", STRATEJI_DEFAULT)
            metin = daily_digest(cfg, stra)
            ok = send_telegram(cfg, metin)
            log(f"Gunluk ozet gonderildi: {ok}")
        except Exception as e:
            log(f"Gunluk ozet hatasi: {e}\n{traceback.format_exc()}")
        return

    # 409 "Conflict" onarimi: daha once kalmis bir webhook varsa sil.
    # (Webhook aktifken getUpdates/long-polling 409 verir.)
    try:
        bot.delete_webhook(drop_pending_updates=True)
        log("Varsa eski webhook silindi.")
    except Exception as e:
        log(f"Webhook silme uyari: {e}")

    stop_event = threading.Event()
    t = threading.Thread(target=scheduler_loop, args=(cfg, stop_event), daemon=True)
    t.start()
    log("Bot baslatildi. /start komutunu Telegram'dan gonderin.")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
            break  # normal cikis
        except Exception as e:
            err = str(e)
            if "409" in err or "Conflict" in err:
                # Ayni token ile baska bir bot oturumu acik olabilir.
                log("HATA 409 (Conflict): Ayni bot zaten calisiyor olabilir. "
                    "Diger örnekleri kapatip tekrar deneyin. 15 sn bekleniyor...")
                import time as _t
                _t.sleep(15)
                continue
            log(f"Bot durdu: {e}\n{traceback.format_exc()}")
            break
    stop_event.set()


if __name__ == "__main__":
    main()
