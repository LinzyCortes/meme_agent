"""
AGENT 2: TOKEN SCREENER
Scan token baru & trending di beberapa chain, filter berdasarkan kriteria
di config.SCREENER_FILTERS (market cap kecil, liquidity & volume sehat,
ada momentum harga naik). Token yang lolos filter -> kandidat untuk
dianalisa lebih dalam oleh Agent 3 (deep_analysis.py).

Cara pakai:
    python token_screener.py
"""

from datetime import datetime, timezone

import geckoterminal_api as gt
import state
import dashboard_data
import performance_tracker
from config import SCREENER_CHAINS, SCREENER_FILTERS
from notifier import send_telegram


def _age_hours(created_at_str: str) -> float:
    if not created_at_str:
        return 0
    try:
        created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - created).total_seconds() / 3600
    except Exception:
        return 0


def passes_filters(pool: dict) -> bool:
    f = SCREENER_FILTERS
    age_h = _age_hours(pool["pool_created_at"])

    checks = [
        f["min_market_cap"] <= pool["market_cap_usd"] <= f["max_market_cap"],
        pool["liquidity_usd"] >= f["min_liquidity_usd"],
        pool["volume_24h_usd"] >= f["min_volume_24h_usd"],
        f["min_age_hours"] <= age_h <= f["max_age_hours"],
        pool["txns_24h"] >= f["min_txns_24h"],
        pool["price_change_1h_pct"] >= f["min_price_change_1h_pct"],
    ]
    return all(checks)


def scan_chain(chain: str) -> list:
    """Scan token baru + trending di 1 chain, return list kandidat yang lolos filter."""
    candidates = []
    raw_pools = gt.get_new_pools(chain) + gt.get_trending_pools(chain)

    seen_in_this_scan = set()
    for raw in raw_pools:
        pool = gt.parse_pool(raw)
        if not pool["pool_address"] or pool["pool_address"] in seen_in_this_scan:
            continue
        seen_in_this_scan.add(pool["pool_address"])

        if passes_filters(pool):
            pool["chain"] = chain
            pool["dex_url"] = gt.build_pool_url(chain, pool["pool_address"])
            candidates.append(pool)

    return candidates


def format_candidate_message(pool: dict) -> str:
    return (
        f"🚀 *Token Kandidat Ditemukan* — {pool['base_token_symbol']} ({pool['chain'].title()})\n"
        f"Market Cap: ${pool['market_cap_usd']:,.0f}\n"
        f"Liquidity: ${pool['liquidity_usd']:,.0f}\n"
        f"Volume 24h: ${pool['volume_24h_usd']:,.0f}\n"
        f"Perubahan harga 1h: {pool['price_change_1h_pct']:.1f}% | 24h: {pool['price_change_24h_pct']:.1f}%\n"
        f"Transaksi 24h: {pool['txns_24h']}\n"
        f"Pool address: `{pool['pool_address']}`\n"
        f"Chart: {pool['dex_url']}\n\n"
        f"_Lagi jalanin deep analysis..._"
    )


def run_once(trigger_deep_analysis: bool = True) -> list:
    all_candidates = []
    for chain in SCREENER_CHAINS:
        print(f"[INFO] Scanning chain: {chain}...")
        try:
            candidates = scan_chain(chain)
        except Exception as e:
            print(f"[ERROR] Gagal scan chain {chain}: {e}")
            continue

        for pool in candidates:
            token_key = f"{chain}:{pool['pool_address']}"
            if not state.is_new_token(token_key):
                continue

            print(f"[FOUND] {pool['base_token_symbol']} di {chain} lolos filter screener")
            send_telegram(format_candidate_message(pool))
            dashboard_data.add_screener_candidate(pool)
            performance_tracker.register_candidate(pool)  # mulai pantau performanya dari sekarang
            state.mark_token_seen(token_key)
            all_candidates.append(pool)

    if trigger_deep_analysis and all_candidates:
        import time
        import deep_analysis
        for i, pool in enumerate(all_candidates):
            if i > 0:
                time.sleep(3)  # jeda antar analisis biar gak nembak GeckoTerminal beruntun & kena rate limit
            try:
                deep_analysis.analyze_and_notify(pool)
            except Exception as e:
                print(f"[ERROR] Deep analysis gagal untuk {pool['base_token_symbol']}: {e}")

    print(f"[INFO] Screener selesai. Total kandidat baru: {len(all_candidates)}")
    return all_candidates


if __name__ == "__main__":
    run_once()
