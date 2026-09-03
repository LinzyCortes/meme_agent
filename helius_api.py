"""
[OPSIONAL / TIDAK DIPAKAI DEFAULT] Wrapper untuk Helius Enhanced Transactions API (Solana).

CATATAN PENTING: modul ini TIDAK dipakai lagi oleh wallet_tracker.py secara default,
karena Enhanced API ini boros credit (~100 credit/request) dan bisa bikin kuota gratis
100k/bulan abis dalam hitungan hari kalau dipantau tiap 15 menit. wallet_tracker.py
sekarang pakai solana_rpc_api.py (RPC standar) yang jauh lebih hemat/gratis.

Modul ini disimpan buat referensi kalau suatu saat lo mau data yang sudah "diparse
otomatis" oleh Helius (lebih malas dikit kodingnya, tapi lebih boros credit) - misalnya
untuk analisis mendalam pada 1 wallet tertentu secara manual/jarang.
Daftar API key gratis di https://dev.helius.xyz (free tier: 100k credit/bulan)
Docs: https://docs.helius.dev/solana-apis/enhanced-transactions-api
"""

import requests
from config import HELIUS_API_KEY

BASE_URL = "https://api.helius.xyz/v0"


def get_wallet_transactions(address: str, limit: int = 20):
    """Ambil transaksi terbaru dari satu wallet Solana (sudah di-parse Helius)."""
    if not HELIUS_API_KEY:
        print("[WARN] HELIUS_API_KEY belum diisi di .env")
        return []

    url = f"{BASE_URL}/addresses/{address}/transactions"
    params = {"api-key": HELIUS_API_KEY, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[WARN] Helius request gagal untuk {address}: {e}")
        return []


def extract_swaps(transactions: list) -> list:
    """
    Filter transaksi jadi list swap/token-trade yang relevan.
    Helius sudah kasih field `type` (mis. SWAP) dan `tokenTransfers`.
    """
    swaps = []
    for tx in transactions:
        tx_type = tx.get("type", "")
        token_transfers = tx.get("tokenTransfers", [])
        if tx_type == "SWAP" or (token_transfers and len(token_transfers) >= 1):
            swaps.append({
                "signature": tx.get("signature"),
                "timestamp": tx.get("timestamp"),
                "type": tx_type,
                "description": tx.get("description", ""),
                "token_transfers": [
                    {
                        "mint": t.get("mint"),
                        "from": t.get("fromUserAccount"),
                        "to": t.get("toUserAccount"),
                        "amount": t.get("tokenAmount"),
                    }
                    for t in token_transfers
                ],
            })
    return swaps
