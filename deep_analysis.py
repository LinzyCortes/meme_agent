"""
AGENT 3: DEEP ANALYSIS
Menerima 1 token kandidat (dari token_screener.py atau manual), lalu:
1. Ambil contract address token dari GeckoTerminal
2. Cek keamanan kontrak via GoPlus (honeypot, mintable, holder concentration, dll)
3. Ambil info sosial (twitter/telegram/website) via DexScreener
4. Hitung skor risiko sederhana & kirim laporan lengkap ke Telegram

Cara pakai standalone:
    python deep_analysis.py <chain> <pool_address>
    contoh: python deep_analysis.py solana 8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj
"""

import sys

import geckoterminal_api as gt
import dexscreener_api as ds
import goplus_api
import dashboard_data
from notifier import send_telegram

GECKO_CHAIN_TO_DS_CHAIN = {
    "solana": "solana",
    "ethereum": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "arbitrum": "arbitrum",
}


def get_token_address(chain: str, pool_address: str):
    """
    [FALLBACK] Ambil contract address token dari GeckoTerminal via get_pool_detail
    (1 API call tambahan). Cuma dipakai kalau token_address BELUM ada di pool dict
    (misal dipanggil manual lewat CLI dengan cuma chain+pool_address).
    Kalau pool udah dari token_screener.py/smart_money_finder.py, token_address
    udah otomatis kebawa dari parse_pool() TANPA request tambahan - lihat analyze().
    """
    detail = gt.get_pool_detail(chain, pool_address)
    if not detail:
        print(f"    [WARN] get_pool_detail return kosong untuk {pool_address} (kemungkinan rate limit/timeout GeckoTerminal)")
        return None
    try:
        base_token_id = detail["relationships"]["base_token"]["data"]["id"]
        # format id biasanya "<network>_<address>"
        return base_token_id.split("_", 1)[1]
    except Exception as e:
        print(f"    [WARN] Gagal ekstrak base_token dari response GeckoTerminal untuk {pool_address}: {e}")
        return None


def compute_risk_score(security_flags: list) -> str:
    """Skor kasar berdasarkan jumlah & jenis red flag. Bukan jaminan, cuma panduan awal."""
    critical = sum(1 for f in security_flags if f.startswith("🚨"))
    warning = sum(1 for f in security_flags if f.startswith("⚠️"))

    if critical > 0:
        return "🔴 TINGGI - ada red flag kritis, sangat hati-hati"
    if warning >= 3:
        return "🟠 SEDANG-TINGGI - banyak red flag, riset lebih lanjut wajib"
    if warning >= 1:
        return "🟡 SEDANG - ada beberapa hal yang perlu diwaspadai"
    return "🟢 RELATIF RENDAH - tidak ada red flag mencolok (tetap DYOR)"


def analyze(pool: dict) -> dict:
    """Jalankan analisis lengkap, return dict hasil (tanpa kirim notif)."""
    chain = pool["chain"]
    # Kalau pool udah punya token_address (dari parse_pool() di token_screener.py /
    # smart_money_finder.py), PAKAI ITU LANGSUNG - jangan manggil API GeckoTerminal
    # lagi cuma buat data yang sebenernya udah ada. Cuma fallback ke API call kalau
    # bener-bener belum ada (misal dipanggil manual lewat CLI).
    token_address = pool.get("token_address") or get_token_address(chain, pool["pool_address"])

    security = {}
    if token_address:
        if chain == "solana":
            security = goplus_api.check_solana_token(token_address)
        else:
            security = goplus_api.check_evm_token(chain, token_address)

    sec_summary = goplus_api.summarize_security(chain, security)

    socials = {}
    ds_chain = GECKO_CHAIN_TO_DS_CHAIN.get(chain)
    if ds_chain and token_address:
        pairs = ds.get_token_pairs(ds_chain, token_address)
        if pairs:
            socials = ds.get_socials_and_info(pairs[0])

    risk_score = compute_risk_score(sec_summary["flags"]) if sec_summary["available"] else "⚪ TIDAK DIKETAHUI"

    return {
        "pool": pool,
        "token_address": token_address,
        "security_flags": sec_summary["flags"],
        "risk_score": risk_score,
        "socials": socials,
    }


def format_report(result: dict) -> str:
    pool = result["pool"]
    flags_text = "\n".join(f"• {f}" for f in result["security_flags"])
    socials = result["socials"]
    social_lines = []
    if socials.get("twitter"):
        social_lines.append(f"Twitter: {socials['twitter']}")
    if socials.get("telegram"):
        social_lines.append(f"Telegram: {socials['telegram']}")
    if socials.get("websites"):
        social_lines.append(f"Website: {socials['websites'][0]}")
    social_text = "\n".join(social_lines) if social_lines else "Tidak ditemukan"

    return (
        f"🔍 *Deep Analysis* — {pool['base_token_symbol']} ({pool['chain'].title()})\n\n"
        f"Contract: `{result['token_address'] or 'tidak ditemukan'}`\n"
        f"Market Cap: ${pool['market_cap_usd']:,.0f} | Liquidity: ${pool['liquidity_usd']:,.0f}\n"
        f"Volume 24h: ${pool['volume_24h_usd']:,.0f} | Txns 24h: {pool['txns_24h']}\n\n"
        f"*Estimasi Risiko:* {result['risk_score']}\n"
        f"*Temuan keamanan:*\n{flags_text}\n\n"
        f"*Sosial:*\n{social_text}\n\n"
        f"Chart: {pool['dex_url']}\n\n"
        f"⚠️ _Ini bukan saran finansial. Selalu DYOR (Do Your Own Research) sebelum ambil keputusan._"
    )


def analyze_and_notify(pool: dict):
    result = analyze(pool)
    send_telegram(format_report(result))
    dashboard_data.add_analysis_report(result)
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Pakai: python deep_analysis.py <chain> <pool_address>")
        sys.exit(1)

    chain_arg, pool_address_arg = sys.argv[1], sys.argv[2]
    detail = gt.get_pool_detail(chain_arg, pool_address_arg)
    if not detail:
        print("[ERROR] Pool tidak ditemukan.")
        sys.exit(1)

    pool_parsed = gt.parse_pool(detail)
    pool_parsed["chain"] = chain_arg
    pool_parsed["dex_url"] = gt.build_pool_url(chain_arg, pool_parsed["pool_address"])
    analyze_and_notify(pool_parsed)
