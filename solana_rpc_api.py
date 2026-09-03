"""
Wrapper untuk Solana JSON-RPC standar (BUKAN Helius Enhanced API).
Kenapa ganti dari Enhanced Transactions API:
    - Enhanced API ~100 credit/request -> 100k credit gratis abis dalam hitungan hari
      kalau dipantau tiap 15 menit.
    - RPC standar (getSignaturesForAddress + getTransaction) jauh lebih hemat:
      di Helius ~1 credit/request, atau bisa pakai endpoint publik yang 100% gratis
      tanpa API key sama sekali (dengan trade-off rate limit lebih ketat & kadang kurang stabil).

Default pakai endpoint publik Solana. Kalau mau lebih stabil/cepat, isi SOLANA_RPC_URL
di .env dengan RPC gratis dari Helius/QuickNode/Alchemy/Ankr (jauh lebih murah credit-nya
dibanding Enhanced API meski dari provider yang sama).
"""

import time
import requests
from config import SOLANA_RPC_URL

REQUEST_DELAY = 0.3  # jeda antar request biar gak kena rate limit endpoint publik

# Mint address "Wrapped SOL" - dipakai buat deteksi belanja yang lewat WSOL (bukan SOL native).
# Kebanyakan swap di Raydium/Orca lewat sini, BUKAN lewat native SOL balance langsung.
WSOL_MINT = "So11111111111111111111111111111111111111112"


def _rpc_call(method: str, params: list, retries: int = 3):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    for attempt in range(retries):
        try:
            resp = requests.post(SOLANA_RPC_URL, json=payload, timeout=20)
            if resp.status_code == 429:
                time.sleep(3)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                print(f"[WARN] RPC error ({method}): {data['error']}")
                return None
            return data.get("result")
        except Exception as e:
            if attempt == retries - 1:
                print(f"[WARN] RPC request gagal ({method}): {e}")
                return None
            time.sleep(2)
    return None


def get_signatures_for_address(address: str, limit: int = 15) -> list:
    """Ambil daftar signature transaksi terbaru dari 1 wallet."""
    result = _rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
    time.sleep(REQUEST_DELAY)
    return result or []


def get_transaction(signature: str) -> dict:
    """Ambil detail 1 transaksi (termasuk token balance changes)."""
    result = _rpc_call(
        "getTransaction",
        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
    )
    time.sleep(REQUEST_DELAY)
    return result


def extract_token_changes(tx: dict, wallet_address: str) -> list:
    """
    Bandingkan preTokenBalances vs postTokenBalances buat deteksi token apa
    yang berubah jumlahnya di wallet ini, dan berapa besar perubahannya.
    Ini pengganti "Enhanced parsing" ala Helius, tapi manual & gratis.
    """
    if not tx or not tx.get("meta"):
        return []

    meta = tx["meta"]
    pre_balances = {b["accountIndex"]: b for b in meta.get("preTokenBalances", [])}
    post_balances = {b["accountIndex"]: b for b in meta.get("postTokenBalances", [])}

    changes = []
    all_indices = set(pre_balances.keys()) | set(post_balances.keys())

    for idx in all_indices:
        pre = pre_balances.get(idx)
        post = post_balances.get(idx)
        owner = (post or pre).get("owner")
        if owner != wallet_address:
            continue  # cuma peduli token balance milik wallet yang kita pantau

        mint = (post or pre).get("mint")
        pre_amt = float(pre["uiTokenAmount"]["uiAmountString"]) if pre and pre["uiTokenAmount"]["uiAmountString"] else 0.0
        post_amt = float(post["uiTokenAmount"]["uiAmountString"]) if post and post["uiTokenAmount"]["uiAmountString"] else 0.0
        delta = post_amt - pre_amt

        if abs(delta) > 0:
            changes.append({
                "mint": mint,
                "delta": delta,
                "direction": "BUY/IN" if delta > 0 else "SELL/OUT",
            })

    return changes


