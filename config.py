"""
Config utama untuk Meme Token AI Agent.
Isi semua nilai di bawah, atau lebih baik pakai file .env (lihat .env.example)
"""

import os
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# API KEYS (daftar gratis di masing-masing website)
# =========================================================
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")          # opsional, tidak wajib lagi (lihat SOLANA_RPC_URL)

# RPC Solana buat wallet tracking (JAUH lebih hemat daripada Enhanced API-nya Helius).
# Default: endpoint publik gratis, tanpa key sama sekali (rate limit lebih ketat).
# Kalau mau lebih stabil: daftar RPC gratis di Helius/QuickNode/Ankr, lalu isi URL-nya di .env.
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")     # https://etherscan.io/apis (juga jalan utk basescan v2 unified API)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")   # dari @BotFather
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")       # ID chat/grup tujuan notif

# =========================================================
# WALLET YANG DIPANTAU (Wallet Tracker Agent)
# Isi address wallet yang mau lo pantau (smart money / whale meme coin)
# =========================================================
WATCHED_WALLETS = [
    # {"label": "Whale A", "chain": "solana", "address": "ISI_ADDRESS_SOLANA"},
    # {"label": "Whale B", "chain": "ethereum", "address": "ISI_ADDRESS_EVM"},
    # {"label": "Whale C", "chain": "base", "address": "ISI_ADDRESS_EVM"},
]

# Filter noise: kalau token wallet nambah (BUY/IN) tapi wallet-nya gak beneran keluar SOL
# minimal segini, kemungkinan itu airdrop/reflection/distribusi otomatis - BUKAN pembelian
# asli - jadi gak dinotifikasiin (biar Telegram lo gak dibanjirin notif recehan gak berarti).
# SELL/OUT tetap selalu dinotifikasiin (jual itu selalu aksi sengaja, gak perlu filter ini).
WALLET_TRACKER_MIN_SOL_SPENT_FOR_BUY = 0.02

# =========================================================
# TOKEN SCREENER SETTINGS (Token Screener Agent)
# =========================================================
SCREENER_CHAINS = ["solana", "base", "ethereum"]   # chain yang mau di-scan

SCREENER_FILTERS = {
    "min_market_cap": 20_000,       # USD - jangan terlalu micro (rawan rug total)
    "max_market_cap": 500_000,      # USD - diperketat biar fokus token BENERAN kecil (potensi kali lipat lebih besar)
    "min_liquidity_usd": 8_000,     # liquidity pool minimum, biar gak terlalu ilikuid
    "min_volume_24h_usd": 15_000,   # volume 24 jam minimum, tanda ada aktivitas nyata
    "min_age_hours": 2,             # umur token minimum (jam) - hindari yg baru banget/super rawan
    "max_age_hours": 24 * 14,       # umur token maksimum (hari->jam) - fokus token baru, bukan yg udah lama stuck
    "min_txns_24h": 50,             # jumlah transaksi 24 jam minimum
    "min_price_change_1h_pct": 5,   # ada momentum naik minimal sekian % di 1 jam terakhir
}

SCAN_INTERVAL_MINUTES = 15   # seberapa sering screener jalan (kalau dipakai mode loop)

# =========================================================
# SMART MONEY FINDER SETTINGS (Agent tambahan - auto-discover wallet)
# =========================================================
SMART_MONEY_SETTINGS = {
    "chains": ["solana", "base", "ethereum"],
    "winner_min_price_change_24h_pct": 80,   # token dianggap "pemenang" kalau naik >= ini % dalam 24 jam
    "winner_max_market_cap": 10_000_000,     # tetap batasi biar fokus ke gem, bukan token yang udah besar
    "max_winner_tokens_per_chain": 4,        # dinaikin dikit karena sekarang sumbernya lebih beragam (new_pools + trending)
    "early_buyers_per_token": 12,            # ambil berapa banyak "pembeli awal" per token pemenang
    "min_appearances": 2,                    # dipakai buat status HIGH CONFIDENCE (lihat di bawah)
    "min_appearances_low_confidence": 1,     # status awal/sinyal lemah - biar lo tetep dapet hasil lebih cepat,
                                              # walau confidence-nya masih rendah (perlu ekstra hati-hati/verifikasi manual)
    "min_usd_spent_to_count_as_buy": 150,    # diturunin dari $500 - soalnya di token yang BARU BANGET listing,
                                              # liquidity masih tipis, jadi pembeli PALING AWAL biasanya modalnya
                                              # kecil dulu (nyoba-nyoba), yang modal gede baru masuk belakangan.
                                              # $150 masih jauh di atas dust ($3-10) tapi realistis buat early buy.
                                              # Naikin lagi kalau udah punya cukup data & mau lebih ketat.
    "recheck_cooldown_hours": 6,             # jangan cek ulang token yang SAMA dalam rentang ini - biar tiap run
                                              # dapet token BEDA (bukan itu-itu aja), lebih variatif & gak buang waktu
}
DISCOVERED_WALLETS_FILE = "discovered_wallets.json"
WALLET_EVIDENCE_FILE = "wallet_evidence.json"   # nyimpen SEMUA bukti pembelian awal, lintas-run (biar gak reset tiap scan)

# =========================================================
# PERFORMANCE TRACKING SETTINGS (Agent tambahan - pantau performa token yang direkomendasiin)
# =========================================================
PERFORMANCE_TRACKING_SETTINGS = {
    "tracking_window_days": 14,                       # berapa lama 1 token terus dipantau sebelum "lulus" observasi
    "milestone_multiples": [2, 3, 5, 10, 20, 50, 100], # kirim notif tiap kali harga nyampe kelipatan ini dari titik awal
}

# =========================================================
# DEEP ANALYSIS SETTINGS
# =========================================================
ANALYSIS_RISK_THRESHOLDS = {
    "max_top10_holder_pct": 40,     # kalau top 10 holder pegang > ini % dari supply -> red flag
    "max_owner_balance_pct": 15,    # kalau 1 wallet (bukan LP) pegang > ini % -> red flag
    "min_liquidity_locked_pct": 50, # kalau liquidity locked/burned < ini % -> red flag
}
