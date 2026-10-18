# BIST Weighted Strategy (Telegram Bildirimli)

[AlbertoCuadra/algo_trading_weighted_strategy](https://github.com/AlbertoCuadra/algo_trading_weighted_strategy)
(Pine Script / TradingView) stratejisinin **BIST hisselerine uyarlanmış Python** sürümü.

Orijinal mantık aynen korundu: **5 gösterge** (MACD, Stochastic RSI, RSI, Supertrend,
MA Cross) ayrı ayrı sinyal üretir, her birine verilen **ağırlık** toplanır; toplam
**eşik değerini (vars. 2/5)** geçerse **LONG** veya **SHORT** sinyali oluşur. Sistem
**sadece sinyal üretir**, otomatik alım-satım yapmaz. Her sinyal **Telegram**'a düşer.

> ⚠️ Bilgi amaçlıdır, yatırım tavsiyesi değildir. Stratejiyi kendi hissenize göre
> optimize edip geçmişe dönük test etmeden gerçek para kullanmayın.

---

## 1) Gereksinimler

- Python 3.10+ (3.11 önerilir)
- İnternet (Yahoo Finance verisi + Telegram API)

## 2) Kurulum

```bash
cd bist_weighted_strategy
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 3) Telegram botu oluşturma

1. Telegram'da [@BotFather](https://t.me/BotFather) aç.
2. `/newbot` → isim ve kullanıcı adı ver → **token** al (ör: `123456:ABC-...`).
3. Botu bir sohbete/kanalda ekleyip bir mesaj gönder.
4. **Chat ID öğrenme:**
   - Kişisel sohbet: [@userinfobot](https://t.me/userinfobot) size chat id'yi verir.
   - Kanal: kanalı oluştur, botu yönetici yap, mesaj yaz; sonra
     `https://api.telegram.org/bot<TOKEN>/getUpdates` adresine bak, `chat.id` değeri al.

## 4) Yapılandırma

İki yerden ayar yapılır:

**a) `.env` (gizli bilgiler)** — `.env.example` dosyasını `.env` yap ve doldur:

```ini
TELEGRAM_BOT_TOKEN=123456:ABC-DEF....
TELEGRAM_CHAT_ID=987654321
```

**b) `config.yaml`** — tüm strateji ayarları burada:

- `watchlist`: Kendi BIST hisselerini yaz (MUTLAKA `.IS` soneki):
  ```yaml
  watchlist:
    - THYAO.IS
    - GARAN.IS
    - ASELS.IS
  ```
  Boş bırakırsan otomatik **BIST30** listesine düşer.
- `strategy.weight_trigger`: Kaç gösterge uymalı? (vars. 2)
- `strategy.*.weight`: Her göstergenin ağırlığı (0=kapatır)
- Gösterge parametreleri (MACD periyotları, RSI seviyeleri, Supertrend çarpanı vb.)
- `risk`: SL / TP yüzdeleri (sadece **referans** olarak mesajda gösterilir)

> 💡 Orijinal değerler 4s BTC için ayarlanmıştı. Günlük BIST için `config.yaml`
> içindeki parametreleri kendi hissenize göre optimize etmen iyi olur (backtest şart).

## 5) Çalıştırma

```bash
# Normal tarama (sinyalleri Telegram'a gönderir)
python run_scan.py

# Önce Telegram bağlantısını test et
python run_scan.py --test-telegram

# Telegram'a göndermeden sadece konsola yaz (test)
python run_scan.py --dry-run
```

### Zamanlanmış çalıştırma (önerilen)

Günde 1 kez, BIST seansı kapandıktan sonra (TSI ~18:00) çalıştır:

- **Windows:** Görev Zamanlayıcı → Günlük, 18:00, eylem:
  `python "C:\...\bist_weighted_strategy\run_scan.py"`
- **Linux/macOS cron:**
  ```cron
  0 18 * * 1-5 cd /yol/bist_weighted_strategy && /yol/.venv/bin/python run_scan.py
  ```

## 6) Çıktı örneği (Telegram)

```
📈 BIST SİNYALİ: THYAO.IS
Yön: Uzun (AL)
Skor: 3 / 5   (eşik 2)
Fiyat: 312.40  (2026-10-17)
Tetikleyen: MACD, StochRSI, MACross
Referans SL: 293.66
Referans TP1: 333.64 | TP2: 354.87 | ...
—
Bilgi amaçlıdır, yatırım tavsiyesi değildir.
```

## 7) Dosya yapısı

```
bist_weighted_strategy/
├── config.yaml          # Tüm strateji + hisse ayarları
├── run_scan.py          # Çalıştırma giriş noktası
├── scanner.py           # Tüm hisseleri tara, sinyal topla
├── strategy.py          # 5 gösterge + ağırlıklı skor mantığı
├── data_feed.py         # Yahoo Finance (.IS) veri çekme
├── telegram_alert.py    # Telegram gönderici + mesaj formatı
├── requirements.txt
├── .env.example         # Token & chat_id şablonu
└── README.md
```

## 8) Önemli notlar

- **Veri kaynağı:** Yahoo Finance ücretsizdir ama bazen gecikmeli/eksik olabilir.
  Daha stabil istersen ücretli bir sağlayıcıya (ör. investing, matbah veri sağlayıcıları)
  geçilebilir — `data_feed.py` içindeki `fetch()` fonksiyonunu değiştirmen yeterli.
- **Kısa (SHORT) sinyaller:** Hisse piyasasında açığa satış kuralları farklıdır;
  `strategy.allow_shorts: false` yaparsan sadece AL sinyali üretir.
- **Aşırı uyum (overfitting) riski:** Parametreleri rastgele değiştirme; geçmiş
  dönemlerde test et. Orijinal repo da bunu açıkça uyarıyor.
