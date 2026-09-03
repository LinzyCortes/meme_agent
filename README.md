# Meme Token AI Agent (Gratis)

Sistem 5 agent buat riset meme coin:

1. **Smart Money Finder** (`smart_money_finder.py`) — **otomatis nemuin wallet whale/smart money sendiri**, tanpa lo perlu cari & isi manual. Caranya: cari token yang lagi "menang" (harga naik signifikan), telusuri siapa yang beli paling awal, lalu wallet yang berulang kali beli awal di beberapa token pemenang berbeda ditandai sebagai kandidat smart money.
2. **Wallet Tracker** (`wallet_tracker.py`) — pantau wallet (baik yang lo isi manual, maupun hasil temuan otomatis Agent 1), notif kalau mereka buy/sell token.
3. **Token Screener** (`token_screener.py`) — scan token baru/trending yang market cap-nya masih kecil tapi punya sinyal bagus.
4. **Deep Analysis** (`deep_analysis.py`) — begitu screener nemu kandidat, otomatis dianalisa: cek kontrak, konsentrasi holder, liquidity lock, dan sosial media project-nya.
5. **Performance Tracker** (`performance_tracker.py`) — nyatet harga/mcap tiap token PAS PERTAMA KALI ditemuin, terus ngecek ulang berkala buat liat udah naik/turun berapa kali lipat. Ini yang jawab pertanyaan "apakah rekomendasi sistem ini beneran valid" dengan data konkret, bukan tebak-tebakan.

Semua notifikasi dikirim ke **Telegram**, dan semua API yang dipakai **gratis**.

> ⚠️ **Disclaimer**: Ini alat bantu riset & monitoring, BUKAN sinyal beli/jual otomatis dan bukan saran finansial. Meme coin sangat berisiko tinggi (rug pull, honeypot, volatilitas ekstrem). Selalu DYOR (Do Your Own Research) dan jangan invest lebih dari yang lo rela kehilangan.

---

## 1. Setup Awal

```bash
git clone <repo-lo>   # atau langsung pakai folder ini
cd meme_agent
pip install -r requirements.txt
cp .env.example .env
```

## 2. Isi API Key (semua gratis)

Buka `.env`, isi:

