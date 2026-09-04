"""
AGENT 5: PERFORMANCE TRACKER
Nyatet "snapshot" harga & market cap token PAS PERTAMA KALI ketemu screener,
terus secara berkala ngecek ulang buat liat udah naik/turun berapa kali lipat.

Ini yang jawab pertanyaan paling penting: "apakah token yang direkomendasiin
sistem ini BENERAN pump beneran, atau cuma kelihatan bagus doang pas ditemuin?"

Cara kerja:
1. register_candidate() dipanggil OTOMATIS dari token_screener.py tiap kali ada
   token kandidat baru - nyimpen harga/mcap saat itu sebagai "titik awal".
2. update_all() - dipanggil berkala (manual atau lewat GitHub Actions) - ngecek
   ulang harga SEMUA token yang lagi dipantau, ngitung "udah X kali lipat dari
   titik awal", kirim notif kalau nembus milestone (2x, 5x, 10x, dst).
3. Token yang udah dipantau lebih dari `tracking_window_days` "lulus" observasi
   dan dipindah ke arsip, dengan hasil akhir tercatat buat statistik.
4. get_summary_stats() - dari SEMUA token yang pernah direkomendasiin, berapa %
   yang beneran nyampe 2x/5x/10x - ini angka konkret buat evaluasi sistem.

Cara pakai:
    python performance_tracker.py
"""

import json
import os
import time
from datetime import datetime, timezone

import geckoterminal_api as gt
import dashboard_data
from config import PERFORMANCE_TRACKING_SETTINGS
from notifier import send_telegram

DATA_FILE_PATH = os.path.join(os.path.dirname(__file__), "tracked_performance.json")


def _load() -> dict:
    if not os.path.exists(DATA_FILE_PATH):
        return {"active": {}, "archived": {}}
    try:
        with open(DATA_FILE_PATH, "r") as f:
            data = json.load(f)
            data.setdefault("active", {})
            data.setdefault("archived", {})
            return data
    except Exception:
        return {"active": {}, "archived": {}}


