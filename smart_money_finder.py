"""
AGENT 4: SMART MONEY FINDER
Otomatis nemuin wallet "smart money" tanpa lo harus cari/isi manual.

Cara kerja:
1. Cari token yang lagi "menang" (trending & harga naik signifikan) di tiap chain.
2. Buat tiap token pemenang, telusuri wallet-wallet yang beli PALING AWAL
   (sebelum harganya naik besar).
3. Wallet yang muncul sebagai pembeli awal di >= SMART_MONEY_SETTINGS["min_appearances"]
   token pemenang yang BERBEDA -> disimpan sebagai kandidat smart money ke
   discovered_wallets.json.
4. wallet_tracker.py otomatis baca file ini juga (digabung dengan WATCHED_WALLETS
   manual di config.py), jadi begitu ketemu, langsung ikut dipantau otomatis.

Cara pakai:
    python smart_money_finder.py

Catatan: ini heuristik (perkiraan), bukan jaminan 100% akurat. Wallet yang
kebetulan beli awal di 1-2 token yang lagi pump bisa aja cuma faktor
keberuntungan, bukan skill. Makin tinggi "min_appearances", makin ketat
tapi makin sedikit yang ketemu, dan makin bisa dipercaya sinyalnya.
"""

import json
import os
import time
from collections import defaultdict

import geckoterminal_api as gt
import solana_rpc_api as sol
import evm_wallet_api as evm
import dashboard_data
from config import SMART_MONEY_SETTINGS, DISCOVERED_WALLETS_FILE, WALLET_EVIDENCE_FILE
from notifier import send_telegram

DISCOVERED_FILE_PATH = os.path.join(os.path.dirname(__file__), DISCOVERED_WALLETS_FILE)
EVIDENCE_FILE_PATH = os.path.join(os.path.dirname(__file__), WALLET_EVIDENCE_FILE)
CHECKED_POOLS_FILE_PATH = os.path.join(os.path.dirname(__file__), "checked_pools.json")

# Alamat yang harus di-skip karena bukan wallet asli (kontrak DEX router/pool umum dll)
KNOWN_NON_WALLET_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "11111111111111111111111111111111",
}

# Simbol native currency per chain (dipakai buat deteksi apakah quote token pool = native currency)
NATIVE_SYMBOLS_BY_CHAIN = {
    "solana": ["SOL", "WSOL"],
    "ethereum": ["ETH", "WETH"],
    "base": ["ETH", "WETH"],
    "bsc": ["BNB", "WBNB"],
    "arbitrum": ["ETH", "WETH"],
    "polygon": ["MATIC", "WMATIC"],
}
# Fallback KASAR kalau quote token pool bukan native currency (jadi gak ada data harga live).
# Ini cuma buat filter kasar "masuk akal atau nggak", bukan buat presisi tinggi.
FALLBACK_NATIVE_PRICE_USD = {
    "solana": 150.0,
    "ethereum": 3000.0,
    "base": 3000.0,
    "bsc": 550.0,
    "arbitrum": 3000.0,
    "polygon": 0.7,
}


def _estimate_native_price_usd(pool: dict) -> float:
    """
    Estimasi harga native currency chain ini (SOL/ETH/BNB/dst) saat itu, buat convert
    'berapa banyak native currency yang dikeluarin wallet' jadi USD. Paling akurat kalau
    pool ini dipasangkan langsung ke native currency (data yang udah kebawa otomatis
    dari GeckoTerminal, GAK PERLU API call tambahan). Kalau bukan, pakai angka fallback kasar.
    """
    chain = pool.get("chain", "solana")
    name = (pool.get("name") or "").upper()
    quote_symbol = name.split("/")[-1].strip() if "/" in name else ""
    quote_price = pool.get("quote_token_price_usd") or 0
    native_symbols = NATIVE_SYMBOLS_BY_CHAIN.get(chain, [])
    if any(sym in quote_symbol for sym in native_symbols) and quote_price > 0:
        return quote_price
    return FALLBACK_NATIVE_PRICE_USD.get(chain, 150.0)


