"""
Wrapper untuk GoPlus Security API (gratis, tanpa API key untuk pemakaian wajar).
Dipakai buat cek red flag kontrak: honeypot, mintable, blacklist function,
ownership belum di-renounce, dll.
Docs: https://docs.gopluslabs.io/reference/token-security-api
"""

import requests

BASE_URL = "https://api.gopluslabs.io/api/v1"

# Chain ID GoPlus untuk EVM chain populer
EVM_CHAIN_IDS = {
    "ethereum": "1",
    "bsc": "56",
    "base": "8453",
    "arbitrum": "42161",
    "polygon": "137",
}


def check_evm_token(chain: str, token_address: str) -> dict:
    """Cek keamanan token EVM (Ethereum, Base, BSC, dll)."""
    chain_id = EVM_CHAIN_IDS.get(chain, chain)
    url = f"{BASE_URL}/token_security/{chain_id}"
    try:
        resp = requests.get(url, params={"contract_addresses": token_address}, timeout=20)
        resp.raise_for_status()
        result = resp.json().get("result", {})
        return result.get(token_address.lower(), {})
    except Exception as e:
        print(f"[WARN] GoPlus EVM check gagal: {e}")
        return {}


def check_solana_token(token_address: str) -> dict:
    """Cek keamanan token Solana (SPL token)."""
    url = f"{BASE_URL}/solana/token_security"
    try:
        resp = requests.get(url, params={"contract_addresses": token_address}, timeout=20)
        resp.raise_for_status()
        result = resp.json().get("result", {})
        return result.get(token_address, {})
    except Exception as e:
        print(f"[WARN] GoPlus Solana check gagal: {e}")
        return {}


def summarize_security(chain: str, security: dict) -> dict:
    """
    Ubah raw response GoPlus jadi ringkasan red flag yang gampang dibaca.
    Field beda-beda sedikit antara EVM & Solana, jadi di-handle terpisah.
    """
    if not security:
        return {"available": False, "flags": ["Data keamanan tidak tersedia dari GoPlus"]}

    flags = []

    if chain == "solana":
        if security.get("mintable", {}).get("status") == "1":
            flags.append("⚠️ Token masih bisa di-mint tambahan (mint authority aktif)")
        if security.get("freezable", {}).get("status") == "1":
            flags.append("⚠️ Ada freeze authority - dev bisa freeze wallet holder")
        top_holders = security.get("holders", [])
        try:
            top10_pct = sum(float(h.get("percent", 0)) for h in top_holders[:10]) * 100
            flags.append(f"Top 10 holder pegang ~{top10_pct:.1f}% supply")
        except Exception:
            pass
        lp_locked = security.get("lp_holders", [])
        if lp_locked:
            try:
                locked_pct = sum(
                    float(h.get("percent", 0)) for h in lp_locked if h.get("is_locked") == 1
                ) * 100
                flags.append(f"Liquidity locked: ~{locked_pct:.1f}%")
            except Exception:
                pass
    else:
        if security.get("is_honeypot") == "1":
            flags.append("🚨 TERDETEKSI HONEYPOT - kemungkinan besar tidak bisa dijual!")
        if security.get("is_mintable") == "1":
            flags.append("⚠️ Kontrak bisa mint token baru sesuka dev")
        if security.get("is_open_source") == "0":
            flags.append("⚠️ Kontrak tidak open source / belum verified")
        if security.get("owner_change_balance") == "1":
            flags.append("⚠️ Owner bisa ubah balance wallet lain")
        if security.get("can_take_back_ownership") == "1":
            flags.append("⚠️ Ownership bisa diambil balik oleh dev")
        if security.get("hidden_owner") == "1":
            flags.append("🚨 Ada hidden owner di kontrak")
        buy_tax = security.get("buy_tax")
        sell_tax = security.get("sell_tax")
        if buy_tax and float(buy_tax) > 0.1:
            flags.append(f"⚠️ Buy tax tinggi: {float(buy_tax) * 100:.1f}%")
        if sell_tax and float(sell_tax) > 0.1:
            flags.append(f"⚠️ Sell tax tinggi: {float(sell_tax) * 100:.1f}%")
        holders = security.get("holders", [])
        try:
            top10_pct = sum(float(h.get("percent", 0)) for h in holders[:10]) * 100
            flags.append(f"Top 10 holder pegang ~{top10_pct:.1f}% supply")
        except Exception:
            pass

    if not flags:
        flags.append("Tidak ada red flag signifikan terdeteksi dari GoPlus (tetap DYOR)")

    return {"available": True, "flags": flags}
