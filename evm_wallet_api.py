"""
Wrapper untuk Etherscan API v2 (unified, support banyak chain EVM pakai 1 API key).
Dipakai buat pantau token transfer wallet di Ethereum, Base, dll.
Daftar API key gratis di https://etherscan.io/apis
Docs: https://docs.etherscan.io/etherscan-v2
"""

import requests
from config import ETHERSCAN_API_KEY

BASE_URL = "https://api.etherscan.io/v2/api"

CHAIN_IDS = {
    "ethereum": 1,
    "base": 8453,
    "bsc": 56,
    "arbitrum": 42161,
    "polygon": 137,
}


def get_wallet_token_transfers(chain: str, address: str, limit: int = 20):
    """Ambil daftar transfer token ERC20 terbaru dari satu wallet."""
    if not ETHERSCAN_API_KEY:
        print("[WARN] ETHERSCAN_API_KEY belum diisi di .env")
        return []

    chain_id = CHAIN_IDS.get(chain)
    if chain_id is None:
        print(f"[WARN] Chain '{chain}' belum didukung di evm_wallet_api")
        return []

    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "tokentx",
        "address": address,
        "page": 1,
        "offset": limit,
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            return []
        return data.get("result", [])
    except Exception as e:
        print(f"[WARN] Etherscan request gagal untuk {address}: {e}")
        return []


def get_early_token_transfers(chain: str, contract_address: str, limit: int = 40):
    """
    Ambil transfer PALING AWAL (ascending) untuk 1 token contract - dipakai buat
    nemuin siapa yang beli token ini duluan (dasar smart_money_finder.py).
    """
    if not ETHERSCAN_API_KEY:
        print("[WARN] ETHERSCAN_API_KEY belum diisi di .env")
        return []

    chain_id = CHAIN_IDS.get(chain)
    if chain_id is None:
        return []

    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "tokentx",
        "contractaddress": contract_address,
        "page": 1,
        "offset": limit,
        "sort": "asc",
        "apikey": ETHERSCAN_API_KEY,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            return []
        return data.get("result", [])
    except Exception as e:
        print(f"[WARN] Etherscan early transfers gagal untuk {contract_address}: {e}")
        return []


def get_transaction_native_value(chain: str, tx_hash: str) -> float:
    """
    Ambil berapa banyak native currency (ETH/BNB/dst, BUKAN token) yang dikirim
    di 1 transaksi - dipakai buat verifikasi wallet BENERAN keluar modal, bukan
    cuma nerima token gratisan (airdrop/reflection). Return dalam satuan native
    (mis. ETH), bukan wei.
    """
    if not ETHERSCAN_API_KEY:
        return 0.0
    chain_id = CHAIN_IDS.get(chain)
    if chain_id is None:
        return 0.0

    params = {
        "chainid": chain_id,
        "module": "proxy",
        "action": "eth_getTransactionByHash",
        "txhash": tx_hash,
        "apikey": ETHERSCAN_API_KEY,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        result = resp.json().get("result")
        if not result or not result.get("value"):
            return 0.0
        value_wei = int(result["value"], 16)
        return value_wei / 1e18
    except Exception as e:
        print(f"[WARN] Gagal ambil value transaksi {tx_hash}: {e}")
        return 0.0


def parse_transfer(tx: dict, wallet_address: str) -> dict:
    """Ubah 1 raw transfer record jadi dict ringkas, tandai buy/sell dari sudut pandang wallet."""
    is_incoming = tx.get("to", "").lower() == wallet_address.lower()
    decimals = int(tx.get("tokenDecimal", 18) or 18)
    raw_value = int(tx.get("value", 0) or 0)
    amount = raw_value / (10 ** decimals)
    return {
        "hash": tx.get("hash"),
        "timestamp": tx.get("timeStamp"),
        "direction": "BUY/IN" if is_incoming else "SELL/OUT",
        "token_symbol": tx.get("tokenSymbol"),
        "token_address": tx.get("contractAddress"),
        "amount": amount,
    }
