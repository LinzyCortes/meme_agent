"""
Wrapper untuk DexScreener public API (gratis, tanpa API key).
Dipakai buat ambil detail token: harga, social links, boosted status, dll.
Docs: https://docs.dexscreener.com/api/reference
"""

import requests

BASE_URL = "https://api.dexscreener.com"


def get_token_pairs(chain_id: str, token_address: str):
    """Ambil semua trading pair untuk satu token address di suatu chain."""
    url = f"{BASE_URL}/token-pairs/v1/{chain_id}/{token_address}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[WARN] DexScreener request gagal: {e}")
        return []


def search_pairs(query: str):
    """Cari pair berdasarkan nama/simbol token."""
    url = f"{BASE_URL}/latest/dex/search"
    try:
        resp = requests.get(url, params={"q": query}, timeout=20)
        resp.raise_for_status()
        return resp.json().get("pairs", [])
    except Exception as e:
        print(f"[WARN] DexScreener search gagal: {e}")
        return []


def get_socials_and_info(pair: dict) -> dict:
    """Ekstrak info sosial media & website dari response pair DexScreener."""
    info = pair.get("info", {}) if pair else {}
    socials = {s.get("type"): s.get("url") for s in info.get("socials", [])}
    websites = [w.get("url") for w in info.get("websites", [])]
    return {
        "image_url": info.get("imageUrl"),
        "websites": websites,
        "twitter": socials.get("twitter"),
        "telegram": socials.get("telegram"),
        "discord": socials.get("discord"),
    }