def find_winner_pools(chain: str, already_checked: dict) -> list:
    """
    Cari token pemenang: gabungin dari 2 sumber (new_pools + trending_pools) biar
    lebih variatif tiap run - kalau cuma dari trending doang, daftarnya cenderung
    sama terus dalam rentang waktu pendek. Token yang udah dicek dalam
    `recheck_cooldown_hours` terakhir di-skip, biar tiap run dapet token BEDA.
    """
    settings = SMART_MONEY_SETTINGS
    cooldown_seconds = settings["recheck_cooldown_hours"] * 3600
    now = time.time()

    raw_pools = gt.get_new_pools(chain) + gt.get_trending_pools(chain)
    seen_this_scan = set()
    candidates = []

    for raw in raw_pools:
        pool = gt.parse_pool(raw)
        if not pool["pool_address"] or pool["pool_address"] in seen_this_scan:
            continue
        seen_this_scan.add(pool["pool_address"])

        if not (
            pool["price_change_24h_pct"] >= settings["winner_min_price_change_24h_pct"]
            and 0 < pool["market_cap_usd"] <= settings["winner_max_market_cap"]
        ):
            continue

        pool_key = f"{chain}:{pool['pool_address']}"
        last_checked = already_checked.get(pool_key, 0)
        if now - last_checked < cooldown_seconds:
            continue  # baru aja dicek run sebelumnya, skip biar dapet token laen

        pool["chain"] = chain
        pool["dex_url"] = gt.build_pool_url(chain, pool["pool_address"])
        candidates.append(pool)

    candidates.sort(key=lambda p: p["price_change_24h_pct"], reverse=True)
    return candidates[: settings["max_winner_tokens_per_chain"]]


def get_token_mint_address(chain: str, pool_address: str):
    """[FALLBACK, jarang dipakai] Kalau butuh token address tapi pool dict gak punya token_address."""
    detail = gt.get_pool_detail(chain, pool_address)
    if not detail:
        return None
    try:
        base_token_id = detail["relationships"]["base_token"]["data"]["id"]
        return base_token_id.split("_", 1)[1]
    except Exception:
        return None


def _estimate_sol_price_usd(pool: dict) -> float:
    """Alias buat backward-compat, sekarang pakai fungsi general _estimate_native_price_usd()."""
    return _estimate_native_price_usd(pool)


def find_early_buyers_solana(pool: dict, limit: int) -> set:
    # token_address udah otomatis kebawa dari gt.parse_pool() di find_winner_pools(),
    # TANPA perlu request tambahan ke GeckoTerminal lagi.
    mint = pool.get("token_address")
    if not mint:
        return set()

    min_usd_spent = SMART_MONEY_SETTINGS["min_usd_spent_to_count_as_buy"]
    sol_price_usd = _estimate_native_price_usd(pool)
    early_sigs = sol.get_early_signatures(pool["pool_address"], max_fetch=300)
    buyers = set()
    max_checks = min(len(early_sigs), limit * 4)  # jangan cek lebih dari ini, biar gak lama banget

    for i, sig_info in enumerate(early_sigs[:max_checks]):
        if len(buyers) >= limit:
            break
        if (i + 1) % 5 == 0:
            print(f"    ...cek transaksi ke-{i + 1}/{max_checks}, sudah ketemu {len(buyers)} pembeli beneran (>=${min_usd_spent})")
        if sig_info.get("err"):
            continue
        tx = sol.get_transaction(sig_info["signature"])
        changes = sol.extract_all_owner_changes_for_mint(tx, mint)
        for c in changes:
            if not (c["delta"] > 0 and c["owner"] and c["owner"] != pool["pool_address"]):
                continue
            # FILTER PENTING: saldo token nambah doang gak cukup - itu bisa jadi
            # airdrop/reflection/distribusi otomatis, bukan pembelian asli. Wallet
            # harus BENERAN keluar modal senilai minimal $X (bukan cuma "gak nol")
            # di transaksi yang sama buat dianggap "beli dengan keyakinan/modal berarti".
            sol_spent = sol.extract_total_sol_spent(tx, c["owner"])  # gabungan SOL native + WSOL
            usd_spent = sol_spent * sol_price_usd
            if usd_spent >= min_usd_spent:
                buyers.add(c["owner"])

    return buyers