def _save(data: dict):
    with open(DATA_FILE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def register_candidate(pool: dict):
    """
    Dipanggil OTOMATIS dari token_screener.py tiap kali ada token kandidat baru.
    Nyimpen snapshot "titik awal" - kalau token ini udah pernah dicatet sebelumnya,
    TIDAK ditimpa (biar titik awalnya tetap konsisten dari pertama kali ketemu).
    """
    data = _load()
    key = f"{pool['chain']}:{pool['pool_address']}"
    if key in data["active"] or key in data["archived"]:
        return

    now = datetime.now(timezone.utc).isoformat()
    data["active"][key] = {
        "symbol": pool.get("base_token_symbol"),
        "chain": pool.get("chain"),
        "pool_address": pool.get("pool_address"),
        "first_seen_at": now,
        "entry_price_usd": pool.get("price_usd"),
        "entry_market_cap_usd": pool.get("market_cap_usd"),
        "entry_liquidity_usd": pool.get("liquidity_usd"),
        "last_checked_at": now,
        "current_price_usd": pool.get("price_usd"),
        "current_market_cap_usd": pool.get("market_cap_usd"),
        "current_liquidity_usd": pool.get("liquidity_usd"),
        "current_multiple": 1.0,
        "ath_price_usd": pool.get("price_usd"),
        "ath_multiple": 1.0,
        "ath_at": now,
        "milestones_hit": [],
        "status_note": None,
        "dex_url": pool.get("dex_url"),
        "multiple_history": [1.0],  # dipakai buat sparkline chart di dashboard, maks 30 titik terakhir
    }
    _save(data)
    print(f"[TRACK] Mulai pantau performa {pool.get('base_token_symbol')} ({pool.get('chain')}) "
          f"- entry mcap: ${pool.get('market_cap_usd', 0):,.0f}")


def _chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def update_all():
    settings = PERFORMANCE_TRACKING_SETTINGS
    data = _load()
    active = data["active"]

    if not active:
        print("[INFO] Belum ada token yang dipantau performanya. Nanti otomatis keisi "
              "begitu token_screener.py nemu kandidat baru.")
        dashboard_data.set_performance_tracking(data)
        return

    by_chain = {}
    for key, entry in active.items():
        by_chain.setdefault(entry["chain"], []).append((key, entry))

    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = time.time()
    expire_seconds = settings["tracking_window_days"] * 86400
    milestone_multiples = sorted(settings["milestone_multiples"])

    updated_count = 0
    expired_count = 0
    to_archive = []

    for chain, entries in by_chain.items():
        print(f"[INFO] Update performa {len(entries)} token di {chain}...")
        for batch in _chunk(entries, 30):  # multi-pool endpoint max 30 address/request
            addresses = [e[1]["pool_address"] for e in batch]
            raw_pools = gt.get_pools_multi(chain, addresses)
            raw_by_address = {
                raw.get("attributes", {}).get("address"): raw
                for raw in raw_pools if raw.get("attributes", {}).get("address")
            }

            for key, entry in batch:
                first_seen_ts = datetime.fromisoformat(entry["first_seen_at"]).timestamp()
                age_seconds = now_ts - first_seen_ts
                raw = raw_by_address.get(entry["pool_address"])

                if not raw:
                    # pool gak ketemu lagi - kemungkinan liquidity ditarik total / rug
                    entry["status_note"] = "Pool tidak ditemukan lagi (kemungkinan liquidity ditarik/rug)"
                    if age_seconds >= expire_seconds:
                        to_archive.append((key, entry, "expired_not_found"))
                        expired_count += 1
                    continue

                pool = gt.parse_pool(raw)
                entry["last_checked_at"] = now_iso
                entry["current_price_usd"] = pool["price_usd"]
                entry["current_market_cap_usd"] = pool["market_cap_usd"]
                entry["current_liquidity_usd"] = pool["liquidity_usd"]

                entry_price = entry.get("entry_price_usd") or 0
                current_multiple = (pool["price_usd"] / entry_price) if entry_price > 0 else 0
                entry["current_multiple"] = round(current_multiple, 3)

                # simpen ke history buat sparkline chart di dashboard, maks 30 titik terakhir
                history = entry.get("multiple_history", [])
                history.append(round(current_multiple, 3))
                entry["multiple_history"] = history[-30:]

                if current_multiple > entry.get("ath_multiple", 1.0):
                    entry["ath_multiple"] = round(current_multiple, 3)
                    entry["ath_price_usd"] = pool["price_usd"]
                    entry["ath_at"] = now_iso

                hit_before = set(entry.get("milestones_hit", []))
                # pakai toleransi kecil (epsilon) buat hindarin isu floating point,
                # misal 0.0003/0.0001 kadang keitung 2.9999999999996 bukan 3.0 persis
                newly_hit = [m for m in milestone_multiples if current_multiple >= m - 1e-6 and m not in hit_before]
                for m in newly_hit:
                    entry.setdefault("milestones_hit", []).append(m)
                    send_telegram(
                        f"🚀 MILESTONE! {entry['symbol']} ({chain.title()}) udah {m}x dari titik pertama ketemu!\n"
                        f"Entry: ${entry['entry_market_cap_usd']:,.0f} mcap -> Sekarang: ${pool['market_cap_usd']:,.0f} mcap\n"
                        f"Chart: {entry.get('dex_url', '')}"
                    )

                entry_liq = entry.get("entry_liquidity_usd") or 0
                if entry_liq > 0 and pool["liquidity_usd"] < entry_liq * 0.1:
                    entry["status_note"] = "Liquidity anjlok >90% dari titik awal - kemungkinan rug/ditinggal"
                else:
                    entry["status_note"] = None

                updated_count += 1

                if age_seconds >= expire_seconds:
                    to_archive.append((key, entry, "expired_window"))
                    expired_count += 1

    for key, entry, reason in to_archive:
        _archive(data, key, entry, reason)

    _save(data)
    dashboard_data.set_performance_tracking(data)
    print(f"[INFO] Performance tracker selesai. Di-update: {updated_count} | "
          f"Diarsipkan (selesai observasi): {expired_count} | Masih aktif dipantau: {len(data['active'])}")


def _archive(data: dict, key: str, entry: dict, reason: str):
    entry["final_multiple"] = entry.get("current_multiple", entry.get("ath_multiple", 1.0))
    entry["archived_reason"] = reason
    entry["archived_at"] = datetime.now(timezone.utc).isoformat()
    data["archived"][key] = entry
    if key in data["active"]:
        del data["active"][key]


def get_summary_stats() -> dict:
    """
    Ringkasan performa dari SEMUA token yang PERNAH dipantau (aktif + arsip):
    berapa % yang berhasil nyampe 2x/5x/10x dst. Ini angka konkret buat jawab
    "seberapa valid sih rekomendasi sistem ini".
    """
    data = _load()
    all_entries = list(data["active"].values()) + list(data["archived"].values())
    total = len(all_entries)
    stats = {"total": total}
    if total == 0:
        return stats

    for m in sorted(PERFORMANCE_TRACKING_SETTINGS["milestone_multiples"]):
        count = sum(1 for e in all_entries if e.get("ath_multiple", 1.0) >= m)
        stats[f"hit_{m}x"] = count
        stats[f"hit_{m}x_pct"] = round(count / total * 100, 1)

    rugged = sum(1 for e in all_entries if e.get("status_note") and "rug" in (e.get("status_note") or "").lower())
    stats["rugged_or_abandoned"] = rugged
    stats["rugged_pct"] = round(rugged / total * 100, 1)
    return stats


if __name__ == "__main__":
    update_all()
    stats = get_summary_stats()
    print("\n=== RINGKASAN PERFORMA SEMUA TOKEN YANG PERNAH DIREKOMENDASIIN ===")
    print(f"Total token yang pernah dipantau: {stats.get('total', 0)}")
    if stats.get("total", 0) > 0:
        for m in sorted(PERFORMANCE_TRACKING_SETTINGS["milestone_multiples"]):
            print(f"  Pernah nyampe {m}x titik awal: {stats.get(f'hit_{m}x', 0)} token ({stats.get(f'hit_{m}x_pct', 0)}%)")
        print(f"  Kemungkinan rug/ditinggal: {stats.get('rugged_or_abandoned', 0)} token ({stats.get('rugged_pct', 0)}%)")
