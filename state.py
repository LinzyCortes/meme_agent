"""
Penyimpanan state sederhana pakai file JSON lokal, biar:
- wallet tracker gak notif transaksi yang sama berkali-kali
- token screener gak notif token yang sama berkali-kali
"""

import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def _load() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"seen_txs": [], "seen_tokens": []}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"seen_txs": [], "seen_tokens": []}


def _save(data: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_new_tx(tx_id: str) -> bool:
    data = _load()
    return tx_id not in data.get("seen_txs", [])


def mark_tx_seen(tx_id: str):
    data = _load()
    seen = data.get("seen_txs", [])
    seen.append(tx_id)
    data["seen_txs"] = seen[-2000:]  # simpan 2000 terakhir aja biar file gak membengkak
    _save(data)


def is_new_token(token_key: str) -> bool:
    data = _load()
    return token_key not in data.get("seen_tokens", [])


def mark_token_seen(token_key: str):
    data = _load()
    seen = data.get("seen_tokens", [])
    seen.append(token_key)
    data["seen_tokens"] = seen[-2000:]
    _save(data)