def find_early_buyers_evm(pool: dict, limit: int) -> set:
    chain = pool["chain"]
    # token_address udah otomatis kebawa dari gt.parse_pool(), gak perlu request tambahan
    token_address = pool.get("token_address")
    if not token_address:
        return set()

    transfers = evm.get_early_token_transfers(chain, token_address, limit=limit * 2)
    buyers = set()
    min_usd_spent = SMART_MONEY_SETTINGS["min_usd_spent_to_count_as_buy"]
    native_price_usd = _estimate_native_price_usd(pool)

    for t in transfers:
        if len(buyers) >= limit:
            break

        from_addr = (t.get("from") or "").lower()
        to_addr = (t.get("to") or "").lower()
        pool_addr = (pool["pool_address"] or "").lower()

        # cuma hitung transfer YANG KELUAR DARI POOL (= aksi beli/swap), skip transfer lain
        # (misal initial liquidity add dari deployer ke pool)
        if from_addr != pool_addr:
            continue
        if to_addr in KNOWN_NON_WALLET_ADDRESSES or not to_addr:
            continue

        # FILTER PENTING (sama kayak Solana): pastiin wallet ini BENERAN keluar modal
        # (native currency) di transaksi yang sama, bukan cuma nerima token gratisan
        # (airdrop/reflection). Ini butuh 1 API call tambahan per kandidat, tapi
        # Etherscan free tier jauh lebih longgar (5 request/detik) daripada GeckoTerminal.
        tx_hash = t.get("hash")
        native_spent = evm.get_transaction_native_value(chain, tx_hash) if tx_hash else 0.0
        usd_spent = native_spent * native_price_usd
        if usd_spent < min_usd_spent:
            continue

        buyers.add(t.get("to"))

    return buyers


