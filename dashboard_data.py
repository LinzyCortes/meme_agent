"""
Modul buat nyimpen hasil kerja semua agent ke SATU file JSON (docs/data.json)
yang dibaca sama dashboard web (docs/index.html).

Kenapa taruh di folder docs/: itu folder yang di-serve GitHub Pages,
jadi website bisa langsung fetch('./data.json') tanpa perlu server/backend.
"""

import json
import os
from datetime import datetime, timezone

DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
DATA_FILE = os.path.join(DOCS_DIR, "data.json")

MAX_ITEMS_PER_SECTION = 50


def _load() -> dict:
    if not os.path.exists(DATA_FILE):
        return {
            "last_updated": None,
            "wallet_activity": [],
            "screener_candidates": [],
            "analysis_reports": [],
            "discovered_wallets": [],
            "performance_active": [],
            "performance_archived": [],
        }
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            data.setdefault("performance_active", [])
            data.setdefault("performance_archived", [])
            return data
    except Exception:
        return {
            "last_updated": None,
            "wallet_activity": [],
            "screener_candidates": [],
            "analysis_reports": [],
            "discovered_wallets": [],
            "performance_active": [],
            "performance_archived": [],
        }


def _save(data: dict):
    os.makedirs(DOCS_DIR, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _append(section: str, item: dict):
    data = _load()
    item["_logged_at"] = datetime.now(timezone.utc).isoformat()
    items = data.get(section, [])
    items.insert(0, item)  # yang terbaru di paling atas
    data[section] = items[:MAX_ITEMS_PER_SECTION]
    _save(data)


def add_wallet_activity(label: str, chain: str, address: str, summary: str, tx_url: str):
    _append("wallet_activity", {
        "label": label,
        "chain": chain,
        "address": address,
        "summary": summary,
        "tx_url": tx_url,
    })


def add_screener_candidate(pool: dict):
    _append("screener_candidates", {
        "symbol": pool.get("base_token_symbol"),
        "chain": pool.get("chain"),
        "market_cap_usd": pool.get("market_cap_usd"),
        "liquidity_usd": pool.get("liquidity_usd"),
        "volume_24h_usd": pool.get("volume_24h_usd"),
        "price_change_1h_pct": pool.get("price_change_1h_pct"),
        "price_change_24h_pct": pool.get("price_change_24h_pct"),
        "dex_url": pool.get("dex_url"),
    })


def add_analysis_report(result: dict):
    pool = result["pool"]
    _append("analysis_reports", {
        "symbol": pool.get("base_token_symbol"),
        "chain": pool.get("chain"),
        "token_address": result.get("token_address"),
        "risk_score": result.get("risk_score"),
        "security_flags": result.get("security_flags"),
        "market_cap_usd": pool.get("market_cap_usd"),
        "liquidity_usd": pool.get("liquidity_usd"),
        "socials": result.get("socials"),
        "dex_url": pool.get("dex_url"),
    })


def set_discovered_wallets(discovered: dict):
    """Overwrite (bukan append) - karena ini representasi status TERKINI semua wallet ketemu."""
    data = _load()
    wallets_list = [
        {"address": addr, **info}
        for addr, info in discovered.items()
    ]
    data["discovered_wallets"] = wallets_list
    _save(data)


def set_performance_tracking(tracking_data: dict):
    """Overwrite (bukan append) - simpen status TERKINI semua token yang lagi/pernah dipantau performanya."""
    data = _load()
    active_list = [{"key": k, **v} for k, v in tracking_data.get("active", {}).items()]
    archived_list = [{"key": k, **v} for k, v in tracking_data.get("archived", {}).items()]
    # urutin yang paling tinggi kali lipatnya duluan, biar yang paling menarik kelihatan di atas
    active_list.sort(key=lambda e: e.get("current_multiple", 0), reverse=True)
    archived_list.sort(key=lambda e: e.get("final_multiple", 0), reverse=True)
    data["performance_active"] = active_list[:MAX_ITEMS_PER_SECTION]
    data["performance_archived"] = archived_list[:MAX_ITEMS_PER_SECTION]
    _save(data)