def extract_all_owner_changes_for_mint(tx: dict, mint_address: str) -> list:
    """
    Buat SEMUA owner (bukan cuma 1 wallet spesifik) yang balance-nya berubah
    untuk 1 mint tertentu di transaksi ini. Dipakai buat deteksi "siapa yang
    beli token ini di transaksi X" - dasar dari smart_money_finder.py.
    """
    if not tx or not tx.get("meta"):
        return []

    meta = tx["meta"]
    pre_balances = {b["accountIndex"]: b for b in meta.get("preTokenBalances", []) if b.get("mint") == mint_address}
    post_balances = {b["accountIndex"]: b for b in meta.get("postTokenBalances", []) if b.get("mint") == mint_address}

    changes = []
    all_indices = set(pre_balances.keys()) | set(post_balances.keys())

    for idx in all_indices:
        pre = pre_balances.get(idx)
        post = post_balances.get(idx)
        owner = (post or pre).get("owner")
        pre_amt = float(pre["uiTokenAmount"]["uiAmountString"]) if pre and pre["uiTokenAmount"]["uiAmountString"] else 0.0
        post_amt = float(post["uiTokenAmount"]["uiAmountString"]) if post and post["uiTokenAmount"]["uiAmountString"] else 0.0
        delta = post_amt - pre_amt
        if abs(delta) > 0:
            changes.append({"owner": owner, "delta": delta})

    return changes


def extract_total_sol_spent(tx: dict, owner: str) -> float:
    """
    Hitung TOTAL yang dikeluarin 1 wallet dalam satuan SOL, GABUNGAN dari 2 sumber:
    1. SOL native (preBalances/postBalances) - dipakai transaksi simple/pump.fun bonding curve
    2. WSOL/Wrapped SOL (SPL token biasa) - dipakai kebanyakan swap di Raydium/Orca

    Ini FIX PENTING: sebelumnya cuma ngecek #1, padahal mayoritas swap DEX lewat #2,
    jadi kelihatan seolah wallet "gak keluar modal" padahal aslinya beneran beli.
    Return: nilai positif = keluar SOL (spent), 0 atau negatif = gak spend/malah nerima.
    """
    native_spent = -extract_sol_change(tx, owner)  # extract_sol_change: positif=nerima, jadi dibalik

    wsol_spent = 0.0
    wsol_changes = extract_all_owner_changes_for_mint(tx, WSOL_MINT)
    for c in wsol_changes:
        if c["owner"] == owner and c["delta"] < 0:
            wsol_spent += -c["delta"]

    return native_spent + wsol_spent


def get_early_signatures(pool_address: str, max_fetch: int = 300) -> list:
    """
    Ambil signature transaksi paling AWAL yang tersedia untuk 1 pool.
    RPC getSignaturesForAddress selalu return dari yang TERBARU dulu, jadi
    kita ambil sampai max_fetch lalu urutkan ascending buat dapetin yang paling lawas
    (approksimasi - kalau pool sudah punya >max_fetch transaksi, ini cuma capture
    sebagian history, cocok dipakai khusus buat token yang masih relatif baru).
    """
    sigs = get_signatures_for_address(pool_address, limit=max_fetch)
    sigs_sorted = sorted(sigs, key=lambda s: s.get("blockTime") or 0)
    return sigs_sorted


def extract_sol_change(tx: dict, wallet_address: str) -> float:
    """Hitung perubahan saldo native SOL wallet ini di transaksi (dalam SOL, bukan lamport)."""
    if not tx or not tx.get("meta"):
        return 0.0
    try:
        account_keys = tx["transaction"]["message"]["accountKeys"]
        idx = next(
            i for i, k in enumerate(account_keys)
            if (k.get("pubkey") if isinstance(k, dict) else k) == wallet_address
        )
        pre = tx["meta"]["preBalances"][idx]
        post = tx["meta"]["postBalances"][idx]
        return (post - pre) / 1_000_000_000  # lamport -> SOL
    except (StopIteration, IndexError, KeyError):
        return 0.0