def load_discovered() -> dict:
    if not os.path.exists(DISCOVERED_FILE_PATH):
        return {}
    try:
        with open(DISCOVERED_FILE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_discovered(data: dict):
    with open(DISCOVERED_FILE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def check_smart_money_overlap(chain: str, pool_address: str) -> list:
    """
    Cek apakah token ini PERNAH jadi bukti pembelian awal buat wallet smart
    money yang udah terkonfirmasi. Dipakai token_screener.py buat "sinyal
    gabungan" - kalau screener DAN smart money tracker sama-sama nunjuk ke
    token yang sama, itu keyakinan yang jauh lebih kuat daripada sinyal
    tunggal. Return: list address wallet yang overlap (kosong kalau gak ada).
    """
    discovered = load_discovered()
    matches = []
    for wallet, info in discovered.items():
        if info.get("chain") != chain:
            continue
        evidence = info.get("evidence_tokens", [])
        if any(pool_address in token_id for token_id in evidence):
            matches.append(wallet)
    return matches


def load_checked_pools() -> dict:
    """Muat catatan 'pool mana aja yang udah dicek, kapan' - biar gak ngulang-ngulang token yang sama."""
    if not os.path.exists(CHECKED_POOLS_FILE_PATH):
        return {}
    try:
        with open(CHECKED_POOLS_FILE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_checked_pools(data: dict):
    # buang entri yang udah lebih dari 7 hari biar file gak membengkak terus
    cutoff = time.time() - (7 * 24 * 3600)
    cleaned = {k: v for k, v in data.items() if v >= cutoff}
    with open(CHECKED_POOLS_FILE_PATH, "w") as f:
        json.dump(cleaned, f, indent=2)


def load_evidence() -> dict:
    """
    Muat SEMUA bukti "pembelian awal" yang pernah terkumpul dari run-run sebelumnya
    (bukan cuma run saat ini). Ini yang bikin smart money finder "inget" dari waktu
    ke waktu, bukan reset tiap kali dijalankan.
    Format: { wallet_address: {"chain": ..., "evidence_tokens": [token_id, ...]} }
    """
    if not os.path.exists(EVIDENCE_FILE_PATH):
        return {}
    try:
        with open(EVIDENCE_FILE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_evidence(data: dict):
    with open(EVIDENCE_FILE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def run_once():
    settings = SMART_MONEY_SETTINGS
    # wallet_address -> set of token_id yang jadi bukti "pembelian awal di token pemenang" DI RUN INI SAJA
    this_run_appearances = defaultdict(set)
    wallet_chain_map = {}
    checked_pools = load_checked_pools()

    for chain in settings["chains"]:
        print(f"[INFO] Cari token pemenang di {chain}...")
        try:
            winners = find_winner_pools(chain, checked_pools)
        except Exception as e:
            print(f"[ERROR] Gagal cari winner di {chain}: {e}")
            continue

        if not winners:
            print(f"    (semua kandidat di {chain} baru aja dicek run sebelumnya, atau gak ada yang lolos filter - skip)")

        for pool in winners:
            print(f"[INFO] Telusuri pembeli awal {pool['base_token_symbol']} ({chain})...")
            pool_key = f"{chain}:{pool['pool_address']}"
            checked_pools[pool_key] = time.time()  # tandain udah dicek, biar run berikutnya skip & cari yang laen
            try:
                if chain == "solana":
                    buyers = find_early_buyers_solana(pool, settings["early_buyers_per_token"])
                else:
                    buyers = find_early_buyers_evm(pool, settings["early_buyers_per_token"])
            except Exception as e:
                print(f"[ERROR] Gagal telusuri pembeli awal {pool['base_token_symbol']}: {e}")
                continue

            token_id = f"{chain}:{pool['base_token_symbol']}:{pool['pool_address']}"
            for wallet in buyers:
                this_run_appearances[wallet].add(token_id)
                wallet_chain_map[wallet] = chain

    save_checked_pools(checked_pools)

    # GABUNGIN bukti run ini dengan bukti yang udah terkumpul dari run-run sebelumnya
    # (ini kuncinya biar wallet yang "kebetulan" keliatan cuma 1x per run, tapi
    # konsisten muncul lagi di run-run berikutnya, tetap keakumulasi jadi bukti kuat)
    evidence = load_evidence()
    for wallet, tokens in this_run_appearances.items():
        existing = set(evidence.get(wallet, {}).get("evidence_tokens", []))
        merged = existing | tokens
        evidence[wallet] = {
            "chain": wallet_chain_map[wallet],
            "evidence_tokens": list(merged),
        }
    save_evidence(evidence)

    # filter wallet yang TOTAL bukti terkumpulnya (lintas semua run) >= min_appearances
    discovered = load_discovered()
    new_smart_money = []

    for wallet, info in evidence.items():
        tokens = info["evidence_tokens"]
        if len(tokens) >= settings["min_appearances"]:
            if wallet not in discovered:
                new_smart_money.append({"wallet": wallet, "chain": info["chain"], "evidence": tokens})
            discovered[wallet] = {
                "chain": info["chain"],
                "appearances": len(tokens),
                "evidence_tokens": tokens,
            }

    save_discovered(discovered)
    dashboard_data.set_discovered_wallets(discovered)

    if new_smart_money:
        for entry in new_smart_money:
            evidence_text = ", ".join(t.split(":")[1] for t in entry["evidence"][:5])
            message = (
                f"🕵️ *Smart Money Baru Ditemukan* ({entry['chain'].title()})\n"
                f"Wallet: `{entry['wallet']}`\n"
                f"Terdeteksi beli awal di {len(entry['evidence'])} token pemenang: {evidence_text}\n"
                f"Wallet ini otomatis ditambahkan ke daftar pantauan."
            )
            send_telegram(message)

    print(f"[INFO] Selesai. Total wallet dengan bukti terkumpul: {len(evidence)} | "
          f"Total smart money terkonfirmasi (>= {settings['min_appearances']} bukti): {len(discovered)} "
          f"(baru terkonfirmasi run ini: {len(new_smart_money)})")
    return discovered


if __name__ == "__main__":
    run_once()