| Variabel | Cara dapat | Kegunaan |
|---|---|---|
| `SOLANA_RPC_URL` | **Tidak wajib diisi** — default sudah pakai RPC publik gratis. Kalau mau lebih stabil (opsional), daftar RPC gratis di [dev.helius.xyz](https://dev.helius.xyz), [quicknode.com](https://quicknode.com), atau [ankr.com](https://ankr.com), lalu isi URL-nya. | Tracking wallet Solana |
| `ETHERSCAN_API_KEY` | Daftar di [etherscan.io/apis](https://etherscan.io/apis), buat API key. Key ini juga jalan untuk Base, Arbitrum, dll (API v2 unified). Free tier-nya cukup besar (5 request/detik, tanpa batas bulanan yang ketat). | Tracking wallet EVM |
| `TELEGRAM_BOT_TOKEN` | Chat `@BotFather` di Telegram → `/newbot` → ikuti instruksi | Kirim notifikasi |
| `TELEGRAM_CHAT_ID` | Chat bot lo sekali, lalu buka `https://api.telegram.org/bot<TOKEN>/getUpdates`, cari `"chat":{"id": ...}` | Tujuan notifikasi |

Token/market data (DexScreener, GeckoTerminal) dan security check (GoPlus) **tidak butuh API key sama sekali**.

### ⚠️ Soal tracking wallet Solana & kuota gratis

Awalnya modul ini dirancang pakai **Helius Enhanced Transactions API**, tapi itu boros credit (~100 credit/request) — kalau dipantau tiap 15 menit, 100k credit/bulan gratisnya abis dalam hitungan **hari**, bukan bulan. Makanya sekarang **default-nya pakai RPC standar Solana** (`getSignaturesForAddress` + `getTransaction`) via endpoint publik yang **100% gratis, tanpa API key, tanpa limit bulanan** — trade-off-nya cuma rate limit per detik yang lebih ketat (sudah di-handle dengan jeda antar request di kode).

Kalau nanti endpoint publik kerasa nggak stabil / sering timeout, ganti `SOLANA_RPC_URL` di `.env` ke RPC gratis dari provider (Helius/QuickNode/Ankr) — ini beda dari "Enhanced API", jadi jauh lebih hemat (~1 credit/request, bukan ~100), dan nggak perlu gonta-ganti akun tiap kuota abis.

## 3. Wallet yang Dipantau — Manual (opsional) + Otomatis

**Lo TIDAK wajib isi wallet manual lagi.** Kalau mau full otomatis:

```bash
python smart_money_finder.py
```

Ini bakal cari & simpan wallet smart money ke `discovered_wallets.json`, dan `wallet_tracker.py` otomatis bakal ikut mantau wallet-wallet itu (digabung kalau lo juga isi manual). Jalankan berkala (misal 1x tiap beberapa jam) — sudah disiapkan jadwalnya sendiri di GitHub Actions (`smart_money_finder.yml`, tiap 6 jam).

Kalau lo **tetap mau** tambah wallet manual (misal ada whale spesifik yang lo tau dari luar), edit `config.py`, bagian `WATCHED_WALLETS`:

```python
WATCHED_WALLETS = [
    {"label": "Whale Solana A", "chain": "solana", "address": "ALAMAT_WALLET"},
    {"label": "Whale Base B", "chain": "base", "address": "0xALAMAT_WALLET"},
]
```

> Catatan soal akurasi: deteksi otomatis ini heuristik (nyari pola "beli awal di token yang lalu pump"), bukan indikator pasti. Atur `SMART_MONEY_SETTINGS["min_appearances"]` di `config.py` — makin tinggi angkanya, makin ketat filternya (wallet harus konsisten beli awal di lebih banyak token pemenang), makin bisa dipercaya tapi makin sedikit yang ketemu.

## 4. Atur Kriteria Screener (opsional, sudah ada default)

Masih di `config.py`, bagian `SCREENER_FILTERS` — atur batas market cap, liquidity, volume, umur token, dll sesuai selera risiko lo.

## 5. Jalankan

**Sekali jalan (test dulu):**
```bash
python main.py once
```

**Mode terus-menerus (di laptop/PC/server sendiri):**
```bash
python main.py loop
```

**Jalankan agent satuan:**
```bash
python smart_money_finder.py     # agent 4: auto-discover wallet smart money
python wallet_tracker.py         # agent 1: cek wallet (manual + hasil auto-discovery)
python token_screener.py         # agent 2 + otomatis trigger agent 3 utk kandidat baru + mulai tracking performa
python deep_analysis.py solana <pool_address>   # analisa manual 1 token
python performance_tracker.py    # agent 5: update performa semua token yang lagi dipantau + tampilin ringkasan statistik
```

## Performance Tracker — cara baca hasilnya

Tiap kali `python performance_tracker.py` dijalanin, di akhir bakal muncul ringkasan kayak gini:

```
=== RINGKASAN PERFORMA SEMUA TOKEN YANG PERNAH DIREKOMENDASIIN ===
Total token yang pernah dipantau: 24
  Pernah nyampe 2x titik awal: 9 token (37.5%)
  Pernah nyampe 5x titik awal: 3 token (12.5%)
  Pernah nyampe 10x titik awal: 1 token (4.2%)
  Kemungkinan rug/ditinggal: 6 token (25.0%)
```

Ini angka KONKRET buat evaluasi seberapa valid sistem screening-nya - bukan tebak-tebakan. Makin lama sistemnya jalan (apalagi kalau udah di GitHub Actions), makin banyak data & makin akurat gambarannya. Token yang udah dipantau lebih dari `tracking_window_days` (default 14 hari, atur di `config.py`) otomatis "lulus" observasi dan hasil akhirnya kesimpen buat statistik ini.

Notifikasi Telegram juga otomatis masuk tiap kali ada token yang nembus milestone (2x, 3x, 5x, 10x, 20x, 50x, 100x) dari titik pertama ditemuin.

## 6. Biar Jalan Otomatis 24/7 GRATIS (tanpa PC nyala terus)

Sudah disiapkan **2 GitHub Actions workflow**:
- `run_agent.yml` — jalanin wallet tracker + screener + deep analysis tiap 15 menit
- `smart_money_finder.yml` — jalanin auto-discovery wallet smart money tiap 6 jam (lebih jarang karena lebih berat request-nya)

Gratis untuk repo publik (atau ~2000 menit/bulan gratis untuk repo privat).

Langkah:
1. Push folder ini ke repo GitHub baru.
2. Buka repo → **Settings → Secrets and variables → Actions → New repository secret**, tambahkan secret: `ETHERSCAN_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (dan `SOLANA_RPC_URL` kalau lo pakai RPC custom, opsional).
3. Selesai — cek tab **Actions**, kedua workflow bakal jalan otomatis sesuai jadwal (bisa juga di-trigger manual lewat tombol "Run workflow").

## 7. Dashboard Web (Gratis, via GitHub Pages)

Ada website statis di folder `docs/` yang nampilin status semua agent secara visual: token kandidat, laporan analisis, aktivitas wallet, dan wallet smart money yang ketemu. Update otomatis tiap kali agent jalan (lewat GitHub Actions di atas).

Cara aktifin (gratis, sekali setup):
1. Pastikan langkah 6 di atas udah dilakukan (project ada di GitHub, workflow udah jalan minimal sekali biar `docs/data.json` keisi).
2. Buka repo di GitHub → **Settings → Pages**.
3. Di bagian **Build and deployment → Source**, pilih **Deploy from a branch**.
4. Branch: `main`, folder: **`/docs`**. Klik **Save**.
5. Tunggu 1-2 menit, GitHub kasih URL, biasanya bentuknya: `https://<username-lo>.github.io/<nama-repo>/`
6. Buka URL itu — dashboard-nya langsung kebaca dari `docs/data.json` yang otomatis di-update tiap agent jalan.

Nggak perlu server, nggak perlu hosting berbayar — GitHub Pages gratis selamanya buat repo publik.

## Struktur File

```
meme_agent/
├── config.py              # semua setting (wallet, filter screener, threshold risiko, smart money)
├── notifier.py             # kirim notif Telegram
├── state.py                 # simpan riwayat biar gak notif dobel
├── dashboard_data.py         # nulis hasil kerja agent ke docs/data.json (buat dashboard web)
├── geckoterminal_api.py     # data token baru/trending (gratis, multichain)
├── dexscreener_api.py       # data tambahan token + sosial media (gratis)
├── goplus_api.py            # cek keamanan kontrak (gratis)
├── solana_rpc_api.py         # tracking wallet Solana (RPC standar, hemat/gratis)
├── helius_api.py             # [opsional, tidak dipakai default] Helius Enhanced API
├── evm_wallet_api.py        # tracking wallet EVM
├── smart_money_finder.py    # AGENT 4 - auto-discover wallet smart money
├── wallet_tracker.py        # AGENT 1
├── token_screener.py        # AGENT 2
├── deep_analysis.py         # AGENT 3
├── performance_tracker.py   # AGENT 5 - pantau performa token dari waktu ke waktu
├── main.py                  # jalankan semua
├── discovered_wallets.json  # hasil temuan smart_money_finder.py (auto-generated)
├── tracked_performance.json # data performa semua token yang lagi/pernah dipantau (auto-generated)
├── docs/
│   ├── index.html            # dashboard web (di-serve GitHub Pages)
│   └── data.json             # data buat dashboard (auto-generated tiap agent jalan)
└── .github/workflows/
    ├── run_agent.yml            # jalan tiap 15 menit
    └── smart_money_finder.yml   # jalan tiap 6 jam
```

## Ide Pengembangan Lanjutan

- **Analisis teknikal chart** (RSI, moving average, volume pattern) — saat ini `deep_analysis.py` fokus ke fundamental (keamanan kontrak, holder, sosial), belum ada indikator teknikal. Bisa ditambah pakai data candle dari GeckoTerminal (`/pools/{address}/ohlcv/{timeframe}`) + library `pandas`/`ta`.
- Tambah scoring lebih canggih (mis. bobot per faktor, bandingkan dengan historical rug rate token sejenis)
- Simpan histori kandidat ke database (SQLite) buat backtesting performa screener dari waktu ke waktu
- Tambah filter "wallet smart money juga megang token ini" — gabungkan sinyal wallet tracker + screener
- Tambah cek sentiment sosial media (butuh API tambahan, mis. LunarCrush)
- Tambah grafik/chart di dashboard (mis. pakai Chart.js) buat visualisasi tren market cap/volume dari waktu ke waktu
