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
import smart_money_finder
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


def format_combined_message(pool: dict, result: dict) -> str:
    """
    1 pesan gabungan berisi info kandidat + hasil deep analysis sekaligus -
    dulu ini 2 pesan terpisah, digabung jadi 1 biar lebih ringkas TAPI tetap
    dikirim REAL-TIME (bukan diantri harian) karena timing itu penting banget
    buat meme coin - telat beberapa jam aja bisa bikin sinyalnya gak relevan lagi.
    """
    flags_text = "\n".join(f"• {f}" for f in result["security_flags"][:4])
    socials = result.get("socials", {})
    social_bits = []
    if socials.get("twitter"):
        social_bits.append(f"[Twitter]({socials['twitter']})")
    if socials.get("telegram"):
        social_bits.append(f"[Telegram]({socials['telegram']})")
    social_line = " | ".join(social_bits) if social_bits else "Sosial media tidak ditemukan"

    technical = result.get("technical", {})
    tech_line = technical.get("summary", "")

    return (
        f"🚀 *{pool['base_token_symbol']}* ({pool['chain'].title()}) — Kandidat Baru\n\n"
        f"Market Cap: ${pool['market_cap_usd']:,.0f} | Liquidity: ${pool['liquidity_usd']:,.0f}\n"
        f"Volume 24h: ${pool['volume_24h_usd']:,.0f} | 1h: {pool['price_change_1h_pct']:.1f}% | 24h: {pool['price_change_24h_pct']:.1f}%\n\n"
        f"*Risiko:* {result['risk_score']}\n"
        f"{flags_text}\n\n"
        f"*Teknikal:* {tech_line}\n\n"
        f"*Sosial:* {social_line}\n"
        f"Pool: `{pool['pool_address']}`\n"
        f"Chart: {pool['dex_url']}\n\n"
        f"⚠️ _Bukan saran finansial. Selalu DYOR._"
    )


def format_strong_signal_message(pool: dict, overlap_wallets: list) -> str:
    wallet_preview = overlap_wallets[0][:10] + "..."
    extra = f" (+{len(overlap_wallets) - 1} wallet lainnya)" if len(overlap_wallets) > 1 else ""
    return (
        f"🔥 *SINYAL KUAT* — {pool['base_token_symbol']} ({pool['chain'].title()})\n\n"
        f"Token ini lolos filter screener DAN pernah dibeli awal oleh wallet "
        f"smart money yang udah terkonfirmasi ({wallet_preview}{extra}).\n"
        f"Ini keyakinan lebih kuat daripada sinyal tunggal - 2 sistem independen sama-sama nunjuk ke token ini.\n\n"
        f"Market Cap: ${pool['market_cap_usd']:,.0f} | Liquidity: ${pool['liquidity_usd']:,.0f}\n"
        f"Pool address: `{pool['pool_address']}`\n"
        f"Chart: {pool['dex_url']}\n\n"
        f"⚠️ _Tetap DYOR - ini sinyal tambahan, bukan jaminan._"
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
            dashboard_data.add_screener_candidate(pool)
            performance_tracker.register_candidate(pool)  # mulai pantau performanya dari sekarang
            state.mark_token_seen(token_key)
            all_candidates.append(pool)

            # SINYAL GABUNGAN: dikirim TERPISAH & real-time, di atas pesan kandidat
            # biasa - ini sinyal langka & kuat, pantas dapet perhatian ekstra
            overlap = smart_money_finder.check_smart_money_overlap(chain, pool["pool_address"])
            if overlap:
                send_telegram(format_strong_signal_message(pool, overlap))

    if trigger_deep_analysis and all_candidates:
        import time
        import deep_analysis
        for i, pool in enumerate(all_candidates):
            if i > 0:
                time.sleep(3)  # jeda antar analisis biar gak nembak GeckoTerminal beruntun & kena rate limit
            try:
                result = deep_analysis.analyze(pool)
                dashboard_data.add_analysis_report(result)
                # KANDIDAT TOKEN dikirim REAL-TIME (1 pesan gabungan, bukan diantri
                # harian) - timing penting banget buat meme coin, telat = gak relevan lagi.
                # Yang diantri harian cuma aktivitas wallet rutin (lihat wallet_tracker.py).
                send_telegram(format_combined_message(pool, result))
            except Exception as e:
                print(f"[ERROR] Deep analysis gagal untuk {pool['base_token_symbol']}: {e}")

    print(f"[INFO] Screener selesai. Total kandidat baru: {len(all_candidates)} (notif real-time)")
    return all_candidates


if __name__ == "__main__":
    run_once()
